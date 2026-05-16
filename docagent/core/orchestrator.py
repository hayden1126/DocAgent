"""Drives plan → generate → verify → write across the artifact DAG."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docagent.artifacts.registry import DocArtifact, GenerationContext, Registry
from docagent.backends.base import LLMBackend
from docagent.writer import WriteResult, apply_patch


@dataclass
class ArtifactRun:
    artifact_id: str
    patches: list[Path] = field(default_factory=list)
    writes: list[WriteResult] = field(default_factory=list)
    verify_ok: bool = True
    findings: list[str] = field(default_factory=list)
    error: str | None = None


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
                run.patches.append(patch.target_path)
            runs.append(run)
        return runs
