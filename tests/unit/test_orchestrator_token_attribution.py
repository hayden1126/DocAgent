"""Regression tests for plan()-call token attribution (Phase 6, Plan 01).

The P0 bug: LLM calls inside `artifact.plan()` land in the orchestrator's
`last_responses` sink, then get discarded by the per-task loop's
`last_responses.clear()` before any draining happens. Phase 6's
`how_to_guides` artifact runs a discovery LLM call inside `plan()`, so
without the drain-block fix the discovery tokens vanish and `--max-cost`
under-reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from docagent.artifacts.registry import DocPatch, GenerationContext, Registry, Task, VerifyResult
from docagent.backends.base import GenerationRequest, GenerationResponse
from docagent.core.orchestrator import Orchestrator
from docagent.index.store import open_store

# ---- Fake backend ----------------------------------------------------------------


@dataclass
class _FakeBackend:
    """Returns a configured GenerationResponse on each call."""

    name: str = "fake"
    model: str | None = "claude-sonnet-4-6"
    input_tokens: int = 1000
    output_tokens: int = 500
    tool_calls: int = 1

    def run(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            content="body",
            tool_calls=self.tool_calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


# ---- Stub artifacts --------------------------------------------------------------


@dataclass
class _PlanAndGenArtifact:
    """Artifact that calls backend once in plan() AND once in generate()."""

    id: str = "plan_and_gen"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        # Discovery-style LLM call — tokens MUST be attributed to run.*.
        ctx.backend.run(  # type: ignore[attr-defined]
            GenerationRequest(
                artifact_id=self.id, prompt="discover", repo_root=ctx.repo_root
            )
        )
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / "out.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        resp = ctx.backend.run(  # type: ignore[attr-defined]
            GenerationRequest(
                artifact_id=self.id, prompt="generate", repo_root=ctx.repo_root
            )
        )
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=resp.content.encode("utf-8"),
            prompt_version="t1",
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


@dataclass
class _PlanOnlyArtifact:
    """plan() makes one backend call; generate() makes zero (pre-baked patch)."""

    id: str = "plan_only"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        ctx.backend.run(  # type: ignore[attr-defined]
            GenerationRequest(
                artifact_id=self.id, prompt="discover", repo_root=ctx.repo_root
            )
        )
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / "po.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        # No backend call here — patch is pre-baked.
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=b"prebaked",
            prompt_version="t1",
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


@dataclass
class _PlanRaisesArtifact:
    """plan() raises BEFORE making any backend call."""

    id: str = "plan_raises"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        raise RuntimeError("plan failure before backend call")

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:  # pragma: no cover
        raise AssertionError("generate should not be called when plan() raises")

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:  # pragma: no cover
        return VerifyResult(ok=True)


@dataclass
class _NoisyPriorArtifact:
    """Runs first, leaves backend responses on the sink to test cross-artifact leakage guard.

    With the W7 top-of-loop clear in place, a stale response from this artifact's
    error path must not leak into the next artifact's accounting.
    """

    id: str = "noisy_prior"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()
    leak_then_raise: bool = True

    def plan(self, ctx: GenerationContext) -> list[Task]:
        if self.leak_then_raise:
            # Make a backend call (response lands in last_responses)…
            ctx.backend.run(  # type: ignore[attr-defined]
                GenerationRequest(
                    artifact_id=self.id, prompt="leak", repo_root=ctx.repo_root
                )
            )
            # …then raise so the per-task loop is skipped (drain wouldn't run).
            raise RuntimeError("intentional leak-and-raise for W7 coverage")
        return []

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:  # pragma: no cover
        raise AssertionError("should not be called")

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:  # pragma: no cover
        return VerifyResult(ok=True)


# ---- Tests ------------------------------------------------------------------------


def test_plan_call_tokens_attributed_to_run(tmp_path: Path) -> None:
    """An artifact that calls backend in plan() AND generate() attributes BOTH calls."""
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_PlanAndGenArtifact())

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=1000, output_tokens=500, tool_calls=1),
        store=store,
    )
    runs = orch.run()
    assert len(runs) == 1
    r = runs[0]
    # Two calls total: discovery + generate. BOTH must be attributed.
    assert r.input_tokens == 2000, f"expected 2000 input tokens (1000 plan + 1000 gen), got {r.input_tokens}"
    assert r.output_tokens == 1000, f"expected 1000 output tokens, got {r.output_tokens}"
    assert r.tool_calls == 2, f"expected 2 tool calls, got {r.tool_calls}"
    assert r.cost_usd > 0.0
    # Tracker matches.
    assert orch.tracker.input_tokens == 2000
    assert orch.tracker.output_tokens == 1000
    store.close()


def test_plan_call_tokens_attributed_when_generate_makes_no_call(tmp_path: Path) -> None:
    """plan() makes a call; generate() returns a pre-baked patch. The plan() tokens MUST still land."""
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_PlanOnlyArtifact())

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=777, output_tokens=333, tool_calls=1),
        store=store,
    )
    runs = orch.run()
    assert len(runs) == 1
    r = runs[0]
    assert r.input_tokens == 777, f"plan()'s tokens were dropped: got {r.input_tokens}"
    assert r.output_tokens == 333
    assert r.tool_calls == 1
    assert r.cost_usd > 0.0
    store.close()


def test_plan_raises_before_call_zero_tokens_and_no_crash(tmp_path: Path) -> None:
    """plan() raises BEFORE the backend call → zero tokens, no crash on stale sink."""
    store = open_store(tmp_path)
    reg = Registry()
    # Run noisy artifact first (leaks a response into sink then raises),
    # then run plan_raises which itself raises before calling backend.
    # With W7 top-of-loop clear AND the new drain block, neither artifact
    # should attribute any tokens.
    reg.register(_NoisyPriorArtifact())
    reg.register(_PlanRaisesArtifact())

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=9999, output_tokens=9999, tool_calls=5),
        store=store,
    )
    runs = orch.run()
    assert len(runs) == 2
    # Both artifacts errored; both should have zero attributed tokens.
    for r in runs:
        assert r.input_tokens == 0, f"{r.artifact_id} leaked tokens: {r.input_tokens}"
        assert r.output_tokens == 0
        assert r.tool_calls == 0
        assert r.cost_usd == pytest.approx(0.0)
    # Tracker too: nothing should have been recorded.
    assert orch.tracker.input_tokens == 0
    assert orch.tracker.output_tokens == 0
    store.close()
