---
phase: 08-multi-provider-backends
plan: 04
status: shipped
shipped_at: 2026-05-17
commit: 5cbd624
tests_delta: 421 -> 437 (+16)
critical_gate: 'grep -cE "external_cost" docagent/core/orchestrator.py == 2 (PASS)'
---

# Phase 8 Plan 04: CLI `--backend` + BudgetTracker `external_cost` — Summary

THE critical wave. Wires LiteLLM end-to-end through the CLI, the
budget tracker, and BOTH orchestrator `tracker.add()` call sites.
This is the symmetric COST-half of the Phase 6 P0 token-attribution
fix — missing one site would have silently dropped plan()-call cost
on `how_to_guides`-shaped multi-task LiteLLM artifacts.

## What landed

- `docagent/cli.py`:
  - Module-level `_BACKEND_CHOICES = ("agent_sdk", "litellm")` and
    `_LITELLM_NO_MODEL_HINT` multi-line string.
  - `_validate_backend(value: str) -> str` callback rejects anything
    outside the choice set via `typer.BadParameter` (exit code 2).
  - `_select_backend(backend: str, model: str | None)` returns the
    right backend instance OR exits 2 with the multi-line hint if
    `--backend litellm` is missing `--model`.
  - Both `init` and `update` gain `--backend` (default `agent_sdk`) and
    `--model` options. The previous unconditional `AgentSDKBackend()`
    instantiation is replaced with `_select_backend(backend, model or None)`.
- `docagent/core/budget.py`:
  - `BudgetTracker.add()` signature gains `external_cost: float | None = None`
    at the end (backward-compatible — existing positional callers
    unaffected). When `external_cost is not None` (including 0.0), the
    tracker uses that value verbatim instead of calling
    `estimate_cost(...)`. Explicit-zero semantics honored.
- `docagent/core/orchestrator.py` — **TWO** lines changed:
  - **CALL SITE A** (~line 166, the Phase 6 P0 plan()-call drain
    loop): `tracker.add(model, r.input_tokens, r.output_tokens,
    r.tool_calls, external_cost=r.cost_usd)`.
  - **CALL SITE B** (~line 223, the per-task post-write attribution
    branch): `tracker.add(model, response.input_tokens,
    response.output_tokens, response.tool_calls,
    external_cost=response.cost_usd)`.
  - Self-policing W1 grep gate: `grep -cE 'external_cost' docagent/core/orchestrator.py == 2`. PASS.

## Verification

- 16 new tests across two files:
  - `tests/unit/test_orchestrator_budget_litellm.py` (8 tests):
    - 3 BudgetTracker external_cost units: override fires, None falls
      through to estimate_cost, zero is used (not replaced with Opus
      estimate).
    - `test_litellm_cost_flows_through_tracker_per_task` — CALL SITE B
      regression.
    - **`test_litellm_cost_flows_through_tracker_for_plan_call_drain`**
      — THE regression test for the W1 fix. Multi-call fake artifact
      with plan-call cost 0.03 + generate-call cost 0.05; tracker MUST
      equal 0.08 (NOT 0.05 = dropped plan-cost, NOT some estimate-cost
      value); spies on `estimate_cost` and asserts it was never called.
    - `test_litellm_plan_call_drain_with_unknown_model_no_warn_spam`
      — proves Phase 5's `_warned_models` stays empty for a Gemini
      model string, i.e. `estimate_cost` was bypassed at both sites.
    - `test_max_cost_cap_fires_on_litellm_path` — soft cap fires on
      LiteLLM path same as SDK path.
    - `test_sdk_response_with_no_cost_usd_still_works` — SDK path
      (cost_usd=None) still routes through estimate_cost as before.
      Pins zero regression.
  - `tests/unit/test_cli_backend_flag.py` (8 tests):
    - Default agent_sdk (init + update each).
    - Explicit `--backend agent_sdk` (init + update each).
    - `--backend litellm` without `--model` → exit 2 + verbatim hint
      with all three env var names (init + update).
    - `--backend litellm --model gemini/...` wires `LiteLLMBackend`
      with the right model attribute (init + update).
    - `--backend nonsense` rejected with exit 2.
- 437 / 437 green.
- `ruff check` + `mypy --strict` clean on new files; pre-existing
  B008 / no-untyped-def errors in `cli.py` unchanged.

## Deviations

None. The critical two-call-site grep gate is exactly 2.

## Out-of-scope flagged

`docagent/cli.py` has 9 pre-existing B008 ruff warnings for the
existing typer.Option() default pattern and one pre-existing
`no-untyped-def` mypy error on `_index_repo`. Both are baseline; my
Wave 4 changes didn't add new ones to either count.
