---
phase: 05-budget-telemetry
plan: 01
status: shipped
shipped_date: 2026-05-17
commits: 5
tests_added: 49
tests_total: 200 → 249
ruff_status: clean (new files)
mypy_status: strict clean (new files)
requirements_completed: [BUDGET-01, BUDGET-02, BUDGET-03]
---

# Phase 5: Budget telemetry — Summary

Per-run token + cost telemetry now surfaces from `AgentSDKBackend` to the CLI, with a hardcoded Anthropic price table, a per-run `BudgetTracker`, a soft `--max-cost` cap with exit code 3, and per-call progress lines for multi-task artifacts. A latent dict-vs-attribute bug in `agent_sdk.py` that silently zeroed every token count was the gate fix for Wave 1.

## One-liner

Token + cost telemetry end-to-end: dict-fix in the SDK backend, pinned Anthropic pricing, `BudgetTracker` threaded through Orchestrator via an instrumented-backend wrapper, `--max-cost` flag + `DOCAGENT_MAX_COST` env on `init`/`update`, shared `_render_summary` footer.

## Commits

| # | Hash | Subject |
|---|------|---------|
| W1 | `c78c260` | `fix(05-budget): wave 1 — use dict .get on ResultMessage.usage` |
| W2 | `9a53d9e` | `feat(05-budget): wave 2 — add docagent/pricing.py with Anthropic table` |
| W3 | `f6fd61a` | `feat(05-budget): wave 3 — add BudgetTracker + BudgetSummary` |
| W4 | `b0457bb` | `feat(05-budget): wave 4 — thread BudgetTracker through Orchestrator` |
| W5 | `c70dca7` | `feat(05-budget): wave 5 — --max-cost flag, DOCAGENT_MAX_COST env, summary` |

## Wave-by-wave deltas

| Wave | Source touched | Tests added |
|------|----------------|-------------|
| 1 | `docagent/backends/agent_sdk.py` (4-line fix) | `tests/unit/test_backend_token_extraction.py` (4 tests) |
| 2 | `docagent/pricing.py` (NEW, 79 lines) | `tests/unit/test_pricing.py` (16 tests) |
| 3 | `docagent/core/budget.py` (NEW, 84 lines) | `tests/unit/test_budget.py` (10 tests) |
| 4 | `docagent/core/orchestrator.py` (expanded ~110 lines) | `tests/unit/test_orchestrator_budget.py` (9 tests) |
| 5 | `docagent/cli.py` (+~115 lines: helpers + flag wiring on both commands) | `tests/unit/test_cli_max_cost.py` (10 tests) |
| Σ | 5 source files (3 new, 2 modified) | 49 new tests |

## The latent bug

`docagent/backends/agent_sdk.py:113-116` used `getattr(usage, "input_tokens", 0) or 0` to read tokens from `ResultMessage.usage`. The SDK types `usage` as `dict[str, Any] | None`. `getattr` on a dict always returns the default, so **every cost-related field in `GenerationResponse` has been zero for the lifetime of the project** — no test asserted token values were non-zero, and the only callsite was a `_log.debug(...)` that printed "0 in, 0 out" silently. Fix: `usage.get("input_tokens", 0) or 0`. Without Wave 1 the rest of the phase is unbuildable.

## Decision-log entries (recorded so future readers don't re-litigate)

