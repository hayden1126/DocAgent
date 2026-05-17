"""Plan 08-04 — `external_cost` threading from LiteLLMBackend through
`BudgetTracker.add()` and the orchestrator's two call sites.

Two call sites in `docagent/core/orchestrator.py`:
- CALL SITE A (~line 166): the `plan()`-call drainage loop introduced
  by Phase 6's how_to_guides P0 fix. Drains responses produced by
  `artifact.plan(ctx)` (e.g. discovery LLM calls).
- CALL SITE B (~line 223): the per-task post-write attribution branch.
  Attributes the per-task `generate()` response's tokens + cost.

A multi-task LiteLLM artifact (e.g. how_to_guides) makes ONE call
inside plan() and N additional calls in generate() (one per topic).
Missing either site = silently dropped cost on multi-task LiteLLM
artifacts, AND spurious `pricing._warned_models` WARNs because the
SDK's `estimate_cost()` falls back to the Opus rate table for a
Gemini/OpenRouter model string.

This file pins that BOTH sites are threaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from docagent.artifacts.registry import (
    DocPatch,
    GenerationContext,
    Registry,
    Task,
    VerifyResult,
)
from docagent.backends.base import GenerationRequest, GenerationResponse
from docagent.core.budget import BudgetTracker
from docagent.core.orchestrator import Orchestrator
from docagent.index.store import open_store

# ---- BudgetTracker.external_cost unit tests --------------------------------


def test_external_cost_overrides_estimate_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external_cost=0.042 -> tracker uses 0.042, NOT estimate_cost(...)."""
    import docagent.core.budget as budget_mod

    calls: list[tuple] = []

    def spy(model, in_tok, out_tok):
        calls.append((model, in_tok, out_tok))
        return 999.0

    monkeypatch.setattr(budget_mod, "estimate_cost", spy)
    tracker = BudgetTracker()
    returned = tracker.add(
        "anthropic/claude-sonnet-4-6", 100, 20, 1, external_cost=0.042
    )
    assert returned == 0.042
    assert tracker.cumulative_cost() == 0.042
    assert calls == [], "estimate_cost should NOT have been called"


def test_external_cost_none_falls_back_to_estimate_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external_cost=None -> tracker calls estimate_cost (existing path)."""
    import docagent.core.budget as budget_mod

    calls: list[tuple] = []

    def spy(model, in_tok, out_tok):
        calls.append((model, in_tok, out_tok))
        return 0.05

    monkeypatch.setattr(budget_mod, "estimate_cost", spy)
    tracker = BudgetTracker()
    returned = tracker.add("claude-sonnet-4-6", 1000, 500, 1)
    assert returned == 0.05
    assert len(calls) == 1


def test_external_cost_zero_is_used_not_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external_cost=0.0 -> use zero, NOT fall back to estimate_cost.
    Tier 3 of the pricing shim returns 0.0 intentionally; that must
    propagate through, not get replaced with Opus estimates."""
    import docagent.core.budget as budget_mod

    monkeypatch.setattr(budget_mod, "estimate_cost", lambda *a: 999.0)
    tracker = BudgetTracker()
    returned = tracker.add(
        "gemini/something-unmapped", 1000, 500, 1, external_cost=0.0
    )
    assert returned == 0.0
    assert tracker.cumulative_cost() == 0.0


# ---- Orchestrator integration: BOTH call sites -----------------------------


@dataclass
class _FakeLiteLLMBackend:
    """Fakes a LiteLLMBackend whose responses carry cost_usd.

    Pops responses from `_queue`; if empty, returns a default response.
    """

    name: str = "litellm"
    model: str = "gemini/gemini-2.5-pro"
    _queue: list[GenerationResponse] | None = None

    def run(self, request: GenerationRequest) -> GenerationResponse:
        if self._queue:
            return self._queue.pop(0)
        return GenerationResponse(
            content="ok", input_tokens=100, output_tokens=20, tool_calls=1, cost_usd=0.001
        )


