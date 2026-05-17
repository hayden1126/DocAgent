"""Drives plan → generate → verify → write across the artifact DAG."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from docagent._logging import get_logger
from docagent.artifacts.registry import DocArtifact, DocPatch, GenerationContext, Registry
from docagent.backends.base import GenerationRequest, GenerationResponse, LLMBackend
from docagent.core.budget import BudgetTracker
from docagent.core.paths import to_repo_rel_posix
from docagent.index.mentions import index_artifact
from docagent.pricing import format_usd
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
    # Phase 5 — budget telemetry per artifact.
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0


class _InstrumentedBackend:
    """Wrap an `LLMBackend` so the orchestrator can observe each call's
    `GenerationResponse` without modifying any artifact module.

    Appends every successful `run()` response to the shared `sink` list.
    The orchestrator pops + clears the sink per task (so tokens attribute
    1:1 to the calling task) and clears it again at the top of each
    artifact loop iteration to prevent error-path leakage into the next
    artifact (W7).

    Proxies arbitrary attribute access to the inner backend via
    `__getattr__` so future artifacts that read e.g. `backend.tools` or
    `backend.max_turns` keep working (W6).
    """

    def __init__(self, inner: LLMBackend, sink: list[GenerationResponse]) -> None:
        self._inner = inner
        self.name = inner.name
        self.model: str | None = getattr(inner, "model", None)
        self._sink = sink

    def run(self, request: GenerationRequest) -> GenerationResponse:
        response = self._inner.run(request)
        self._sink.append(response)
        return response

    def __getattr__(self, name: str) -> Any:
        # Only reached for names not on the wrapper itself; proxy through.
        return getattr(self._inner, name)


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
    # Phase 5 — soft cost cap and budget telemetry.
    max_cost: float = 0.0
    tracker: BudgetTracker = field(default_factory=BudgetTracker)
    console: Console | None = None

    def run(self) -> list[ArtifactRun]:
        """Execute the artifact DAG and return per-artifact runs.

        Phase 5 note: return type is **unchanged** — still `list[ArtifactRun]`.
        The cumulative `BudgetTracker` is exposed as `self.tracker` for
        callers (CLI / tests) to inspect after `run()` returns.

        Cap semantics (Decision Log §4): the cap check at the top of each
        artifact iteration uses `tracker.would_exceed()` with
        `projected_extra_cost=0.0`. This is a POST-FACT check — "have we
        already exceeded?" — not a pre-flight estimate. One artifact may
        therefore push past the cap before the next iteration's check
        fires. Accurate pre-flight estimation is v2 scope.
        """
        # Apply the cap onto the tracker (which may be freshly constructed
        # or test-injected via `orch.tracker = my_tracker`).
        self.tracker.cap = self.max_cost

        # W8: construct the instrumented backend FIRST, then build the
        # GenerationContext with the wrapper as `backend=`. Don't mutate
        # ctx after construction — GenerationContext may be redefined as
        # frozen later, and re-seating an attribute is fragile.
        last_responses: list[GenerationResponse] = []
        wrapped_backend = _InstrumentedBackend(self.backend, last_responses)
        ctx = GenerationContext(
            repo_root=self.repo_root,
            store=self.store,
            backend=wrapped_backend,
            changed_files=self.changed_files,
            config=dict(self.config),
        )

        subset = list(self.only) if self.only else None
        order: list[DocArtifact] = self.registry.topo_order(subset)
        runs: list[ArtifactRun] = []
        model = getattr(self.backend, "model", None)
        _log.debug("orchestrator.run: %d artifact(s), dry_run=%s", len(order), self.dry_run)

        for artifact in order:
            # Cap check at the top of each artifact loop iteration.
            # See Decision Log §4 — post-fact, not pre-flight.
            if self.tracker.would_exceed():
                self.tracker.mark_aborted()
                break

            # W7: clear the response sink at the TOP of each artifact
            # iteration so a stale response from a prior artifact's error
            # path cannot leak into this artifact's first task.
            last_responses.clear()

            run = ArtifactRun(artifact_id=artifact.id)
            _log.debug("artifact start: %s", artifact.id)
            try:
                tasks = artifact.plan(ctx)
            except Exception as exc:  # pragma: no cover - defensive
                _log.exception("plan failed for %s", artifact.id)
                run.error = f"plan failed: {exc!r}"
                runs.append(run)
                continue

            # Drain any backend responses produced inside plan() (e.g.
            # how_to_guides' discovery call) BEFORE the per-task loop's
            # clear discards them. Iterate ALL entries (future-proofing
            # for plan() with multiple calls), then clear.
            if not self.dry_run:
                for r in last_responses:
                    per_call_cost = self.tracker.add(
                        model, r.input_tokens, r.output_tokens, r.tool_calls
                    )
                    run.input_tokens += r.input_tokens
                    run.output_tokens += r.output_tokens
                    run.tool_calls += r.tool_calls
                    run.cost_usd += per_call_cost
            last_responses.clear()

            multi_task = len(tasks) > 1
            for i, task in enumerate(tasks):
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

                        # Phase 5: attribute the most-recent backend response
                        # to this task and clear the sink so the next task's
                        # generate() produces a fresh entry.
                        response = last_responses[-1] if last_responses else None
                        last_responses.clear()
                        if response is not None:
                            per_call_cost = self.tracker.add(
                                model,
                                response.input_tokens,
                                response.output_tokens,
                                response.tool_calls,
                            )
                            run.input_tokens += response.input_tokens
                            run.output_tokens += response.output_tokens
                            run.tool_calls += response.tool_calls
                            run.cost_usd += per_call_cost

                            # Per-call progress line for multi-task artifacts only.
                            if multi_task and self.console is not None:
                                module_slot = patch.target_path.stem or patch.artifact_id
                                self.console.print(
                                    f"[{i + 1}/{len(tasks)}] {module_slot}  "
                                    f"in={response.input_tokens} out={response.output_tokens}  "
                                    f"call={format_usd(per_call_cost)}  "
                                    f"cum={format_usd(self.tracker.cumulative_cost())}"
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
            now = datetime.now(UTC).isoformat()
            self.store.upsert_artifact(  # type: ignore[attr-defined]
                artifact_id=patch.artifact_id,
                path=target_rel,
                digest=digest,
                last_run=now,
            )
        except Exception as exc:  # pragma: no cover - defensive
            _log.exception("post-write hook failed for %s", patch.artifact_id)
            run.findings.append(f"post-write hook failed: {exc!r}")
