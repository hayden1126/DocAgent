"""Tests for the LiteLLM pricing shim (Plan 08-02).

Three-tier ladder per RESEARCH.md Code Example 3:
- Tier 1: OpenRouter server-reported `usage.cost` (preferred over LiteLLM
  upstream).
- Tier 2: `litellm.completion_cost(completion_response=response)`.
- Tier 3: catch broad `Exception` (LiteLLM raises bare `Exception` for
  unmapped models), emit ONE WARN per model name via
  `_warned_pricing_models` dedup, return 0.0.

Tests use attribute-access dataclasses (not dicts) per RESEARCH.md
Pitfall 3 — `response.usage` is an attribute object on real LiteLLM
responses, NOT a dict.
"""

from __future__ import annotations

import logging
import sys
import types
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import pytest

# ---- Fake LiteLLM response shapes ------------------------------------------


@dataclass
class _FakeUsage:
    """Mimics LiteLLM's usage object: attribute access, NOT dict."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # `cost` is OpenRouter-specific; only populated when the caller passes
    # `extra_body={"usage": {"include": True}}`.
    cost: float | str | None = None


@dataclass
class _FakeResponse:
    """Mimics LiteLLM's ModelResponse object."""

    usage: _FakeUsage | None = None
    choices: list[Any] = field(default_factory=list)
    model: str = "test"


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def reset_warned_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-private dedup set to a fresh set per test.

    Mirrors `tests/unit/test_pricing.py`'s pattern for Phase 5's
    `_warned_models` reset.
    """
    from docagent.backends import _litellm_pricing

    monkeypatch.setattr(_litellm_pricing, "_warned_pricing_models", set())


@pytest.fixture(autouse=True)
def _restore_logger_propagation() -> Generator[None, None, None]:
    """`docagent._logging.setup_logging` sets `propagate=False` on the
    `docagent` logger. caplog captures via the root logger, so if another
    test in the same session called `setup_logging`, caplog can't see our
    WARN records. Force propagation on for the duration of the test.
    Mirrors the fixture in `tests/unit/test_pricing.py`.
    """
    logger = logging.getLogger("docagent")
    prior = logger.propagate
    logger.propagate = True
    try:
        yield
    finally:
        logger.propagate = prior


@pytest.fixture
def fake_litellm(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Install a fake `litellm` module in sys.modules whose
    `completion_cost` is a settable stub.

    Mirrors the pattern from RESEARCH.md Code Example 2 — we test the
    actual `import litellm` path the shim uses (not a monkeypatch on the
    shim's lookup).
    """
    fake = types.ModuleType("litellm")
    fake.completion_cost = lambda **kwargs: 0.0  # type: ignore[attr-defined]
    # Provide a stand-in BadRequestError so test_bad_request_error_returns_zero
    # has something to raise.
    fake.BadRequestError = type("BadRequestError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return fake


# ---- Tier 1: OpenRouter server-reported cost -------------------------------


def test_openrouter_server_cost_preferred(
    reset_warned_pricing, fake_litellm
) -> None:
    """When response.usage.cost is populated, OpenRouter cost wins
    over litellm.completion_cost."""
    from docagent.backends._litellm_pricing import cost_for_response

    # Even though completion_cost would return 999.0, server-reported wins.
    fake_litellm.completion_cost = lambda **kw: 999.0
    resp = _FakeResponse(usage=_FakeUsage(cost=0.0123))
    assert cost_for_response("openrouter/anthropic/claude-sonnet-4-6", resp) == 0.0123


def test_openrouter_no_server_cost_falls_through(
    reset_warned_pricing, fake_litellm
) -> None:
    """response.usage.cost is None → Tier 2 fires."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = lambda **kw: 0.0007
    resp = _FakeResponse(usage=_FakeUsage(cost=None))
    assert cost_for_response("openrouter/anthropic/claude-sonnet-4-6", resp) == 0.0007


def test_openrouter_server_cost_string_coerces(
    reset_warned_pricing, fake_litellm
) -> None:
    """Some providers return cost as a string; coerce via float()."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = lambda **kw: 999.0
    resp = _FakeResponse(usage=_FakeUsage(cost="0.05"))
    assert cost_for_response("openrouter/anthropic/claude-sonnet-4-6", resp) == 0.05


def test_openrouter_server_cost_bad_value_falls_through(
    reset_warned_pricing, fake_litellm
) -> None:
    """Non-coercible cost string → Tier 1 returns None → Tier 2 fires."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = lambda **kw: 0.0007
    resp = _FakeResponse(usage=_FakeUsage(cost="not-a-number"))
    # Tier 2 must fire — we should NOT raise.
    assert cost_for_response("openrouter/anthropic/claude-sonnet-4-6", resp) == 0.0007


# ---- Tier 2: litellm.completion_cost --------------------------------------


def test_gemini_completion_cost(reset_warned_pricing, fake_litellm) -> None:
    """Tier 2 happy path for a Gemini model."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = lambda **kw: 0.000135
    resp = _FakeResponse(usage=_FakeUsage(prompt_tokens=100, completion_tokens=20))
    assert cost_for_response("gemini/gemini-2.5-pro", resp) == 0.000135


def test_anthropic_completion_cost(reset_warned_pricing, fake_litellm) -> None:
    """Tier 2 happy path for Anthropic-direct."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = lambda **kw: 0.0006
    resp = _FakeResponse(usage=_FakeUsage(prompt_tokens=100, completion_tokens=20))
    assert cost_for_response("anthropic/claude-sonnet-4-6", resp) == 0.0006


# ---- Tier 3: broad-exception swallow + WARN dedup -------------------------


def _raises(exc: Exception):
    """Return a lambda that raises `exc` when called."""

    def _fn(**_kw: Any) -> float:
        raise exc

    return _fn


def test_unmapped_model_returns_zero(
    reset_warned_pricing, fake_litellm, caplog: pytest.LogCaptureFixture
) -> None:
    """Bare Exception (LiteLLM's actual behavior for unmapped models)
    → Tier 3 catches, returns 0.0."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = _raises(Exception("This model isn't mapped yet"))
    caplog.set_level(logging.WARNING)
    resp = _FakeResponse(usage=_FakeUsage())
    assert cost_for_response("some/totally-unmapped-model", resp) == 0.0


def test_bad_request_error_returns_zero(
    reset_warned_pricing, fake_litellm
) -> None:
    """BadRequestError (and any other non-bare-Exception) also caught."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = _raises(fake_litellm.BadRequestError("nope"))
    resp = _FakeResponse(usage=_FakeUsage())
    assert cost_for_response("anthropic/bogus-model", resp) == 0.0


def test_warn_dedup_same_model(
    reset_warned_pricing, fake_litellm, caplog: pytest.LogCaptureFixture
) -> None:
    """Same unmapped model called 3 times → WARN logged exactly once."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = _raises(Exception("unmapped"))
    caplog.set_level(logging.WARNING)
    resp = _FakeResponse(usage=_FakeUsage())
    for _ in range(3):
        cost_for_response("some/unmapped-model", resp)
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1, f"expected 1 WARN, got {len(warns)}"


def test_warn_per_distinct_model(
    reset_warned_pricing, fake_litellm, caplog: pytest.LogCaptureFixture
) -> None:
    """Two distinct unmapped models → exactly two WARNs (one per name)."""
    from docagent.backends._litellm_pricing import cost_for_response

    fake_litellm.completion_cost = _raises(Exception("unmapped"))
    caplog.set_level(logging.WARNING)
    resp = _FakeResponse(usage=_FakeUsage())
    cost_for_response("provider-a/model-x", resp)
    cost_for_response("provider-b/model-y", resp)
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 2, f"expected 2 WARNs, got {len(warns)}"


def test_warn_message_contains_model_and_exception_class(
    reset_warned_pricing, fake_litellm, caplog: pytest.LogCaptureFixture
) -> None:
    """WARN format includes the model name and the exception class name."""
    from docagent.backends._litellm_pricing import cost_for_response

    class _MyCustomError(Exception):
        pass

    fake_litellm.completion_cost = _raises(_MyCustomError("nope"))
    caplog.set_level(logging.WARNING)
    resp = _FakeResponse(usage=_FakeUsage())
    cost_for_response("some/specific-model-id", resp)
    msg = caplog.records[-1].getMessage()
    assert "some/specific-model-id" in msg
    assert "_MyCustomError" in msg


# ---- GenerationResponse.cost_usd field ------------------------------------


def test_generation_response_cost_usd_default_none() -> None:
    """New optional field defaults to None (SDK path leaves it None)."""
    from docagent.backends.base import GenerationResponse

    assert GenerationResponse(content="x").cost_usd is None


def test_generation_response_cost_usd_attached() -> None:
    """LiteLLM path will attach a float; pin the contract."""
    from docagent.backends.base import GenerationResponse

    assert GenerationResponse(content="x", cost_usd=0.05).cost_usd == 0.05