@dataclass
class _PlanAndGenLiteLLMArtifact:
    """Mirror of `_PlanAndGenArtifact` from Phase 6's test_orchestrator_token_attribution.py.
    Makes one LLM call in plan() AND one in generate() — exercises BOTH
    orchestrator tracker.add() call sites in one run.
    """

    id: str = "plan_and_gen_litellm"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
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


def _build_orchestrator(
    tmp_path: Path,
    backend: _FakeLiteLLMBackend,
    artifact: _PlanAndGenLiteLLMArtifact,
    max_cost: float = 0.0,
) -> Orchestrator:
    registry = Registry()
    registry.register(artifact)  # type: ignore[arg-type]
    store = open_store(tmp_path)
    return Orchestrator(
        repo_root=tmp_path,
        registry=registry,
        backend=backend,  # type: ignore[arg-type]
        store=store,
        max_cost=max_cost,
    )


def test_litellm_cost_flows_through_tracker_per_task(tmp_path: Path) -> None:
    """CALL SITE B: per-task post-write attribution honors cost_usd."""
    backend = _FakeLiteLLMBackend(
        _queue=[
            # plan() call:
            GenerationResponse(
                content="discover", input_tokens=10, output_tokens=5, tool_calls=0, cost_usd=0.0
            ),
            # generate() call:
            GenerationResponse(
                content="x", input_tokens=100, output_tokens=20, tool_calls=1, cost_usd=0.05
            ),
        ]
    )
    artifact = _PlanAndGenLiteLLMArtifact()
    orch = _build_orchestrator(tmp_path, backend, artifact)
    orch.run()
    # Cumulative MUST equal sum of cost_usd values, not estimate_cost result.
    # plan-call cost is 0.0, generate-call cost is 0.05 -> total 0.05.
    assert orch.tracker.cumulative_cost() == 0.05


def test_litellm_cost_flows_through_tracker_for_plan_call_drain(
    tmp_path: Path,
) -> None:
    """CALL SITE A: the plan()-call drainage loop honors cost_usd.

    THE regression test for the W1 fix. plan() makes one call (cost
    0.03); generate() makes one call (cost 0.05). Tracker total must
    be 0.08 -- NOT 0.05 (which would mean plan-call cost was dropped)
    and NOT some estimate_cost-derived value (which would mean Phase
    5's Opus fallback fired for a Gemini model string).
    """
    backend = _FakeLiteLLMBackend(
        _queue=[
            # plan() drainage:
            GenerationResponse(
                content="discover", input_tokens=10, output_tokens=5, tool_calls=0, cost_usd=0.03
            ),
            # generate():
            GenerationResponse(
                content="x", input_tokens=100, output_tokens=20, tool_calls=1, cost_usd=0.05
            ),
        ]
    )
    artifact = _PlanAndGenLiteLLMArtifact()
    orch = _build_orchestrator(tmp_path, backend, artifact)
    # Spy estimate_cost — must NEVER be called when cost_usd is set.
    import docagent.core.budget as budget_mod

    calls: list[tuple] = []
    original_estimate = budget_mod.estimate_cost
    budget_mod.estimate_cost = lambda *a: (calls.append(a), original_estimate(*a))[1]  # type: ignore[assignment]
    try:
        orch.run()
    finally:
        budget_mod.estimate_cost = original_estimate  # type: ignore[assignment]

    assert orch.tracker.cumulative_cost() == 0.08, (
        f"plan-call cost (0.03) was dropped: tracker got "
        f"{orch.tracker.cumulative_cost()}; expected 0.08"
    )
    assert calls == [], (
        f"estimate_cost called {len(calls)} times despite cost_usd being set: "
        f"{calls}"
    )


