"""Drives plan → generate → verify → write across the artifact DAG."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from docagent.artifacts.registry import DocArtifact, DocPatch, GenerationContext, Registry
from docagent.backends.base import LLMBackend
from docagent.index.mentions import index_artifact
from docagent.writer import WriteResult, apply_patch


def _patch_digest(patch: DocPatch) -> str:
    h = hashlib.sha256()
    h.update(patch.prompt_version.encode("utf-8"))
    h.update(b"\x00")
    h.update(patch.new_content)
    return h.hexdigest()


@dataclass
class ArtifactRun:
    artifact_id: str
    patches: list[Path] = field(default_factory=list)
    writes: list[WriteResult] = field(default_factory=list)
    verify_ok: bool = True
    findings: list[str] = field(default_factory=list)
    error: str | None = None
    mention_count: int = 0
    digest: str | None = None


@dataclass
class Orchestrator:
    repo_root: Path
    registry: Registry
    backend: LLMBackend
    store: object  # docagent.index.store.Store
    changed_files: tuple[Path, ...] = ()
    only: tuple[str, ...] = ()
    dry_run: bool = False

    def run(self) -> list[ArtifactRun]:
        ctx = GenerationContext(
            repo_root=self.repo_root,
            store=self.store,
            backend=self.backend,
            changed_files=self.changed_files,
        )
        subset = list(self.only) if self.only else None
        order: list[DocArtifact] = self.registry.topo_order(subset)
        runs: list[ArtifactRun] = []
        for artifact in order:
            run = ArtifactRun(artifact_id=artifact.id)
            try:
                tasks = artifact.plan(ctx)
            except Exception as exc:  # pragma: no cover - defensive
                run.error = f"plan failed: {exc!r}"
                runs.append(run)
                continue

            for task in tasks:
                try:
                    patch = artifact.generate(task, ctx)
                except NotImplementedError as exc:
                    run.error = f"generate not wired: {exc}"
                    continue
                except Exception as exc:
                    run.error = f"generate failed: {exc!r}"
                    continue

                result = artifact.verify(patch, ctx)
                if not result.ok:
                    run.verify_ok = False
                run.findings.extend(result.findings)
                if result.ok:
                    write_result = apply_patch(patch, self.repo_root, dry_run=self.dry_run)
                    run.writes.append(write_result)
                    if not self.dry_run and write_result.written:
                        self._post_write(patch, run)
                run.patches.append(patch.target_path)
            runs.append(run)
        return runs

    def _post_write(self, patch: DocPatch, run: ArtifactRun) -> None:
        """Populate the mention index and the `artifacts` table after a write.

        Without this hook every artifact has zero mention rows in SQLite and
        ``update`` mode silently does nothing. Failures are caught and folded
        into ``run.findings`` rather than raised — a missing mention row
        degrades incremental mode but doesn't invalidate the artifact.
        """
        try:
            try:
                known = self.store.known_symbol_names()  # type: ignore[attr-defined]
            except AttributeError:
                known = set()
            target_rel = patch.target_path
            if target_rel.is_absolute():
                try:
                    target_rel = target_rel.relative_to(self.repo_root)
                except ValueError:
                    pass
            run.mention_count = index_artifact(
                self.store,
                artifact_id=patch.artifact_id,
                target_path=target_rel,
                content=patch.new_content,
                known_identifiers=known,
            )
            digest = _patch_digest(patch)
            run.digest = digest
            now = datetime.now(timezone.utc).isoformat()
            self.store.upsert_artifact(  # type: ignore[attr-defined]
                artifact_id=patch.artifact_id,
                path=str(target_rel),
                digest=digest,
                last_run=now,
            )
        except Exception as exc:  # pragma: no cover - defensive
            run.findings.append(f"post-write hook failed: {exc!r}")
