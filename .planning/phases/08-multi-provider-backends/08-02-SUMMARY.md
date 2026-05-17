---
phase: 08-multi-provider-backends
plan: 02
status: shipped
shipped_at: 2026-05-17
commit: 1f6e9f1
tests_delta: 385 -> 398 (+13)
---

# Phase 8 Plan 02: `_litellm_pricing.py` three-tier fallback — Summary

LiteLLM pricing shim implemented per RESEARCH.md Code Example 3. The
LiteLLM path now has its own price-resolution ladder, separate from the
Anthropic-only `docagent.pricing.estimate_cost`.

## What landed

- `docagent/backends/_litellm_pricing.py`:
  - `cost_for_response(model: str, response: Any) -> float` implements
    the three-tier ladder. Never raises; returns 0.0 on the fallback
    path.
  - **Tier 1** — OpenRouter authoritative `response.usage.cost`. Only
    fires when `model.startswith("openrouter/")` AND
    `_openrouter_server_cost(response)` returns a coerced float. String
    values coerce; non-coercible values (e.g. `"not-a-number"`) fall
    through to Tier 2.
  - **Tier 2** — `litellm.completion_cost(completion_response=response)`.
    Lazy `import litellm` inside the function keeps the module top
    import-safe without `[multi]` installed.
  - **Tier 3** — **broad** `except Exception:` (Pitfall 1: LiteLLM
    raises bare `Exception` for unmapped routes, NOT `BadRequestError`).
    ONE-WARN-per-model dedup via module-private `_warned_pricing_models:
    set[str]`. WARN message format includes the model name and the
    exception class name. Returns `0.0`.
  - `_openrouter_server_cost(response)` helper handles
    `response.usage is None`, `usage.cost is None`, and non-coercible
    `usage.cost` values (returns None on any failure path).
- `docagent/backends/base.py` — `GenerationResponse.cost_usd: float | None = None`
  field added. SDK path leaves None (unchanged); LiteLLM path will
  populate it in Plan 08-03.

## Verification

- 13 new tests in `tests/unit/test_litellm_pricing.py`:
  - 4 Tier 1 cases (OpenRouter cost preferred, fall-through to Tier 2 when None, string coerce, bad-value fall-through).
  - 2 Tier 2 happy paths (Gemini + Anthropic).
  - 5 Tier 3 cases (bare Exception, BadRequestError, dedup same model, distinct models, WARN message format).
  - 2 `GenerationResponse.cost_usd` field tests (default None + override).
- Logger-propagation fixture mirrors `tests/unit/test_pricing.py` —
  `docagent` logger has `propagate=False` once `setup_logging` is
  called by any earlier test, so caplog can't see WARN records. Force
  on for the test duration.
- `ruff check` + `mypy --strict` clean on both files.
- 32 existing pricing/budget/backend tests still green; no regression.

## Deviations

- `_warned_pricing_models` is a **fresh** module-private set, NOT an
  extension of Phase 5's `docagent.pricing._warned_models`. RESEARCH.md
  Pattern 2 Option A recommendation: keep the two dedup-sets
  semantically separate because they cover different price-resolution
  pipelines (Anthropic-only vs LiteLLM 100+ providers).

## Out-of-scope flagged

Tier 1 currently has no protection against malicious-looking values
like `usage.cost = -999999.0` (a negative cost would reduce
`tracker._cost`). This is an accepted risk per the plan's threat
model — token counts (the real telemetry) are unaffected, and the
cap-check `(cumulative + projected) > cap` doesn't invert on negative
inputs. If providers start poisoning costs, add a `max(0.0, cost)`
floor in v1.1.
