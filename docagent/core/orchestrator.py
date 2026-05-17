"""Drives plan → generate → verify → write across the artifact DAG."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from docagent._logging import get_logger
from docagent.artifacts.registry import DocArtifact, DocPatch, GenerationContext, Registry
from docagent.backends.base import LLMBackend
from docagent.core.paths import to_repo_rel_posix
from docagent.index.mentions import index_artifact
from docagent.writer import WriteResult, apply_patch

_log = get_logger("orchestrator")


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
    config: dict[str, object] = field(default_factory=dict)

    def run(self) -> list[ArtifactRun]:
        ctx = GenerationContext(
            repo_root=self.repo_root,
            store=self.store,
            backend=self.backend,
            changed_files=self.changed_files,
            config=dict(self.config),
        )
        subset = list(self.only) if self.only else None
        order: list[DocArtifact] = self.registry.topo_order(subset)
        runs: list[ArtifactRun] = []
        _log.debug("orchestrator.run: %d artifact(s), dry_run=%s", len(order), self.dry_run)
        for artifact in order:
            run = ArtifactRun(artifact_id=artifact.id)
            _log.debug("artifact start: %s", artifact.id)
            try:
                tasks = artifact.plan(ctx)
            except Exception as exc:  # pragma: no cover - defensive
                _log.exception("plan failed for %s", artifact.id)
                run.error = f"plan failed: {exc!r}"
                runs.append(run)
                continue

            for task in tasks:
                try:
                    patch = artifact.generate(task, ctx)
                except NotImplementedError as exc:
                    _log.info("generate not wired: %s (%s)", artifact.id, exc)
                    run.error = f"generate not wired: {exc}"
                    continue
                except Exception as exc:
                    _log.exception("generate failed for %s", artifact.id)
                    run.error = f"generate failed: {exc!r}"
                    continue

                result = artifact.verify(patch, ctx)
                if not result.ok:
                    run.verify_ok = False
                    _log.info("verify failed for %s: %s", artifact.id, result.findings)
                run.findings.extend(result.findings)
                if result.ok:
                    write_result = apply_patch(patch, self.repo_root, dry_run=self.dry_run)
                    run.writes.append(write_result)
                    _log.debug(
                        "wrote %s → %s (written=%s, dry_run=%s)",
                        artifact.id, write_result.target, write_result.written, self.dry_run,
                    )
                    if not self.dry_run and write_result.written:
                        self._post_write(patch, run)
                        # Per-artifact post_write hook (used by multi-file
                        # artifacts like api_reference to persist their
                        # per-unit fingerprint after a successful write).
                        artifact_post = getattr(artifact, "post_write", None)
                        if artifact_post is not None:
                            try:
                                artifact_post(patch, ctx)
                            except Exception as exc:  # pragma: no cover - defensive
                                _log.exception(
                                    "artifact post_write failed for %s", artifact.id
                                )
                                run.findings.append(
                                    f"artifact post_write failed: {exc!r}"
                                )
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
            target_rel = to_repo_rel_posix(self.repo_root, patch.target_path)
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
                path=target_rel,
                digest=digest,
                last_run=now,
            )
        except Exception as exc:  # pragma: no cover - defensive
            _log.exception("post-write hook failed for %s", patch.artifact_id)
            run.findings.append(f"post-write hook failed: {exc!r}")
