---
phase: 08-multi-provider-backends
plan: 03
status: shipped
shipped_at: 2026-05-17
commit: 761003b
tests_delta: 398 -> 421 (+23)
---

# Phase 8 Plan 03: Tested-model allowlist + per-turn cost — Summary

The LiteLLM backend now identifies unsupported models with a one-time
WARN, computes per-call cost via the Wave 2 shim, accumulates across
turns, and attaches the total to `GenerationResponse.cost_usd`.

## What landed

- `docagent/backends/litellm_backend.py`:
  - `_TESTED_MODELS: frozenset[str]` constant with exactly the six
    models locked in CONTEXT.md: `gemini/gemini-2.5-pro`,
    `gemini/gemini-2.5-flash`,
    `openrouter/anthropic/claude-sonnet-4-6`,
    `openrouter/anthropic/claude-opus-4-7`,
    `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-7`.
    **NO Ollama** (spike verdict; v1.1 re-spike).
  - `_warned_allowlist_models: set[str]` dedup set (separate from the
    Wave 2 pricing dedup set).
  - `_warn_unsupported_model(model: str)` helper — ONE
    `[unsupported-model]` WARN per unknown model name per process,
    non-blocking. Allowlist membership check is `==`, not `startswith` —
    explicit routes only.
  - `LiteLLMBackend.run()` calls `_warn_unsupported_model(self.model)`
    AFTER the lazy `import litellm` (so missing-litellm still raises
    `BackendUnavailableError` first) but BEFORE the first
    `completion()` call.
  - `completion()` kwargs built as a dict; injects
    `extra_body={"usage": {"include": True}}` when
    `self.model.startswith("openrouter/")` — the opt-in that populates
    Tier 1 of the pricing shim.
  - `accumulated_cost: float = 0.0` initialized alongside
    `input_tokens` / `output_tokens`; each turn's
    `cost_for_response(self.model, response)` adds to it.
  - Return statement now threads `cost_usd=accumulated_cost`.

## Verification

- 23 new tests in `tests/unit/test_litellm_backend.py`:
  - 5 allowlist cases: pin-content (frozenset == expected, Ollama not present), known model no-warn, unknown warns-once, dedup same model, multiple distinct unknowns warn N times.
  - 1 tool-loop terminate.
  - 2 tool dispatch (Read happy path, unknown tool name).
  - 4 sandbox-escape: parent-relative, absolute, symlink, accept positive.
  - 2 token accumulation: 3-turn sum + None-usage skip.
  - 1 `tc.model_dump()` round-trip contract.
  - 1 empty `fn.arguments`.
  - 1 max_turns exhaustion WARN.
  - 3 cost accumulation: sum-across-turns, attached-when-known,
    attached-when-unknown (0.0 from Tier 3, NOT None).
  - 2 OpenRouter `extra_body.usage.include` spy: yes for
    `openrouter/*`, no for `anthropic/*`.
  - 1 missing-litellm raises `BackendUnavailableError` with pip hint.
- `ruff check` + `mypy --strict` clean.
- 421 / 421 green (398 baseline + 23 new).

## Deviations

None. All 23 tests + the source changes match the plan.

## Out-of-scope flagged

None.
