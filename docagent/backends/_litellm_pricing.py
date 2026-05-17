"""LiteLLM pricing shim — three-tier ladder.

Per RESEARCH.md Code Example 3 and Pitfalls 1-3:

- **Tier 1** — OpenRouter authoritative server-reported cost. When the
  caller passes `extra_body={"usage": {"include": True}}` to
  `litellm.completion(...)`, the OpenRouter route attaches a
  `response.usage.cost` field with the server's billed cost. Prefer it
  over the LiteLLM upstream table because OpenRouter shifts model
  pricing in real time as providers reprice and LiteLLM's table lags
  by days-to-weeks.
- **Tier 2** — `litellm.completion_cost(completion_response=response)`.
  LiteLLM's bundled price table covers ~100 providers; for everything
  on the tested-model allowlist, it returns the correct rate.
- **Tier 3** — Broad `except Exception`. LiteLLM raises bare
  `Exception` (NOT just `BadRequestError`) for some unmapped routes
  (e.g. `openrouter/anthropic/claude-sonnet-4-5` empirically — see
  RESEARCH.md Pitfall 1). Catch broadly, emit ONE WARN per model name
  per process via `_warned_pricing_models` dedup, return 0.0.

This module is import-safe without `litellm` installed (lazy `import
litellm` inside `cost_for_response`). The `_warned_pricing_models` set
is module-private and semantically separate from
`docagent.pricing._warned_models` (which scopes to the Anthropic-only
hand-maintained price table for the SDK path).
"""

from __future__ import annotations

from typing import Any

from docagent._logging import get_logger

_log = get_logger("litellm_pricing")

# Module-private dedup set — one WARN per model name per process.
# Tests reset this to a fresh `set()` via monkeypatch (mirror Phase 5's
# `tests/unit/test_pricing.py` pattern).
_warned_pricing_models: set[str] = set()


def cost_for_response(model: str, response: Any) -> float:
    """Return the USD cost for one LiteLLM completion response.

    Never raises. Returns 0.0 on the Tier 3 fallback path; tokens
    accumulated by the caller are unaffected.
    """
    # Tier 1: OpenRouter server-reported cost.
    if model.startswith("openrouter/"):
        server_cost = _openrouter_server_cost(response)
        if server_cost is not None:
            return server_cost

    # Tier 2: LiteLLM upstream price table.
    try:
        import litellm

        return float(litellm.completion_cost(completion_response=response))
    except Exception as exc:
        # Tier 3: dedup-WARN and recover gracefully.
        if model not in _warned_pricing_models:
            _log.warning(
                "litellm could not price model %r (%s); recording $0.00 for this call. "
                "Token counts unaffected. See README troubleshooting for details.",
                model,
                exc.__class__.__name__,
            )
            _warned_pricing_models.add(model)
        return 0.0


def _openrouter_server_cost(response: Any) -> float | None:
    """Pull `response.usage.cost` if present and float-coercible.

    Returns None on any of: missing usage, missing cost, non-coercible
    value (e.g. malformed string). Callers fall through to Tier 2.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    cost = getattr(usage, "cost", None)
    if cost is None:
        return None
    try:
        return float(cost)
    except (TypeError, ValueError):
        return None
