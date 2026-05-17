"""Tests for `docagent.core.budget` — accumulation, cap, summary."""

from __future__ import annotations

import logging

import pytest

from docagent import pricing
from docagent.core.budget import BudgetSummary, BudgetTracker


@pytest.fixture(autouse=True)
def _clean_warned_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pricing, "_warned_models", set())


def test_fresh_tracker_is_zero() -> None:
    t = BudgetTracker(cap=0.0)
    assert t.cumulative_cost() == 0.0
    assert t.aborted is False
    assert t.would_exceed(0.0) is False


def test_cap_zero_disables_check() -> None:
    t = BudgetTracker(cap=0.0)
    assert t.would_exceed(99999.0) is False


def test_negative_cap_disables_check() -> None:
    t = BudgetTracker(cap=-1.0)
    assert t.would_exceed(0.0) is False


def test_add_accumulates_sonnet() -> None:
    t = BudgetTracker(cap=0.0)
    per_call = t.add("claude-sonnet-4-6", 1_000_000, 1_000_000, tool_calls=3)
    assert per_call == 18.0
    assert t.cumulative_cost() == 18.0
    assert t.input_tokens == 1_000_000
    assert t.output_tokens == 1_000_000
    assert t.tool_calls == 3


def test_two_adds_accumulate() -> None:
    t = BudgetTracker(cap=0.0)
    t.add("claude-sonnet-4-6", 1_000_000, 0, 0)
    t.add("claude-sonnet-4-6", 0, 1_000_000, 0)
    assert t.cumulative_cost() == 18.0
    assert t.tool_calls == 0


def test_would_exceed_boundary() -> None:
    t = BudgetTracker(cap=5.0)
    # Seed cumulative to $4.50 by hand-rigged add (avoid SDK dep on test math).
    t._cost = 4.50
    assert t.would_exceed(0.40) is False  # 4.90 not > 5.0
    assert t.would_exceed(0.60) is True  # 5.10 > 5.0
    assert t.would_exceed(0.50) is False  # exactly equal allowed (strict >)


def test_mark_aborted_idempotent() -> None:
    t = BudgetTracker(cap=5.0)
    assert t.aborted is False
    t.mark_aborted()
    assert t.aborted is True
    t.mark_aborted()
    assert t.aborted is True


def test_summary_dataclass_shape() -> None:
    t = BudgetTracker(cap=2.0)
    t.add("claude-sonnet-4-6", 100_000, 50_000, 1)
    s = t.summary(artifacts_completed=3, artifacts_total=10)
    assert isinstance(s, BudgetSummary)
    assert isinstance(s.input_tokens, int)
    assert isinstance(s.output_tokens, int)
    assert isinstance(s.tool_calls, int)
    assert isinstance(s.cost_usd, float)
    assert isinstance(s.artifacts_completed, int)
    assert isinstance(s.artifacts_total, int)
    assert isinstance(s.aborted, bool)
    assert isinstance(s.cap, float)
    assert s.input_tokens == 100_000
    assert s.output_tokens == 50_000
    assert s.tool_calls == 1
    assert s.artifacts_completed == 3
    assert s.artifacts_total == 10
    assert s.cap == 2.0


def test_unknown_model_uses_opus_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    t = BudgetTracker(cap=0.0)
    with caplog.at_level(logging.WARNING, logger="docagent.pricing"):
        per_call = t.add("totally-fake", 1000, 0, 0)
    # Opus 4.7 input rate is $5/Mtok → 1000 * 5 / 1e6 = $0.005
    assert per_call == 0.005
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1


def test_would_exceed_default_is_post_fact() -> None:
    """`would_exceed()` with default `projected_extra_cost=0.0` means
    'have we ALREADY exceeded the cap?' — see Decision Log §4 of PLAN.md."""
    t = BudgetTracker(cap=5.0)
    t._cost = 4.99
    assert t.would_exceed() is False
    t._cost = 5.01
    assert t.would_exceed() is True
