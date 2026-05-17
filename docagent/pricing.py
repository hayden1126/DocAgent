"""Anthropic-only price table and cost helpers.

v1 ships a single canonical backend (`AgentSDKBackend`); multi-provider
support lands in Phase 8. The table below is a small constant dict keyed
by Anthropic model id, plus a `sdk-default` sentinel that maps to the
SDK's current default (Sonnet 4.6 as of the refresh date).

Refreshed 2026-05-17 from
https://platform.claude.com/docs/en/about-claude/pricing

Re-verify quarterly (next: 2026-08-17).
"""

from __future__ import annotations

from docagent._logging import get_logger

_log = get_logger("pricing")

# Model id -> (input $ / Mtok, output $ / Mtok). Refreshed 2026-05-17 from
# https://platform.claude.com/docs/en/about-claude/pricing
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-opus-4-6":   (5.0, 25.0),
    "claude-opus-4-5":   (5.0, 25.0),
    "claude-opus-4-1":   (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0, 5.0),
    # SDK default model id is Sonnet 4.6 as of 2026-05-17. If Anthropic
    # changes the SDK default, update THIS row (not a new sentinel).
    "sdk-default":       (3.0, 15.0),
}

# Highest known input rate among Opus 4.x; used when an unknown model id
# is passed. Overestimates rather than silently undercounting.
_FALLBACK = "claude-opus-4-7"

# Per-model dedup of the unknown-model WARN. Cleared only at process exit.
# Tests must monkeypatch `docagent.pricing._warned_models` to a fresh set
# if they need a clean slate.
_warned_models: set[str] = set()


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for one call given a model id and token counts.

    `model=None` routes to the `sdk-default` sentinel. Unknown models route
    to Opus 4.7 rates and emit a single WARN line per distinct model name
    per process lifetime (dedup via `_warned_models`).
    """
    key = model or "sdk-default"
    rates = PRICES.get(key)
    if rates is None:
        if key not in _warned_models:
            _log.warning(
                "model %r not in price table — estimating with Opus rates", key
            )
            _warned_models.add(key)
        rates = PRICES[_FALLBACK]
    in_rate, out_rate = rates
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def format_usd(amount: float) -> str:
    """Adaptive-precision dollar string.

    Under $1: 3 decimals (`$0.034`).
    $1 and over: 2 decimals (`$1.24`, `$487.00`).
    Zero is rendered with 3 decimals for distinguishability from missing
    data. Threshold is strict `< 1.0`.
    """
    if amount < 1.0:
        return f"${amount:.3f}"
    return f"${amount:.2f}"