def test_litellm_plan_call_drain_with_unknown_model_no_warn_spam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No spurious Phase-5 `_warned_models` for unmapped LiteLLM model.

    With cost_usd populated, estimate_cost (and therefore its Opus
    fallback WARN) MUST NOT fire at EITHER call site. The W1 fix's
    self-policing test.
    """
    import docagent.pricing as pricing_mod

    # Reset to a fresh set so prior tests can't leak entries in.
    monkeypatch.setattr(pricing_mod, "_warned_models", set())

    backend = _FakeLiteLLMBackend(
        model="gemini/gemini-2.5-pro",
        _queue=[
            GenerationResponse(
                content="discover", input_tokens=10, output_tokens=5, tool_calls=0, cost_usd=0.03
            ),
            GenerationResponse(
                content="x", input_tokens=100, output_tokens=20, tool_calls=1, cost_usd=0.05
            ),
        ],
    )
    orch = _build_orchestrator(tmp_path, backend, _PlanAndGenLiteLLMArtifact())
    orch.run()
    assert pricing_mod._warned_models == set(), (
        f"Phase 5's _warned_models fired spuriously: {pricing_mod._warned_models}; "
        "this means estimate_cost was called for a Gemini model string, "
        "i.e. external_cost was NOT threaded at one of the call sites."
    )


def test_max_cost_cap_fires_on_litellm_path(tmp_path: Path) -> None:
    """--max-cost cap works on the LiteLLM path: first artifact pushes
    past 0.001 -> next artifact is skipped (would_exceed fires)."""

    @dataclass
    class _SecondArtifact:
        id: str = "second"
        audience: str = "human"
        depends_on: tuple[str, ...] = ("plan_and_gen_litellm",)

        def plan(self, ctx: GenerationContext) -> list[Task]:
            ctx.backend.run(  # type: ignore[attr-defined]
                GenerationRequest(
                    artifact_id=self.id, prompt="d", repo_root=ctx.repo_root
                )
            )
            return [Task(artifact_id=self.id, target_path=ctx.repo_root / "two.md")]

        def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
            resp = ctx.backend.run(  # type: ignore[attr-defined]
                GenerationRequest(
                    artifact_id=self.id, prompt="g", repo_root=ctx.repo_root
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

    backend = _FakeLiteLLMBackend(
        _queue=[
            # First artifact's plan + generate calls produce 0.05 cost total.
            GenerationResponse(content="discover", cost_usd=0.0),
            GenerationResponse(content="x", cost_usd=0.05),
            # Second artifact's plan + generate (shouldn't run).
            GenerationResponse(content="discover2", cost_usd=0.0),
            GenerationResponse(content="y", cost_usd=0.05),
        ]
    )
    registry = Registry()
    registry.register(_PlanAndGenLiteLLMArtifact())  # type: ignore[arg-type]
    registry.register(_SecondArtifact())  # type: ignore[arg-type]
    store = open_store(tmp_path)
    orch = Orchestrator(
        repo_root=tmp_path,
        registry=registry,
        backend=backend,  # type: ignore[arg-type]
        store=store,
        max_cost=0.001,  # tiny cap; first artifact blows through it
    )
    orch.run()
    assert orch.tracker.aborted is True


def test_sdk_response_with_no_cost_usd_still_works(tmp_path: Path) -> None:
    """SDK path: backend returns cost_usd=None -> tracker falls back to
    estimate_cost. Pins zero regression on the SDK path."""
    backend = _FakeLiteLLMBackend(
        model="claude-sonnet-4-6",  # SDK-shaped model string
        _queue=[
            GenerationResponse(
                content="discover",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=None,  # SDK path leaves it None
            ),
            GenerationResponse(
                content="x",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=None,
            ),
        ],
    )
    orch = _build_orchestrator(tmp_path, backend, _PlanAndGenLiteLLMArtifact())
    orch.run()
    # Sonnet at $3 input + $15 output, 1M scale: per-call =
    # 1000 * 3/1_000_000 + 500 * 15/1_000_000 = 0.003 + 0.0075 = 0.0105
    # Sum across two calls = 0.021. Just assert > 0.
    assert orch.tracker.cumulative_cost() > 0