1. **`DocPatch` is NOT extended with token fields.** Per-call tokens are run state, not artifact state. The orchestrator wraps `ctx.backend` with `_InstrumentedBackend` to observe each `GenerationResponse` without modifying any artifact module. `docagent/artifacts/registry.py` and all five v1 artifact modules are UNTOUCHED in this phase.
2. **`Orchestrator.run()` return signature is UNCHANGED.** Still `list[ArtifactRun]`. The `BudgetTracker` is exposed as `orchestrator.tracker` — read it after `run()` returns. This avoided breaking the four `orch.run()[0]` call sites in `tests/unit/test_orchestrator_post_write.py`.
3. **Unknown-model WARN is deduplicated per model name.** Module-private `_warned_models: set[str]` in `docagent/pricing.py`. A 20-module run with an unknown model emits ONE WARN total, not 20.
4. **Cap check is post-fact, not pre-flight.** `tracker.would_exceed()` uses `projected_extra_cost=0.0` at the top of each artifact iteration. One artifact may push past the cap before the abort fires (slack ≤ one artifact's cost). Accurate pre-flight estimation is v2.
5. **Shared `_render_summary(console, tracker, dry_run, effective_cap, runs_count, expected_total, wall) -> None` helper.** Both `init` and `update` call it identically — eliminates footer drift between the two CLI paths. Parity is unit-tested via byte-identical `Console(file=StringIO())` comparison.

## Iteration-2 warnings (W6–W9): how they were folded in

The plan-checker flagged four robustness concerns introduced by the `_InstrumentedBackend` resolution path. All four were addressed during Wave 4/Wave 5 execution without deviating from the plan:

- **W6 (wrapper attribute coverage).** Added `def __getattr__(self, name): return getattr(self._inner, name)` to `_InstrumentedBackend`. Documented in the class docstring. Any future artifact that reads e.g. `backend.tools` or `backend.max_turns` works transparently.
- **W7 (sink not cleared between artifacts).** Added `last_responses.clear()` at the TOP of each `for artifact in order:` iteration (before `artifact.plan(ctx)`), in addition to the per-task clear. Prevents an error-path stale response from leaking into the next artifact's first task.
- **W8 (`ctx.backend` mutability assumption).** Re-ordered Wave 4 step 6: the `_InstrumentedBackend` wrapper is constructed FIRST, then `GenerationContext(..., backend=wrapper)` is built ONCE. No post-construction mutation of `ctx.backend`. Robust if `GenerationContext` is later made frozen.
- **W9 (`typer.BadParameter` raised mid-command body).** Moved negative-value rejection into a typer `Option(callback=_validate_max_cost)` so the cap is validated at parse time and produces a clean exit code 2. The `_resolve_max_cost` helper now only does env-var precedence; it never raises. Env-var path stays lenient by design (DEBUG log + fallback to 0).

## Deviations from PLAN.md

The plan was executed as written. Two small in-flight adjustments worth noting for the post-mortem:

1. **`_restore_logger_propagation` autouse fixture added to `test_pricing.py`, `test_budget.py`, and `test_cli_max_cost.py`.** Not in the plan. Discovered when running the full unit suite: `docagent._logging.setup_logging` (called by other tests during the session) sets `propagate=False` on the `docagent` logger, which makes `caplog` blind to records emitted by `docagent.pricing.estimate_cost`. The fixture saves+restores propagation for the duration of each test. Same shape as a defensive cleanup; no production code affected.

2. **One pre-existing unused `# type: ignore[arg-type]` comment removed from `docagent/cli.py` (the `verify` command's `GenerationContext(...)` constructor).** Mypy began flagging it as unused once Phase 5 expanded `cli.py`'s import surface. One-line cleanup; not a behavioral change.

## Code-quality results

```
pytest        → 249 passed (49 new + 200 prior)
ruff check    → clean on docagent/pricing.py, docagent/core/budget.py,
                docagent/core/orchestrator.py, docagent/backends/agent_sdk.py
                (cli.py has 9 PRE-EXISTING B008 errors on typer.Option defaults —
                same count as before Phase 5; Phase 5 added zero new lints)
mypy --strict → clean on the four files above
                (cli.py has 1 PRE-EXISTING no-untyped-def error on `_index_repo` —
                same count as before Phase 5; Phase 5 net change: -1 unused ignore)
```

## Forward links / gotchas for the next session

- **`sdk-default` rates must be re-verified quarterly.** Next refresh due **2026-08-17**. The row is dated in the `PRICES` dict comment (`# Refreshed 2026-05-17`). If the SDK ever bumps its default model id away from Sonnet 4.6, the symptom is a spike of unknown-model WARN records on stderr. Update the `sdk-default` row, not the SDK default.
- **Phase 8 (multi-provider) inherits the `PRICES` data shape verbatim.** Adding Ollama/Gemini/litellm rows is mechanical; the dispatch is already through the model id, and unknown models gracefully fall back with a WARN.
- **Pre-flight cap estimation (v2) is the only meaningful scope gap.** Today's `would_exceed()` is post-fact — a single $5 artifact can exceed a $4 cap by $1 before the abort fires. Accurate pre-flight needs prompt-length + expected-output estimation; tracked in CONTEXT.md "Out of scope."
- **Cache pricing (cache_creation_input_tokens / cache_read_input_tokens) is also v2.** Wave 1 deliberately ignores these keys; including them in v1 would double-count cache hits at full rate (10% actual cost).
- **The `_InstrumentedBackend` wrapper depends on artifacts going through `ctx.backend.run(...)`.** All five v1 artifacts do (verified by codebase grep at plan time). Any future artifact that stashes its own backend reference will not appear in the tracker — degrades cost reporting, not correctness. Documented in the wrapper docstring + threat model row T-05-08.

## Self-check

Files referenced in this SUMMARY:

- `docagent/backends/agent_sdk.py` — exists (Wave 1 commit `c78c260`)
- `docagent/pricing.py` — exists (Wave 2 commit `9a53d9e`)
- `docagent/core/budget.py` — exists (Wave 3 commit `f6fd61a`)
- `docagent/core/orchestrator.py` — modified (Wave 4 commit `b0457bb`)
- `docagent/cli.py` — modified (Wave 5 commit `c70dca7`)
- `tests/unit/test_backend_token_extraction.py` — exists
- `tests/unit/test_pricing.py` — exists
- `tests/unit/test_budget.py` — exists
- `tests/unit/test_orchestrator_budget.py` — exists
- `tests/unit/test_cli_max_cost.py` — exists

## Self-Check: PASSED
