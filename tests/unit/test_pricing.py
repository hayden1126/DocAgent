"""Tests for `docagent.pricing`: arithmetic, fallback WARN, dedup, formatter."""

from __future__ import annotations

import logging

import pytest

from docagent import pricing
from docagent.pricing import estimate_cost, format_usd


@pytest.fixture(autouse=True)
def _clean_warned_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the dedup set per-test so test order is irrelevant."""
    monkeypatch.setattr(pricing, "_warned_models", set())


def test_estimate_cost_sonnet() -> None:
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0


def test_estimate_cost_opus_4_7() -> None:
    assert estimate_cost("claude-opus-4-7", 1_000_000, 1_000_000) == 30.0


def test_estimate_cost_haiku() -> None:
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0


def test_estimate_cost_none_routes_to_sdk_default() -> None:
    # sdk-default maps to Sonnet rates: $3 input, $15 output
    assert estimate_cost(None, 1_000_000, 0) == 3.0


def test_estimate_cost_sdk_default_output() -> None:
    assert estimate_cost("sdk-default", 0, 1_000_000) == 15.0


def test_estimate_cost_unknown_warns_and_uses_opus(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="docagent.pricing"):
        cost = estimate_cost("claude-totally-fake-9", 1_000_000, 0)
    assert cost == 5.0  # Opus 4.7 input rate
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "not in price table" in msg
    assert "claude-totally-fake-9" in msg
    assert "Opus" in msg


def test_unknown_model_warn_deduped_per_model(caplog: pytest.LogCaptureFixture) -> None:
    """Two calls to unknown-x + one call to unknown-y = exactly 2 WARN records."""
    with caplog.at_level(logging.WARNING, logger="docagent.pricing"):
        estimate_cost("unknown-x", 1, 0)
        estimate_cost("unknown-x", 1, 0)
        estimate_cost("unknown-y", 1, 0)
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 2
    messages = [r.getMessage() for r in warns]
    assert any("unknown-x" in m for m in messages)
    assert any("unknown-y" in m for m in messages)


def test_unknown_model_dedup_persists(caplog: pytest.LogCaptureFixture) -> None:
    """After warning once for a model, subsequent calls emit zero new WARNs."""
    with caplog.at_level(logging.WARNING, logger="docagent.pricing"):
        estimate_cost("unknown-x", 1, 0)
        caplog.clear()
        # Second call to the same model: no new WARN.
        cost = estimate_cost("unknown-x", 1, 0)
    assert cost == 5e-6  # still Opus-rated; functional behavior unchanged
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warns == []


def test_known_model_zero_tokens_no_warn(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="docagent.pricing"):
        cost = estimate_cost("claude-sonnet-4-6", 0, 0)
    assert cost == 0.0
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warns == []


def test_estimate_cost_mixed_scale() -> None:
    # 500_000 * 3 + 200_000 * 15 = 1_500_000 + 3_000_000 = 4_500_000 / 1e6 = 4.5
    assert estimate_cost("claude-sonnet-4-6", 500_000, 200_000) == 4.5


def test_format_usd_under_one_three_decimals() -> None:
    assert format_usd(0.034) == "$0.034"


def test_format_usd_zero_three_decimals() -> None:
    # Zero rendered with 3 decimals for distinguishability from missing data.
    assert format_usd(0.0) == "$0.000"


def test_format_usd_just_under_one() -> None:
    # 0.9999 is < 1.0, so the :.3f branch rounds up to "$1.000". This is the
    # documented behavior: strict `< 1.0` threshold, no special-casing.
    assert format_usd(0.9999) == "$1.000"


def test_format_usd_one_dollar_two_decimals() -> None:
    assert format_usd(1.0) == "$1.00"


def test_format_usd_small_dollar() -> None:
    assert format_usd(1.24) == "$1.24"


def test_format_usd_hundreds() -> None:
    assert format_usd(487.0) == "$487.00"
