"""Per-run cumulative token + cost tracker.

In-memory only; discarded at the end of each `docagent init` /
`docagent update` invocation. Cap-of-0 (the default) disables checking
entirely — see Pitfall 4 in `.planning/phases/05-budget-telemetry/RESEARCH.md`.

The WARN line for unknown models is emitted by `pricing.estimate_cost`,
not by the tracker; the tracker stays I/O-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docagent.pricing import estimate_cost


@dataclass(frozen=True, slots=True)
class BudgetSummary:
    """Snapshot of a `BudgetTracker` at a moment in time."""

    input_tokens: int
    output_tokens: int
    tool_calls: int
    cost_usd: float
    artifacts_completed: int
    artifacts_total: int
    aborted: bool
    cap: float


@dataclass
class BudgetTracker:
    """Mutable cumulative tracker. `cap <= 0` disables the would_exceed check."""

    cap: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    _cost: float = field(default=0.0, repr=False)
    aborted: bool = False

    def add(
        self,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        tool_calls: int,
        external_cost: float | None = None,
    ) -> float:
        """Accumulate one call's tokens + cost. Returns the per-call cost
        so the orchestrator can render the per-call progress line.

        When `external_cost is not None` (including 0.0), the tracker uses
        that value verbatim instead of calling `pricing.estimate_cost(...)`.
        This is how LiteLLM's authoritative per-call cost (from the
        `_litellm_pricing` shim) flows through unchanged — bypassing the
        Anthropic-only hand-maintained price table. The Phase 5 SDK path
        leaves `external_cost=None` and the estimate_cost branch fires as
        before.
        """
        if external_cost is not None:
            per_call = external_cost
        else:
            per_call = estimate_cost(model, input_tokens, output_tokens)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.tool_calls += tool_calls
        self._cost += per_call
        return per_call

    def cumulative_cost(self) -> float:
        return self._cost

    def would_exceed(self, projected_extra_cost: float = 0.0) -> bool:
        """True if `(cumulative + projected) > cap`. `cap <= 0` short-circuits."""
        if self.cap <= 0:
            return False
        return (self._cost + projected_extra_cost) > self.cap

    def mark_aborted(self) -> None:
        self.aborted = True

    def summary(self, artifacts_completed: int, artifacts_total: int) -> BudgetSummary:
        return BudgetSummary(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_calls=self.tool_calls,
            cost_usd=self._cost,
            artifacts_completed=artifacts_completed,
            artifacts_total=artifacts_total,
            aborted=self.aborted,
            cap=self.cap,
        )
