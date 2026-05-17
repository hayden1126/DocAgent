# Phase 8 PLAN Verification — Multi-provider backends

**Date:** 2026-05-17
**Plans checked:** 08-01 through 08-06 (6 plans, 6 waves)
**Verifier:** gsd-plan-checker
**Status:** PASSED with 2 WARNINGS

---

## Summary

All six Phase 8 plans deliver the locked CONTEXT.md decisions for multi-provider backend support via LiteLLM. Goal-backward verification against BACKEND-01 (narrowed, Ollama deferred) and BACKEND-02 (LiteLLM-delegated pricing) finds no blockers. Two warning-level issues — one is a real correctness gap that should be patched before execution; the other is a cosmetic compliance miss.

The plans collectively wire: spike port (W1) → pricing shim + GenerationResponse.cost_usd (W2) → allowlist + cost accumulation + OpenRouter opt-in (W3) → CLI --backend + BudgetTracker.external_cost + orchestrator threading (W4) → 9-gap closure + RateLimitError retry (W5) → mock_response golden snapshot + how-to discovery confirmation (W6).

## Requirement Coverage

| Requirement | Plans | Status |
|---|---|---|
| BACKEND-01 (narrowed) — multi-provider via LiteLLM, AgentSDK default, Ollama OUT | 08-01, 08-03, 08-04, 08-05, 08-06 | Covered |
| BACKEND-02 — LiteLLM-delegated pricing, unknown-model WARN dedup | 08-02, 08-03, 08-04 | Covered |

## Plan Topology

| Plan | Wave | depends_on | wave=max(deps)+1? | Tasks | Files modified |
|---|---|---|---|---|---|
| 08-01 | 1 | [] | yes | 3 | 3 |
| 08-02 | 2 | [08-01] | yes | 2 (TDD) | 3 |
| 08-03 | 3 | [08-01, 08-02] | yes | 2 (TDD) | 2 |
| 08-04 | 4 | [08-01, 08-02, 08-03] | yes | 2 (TDD) | 5 |
| 08-05 | 5 | [08-04] | yes | 2 (TDD) | 2 |
| 08-06 | 6 | [08-04, 08-05] | yes | 3 (incl. checkpoint:human-verify) | 2 |

No cycles. No forward references. Each plan in its own wave → file-disjoint by construction.

## Critical Correctness Checks (from caller)

| # | Check | Status | Evidence |
|---|---|---|---|
| 1 | Wave 1 uses `git checkout spike/...` (not rewrite) | PASS | 08-01 Task 1 line 149: `git checkout spike/phase-8-litellm -- docagent/backends/litellm_backend.py`. Spike branch exists locally and remote; file confirmed at 270 LOC. |
| 2 | Pricing shim catches broad `Exception` | PASS | 08-02 Task 2 behavior: "`try / except Exception` — BROAD on purpose per Pitfall 1". Verbatim ladder in `<interfaces>` block. |
| 3 | `_warned_models` extension OR parallel set chosen explicitly | PASS | Both 08-02 and 08-03 explicitly choose Option A (parallel sets `_warned_pricing_models` + `_warned_allowlist_models`). 08-02 verification asserts `grep -c '_warned_models' docagent/backends/_litellm_pricing.py` returns 0. |
| 4 | Missing-`--model` exit code 2 | PASS | 08-04 Task 1 + `<interfaces>`: `raise typer.Exit(code=2)`; test `test_litellm_without_model_errors` asserts exit code 2. |
| 5 | AgentSDKBackend remains default | PASS | 08-04 CLI option default `"agent_sdk"`; test `test_default_backend_is_agent_sdk` pins it. Truth list: "Default behavior unchanged". |
| 6 | Ollama absent from `_TESTED_MODELS` | PASS | 08-03 lists exactly six models, none with `ollama` prefix. Test `test_allowlist_contains_six_locked_models` does direct frozenset equality. |
| 7 | `pydantic>=2.10` floor bump | PASS | 08-01 Task 2 explicitly bumps `pydantic>=2.7 → pydantic>=2.10`; verified pyproject.toml currently at `pydantic>=2.7`. |
| 8 | LiteLLM gated behind `[multi]` extras with friendly error | PASS | 08-01 makes the extras gating explicit; lazy `import litellm` lives inside `run()`. BackendUnavailableError pattern preserved from spike (line 95-99). 08-05 Task 1 adds explicit test `test_missing_litellm_install_error_distinct_from_missing_api_key`. |
| 9 | RateLimitError: single retry, 2s sleep | PASS | 08-05 Task 2: `time.sleep(2); response = completion(**completion_kwargs)`. Test asserts EXACTLY two completion calls. BadRequestError NOT caught (re-raises). |
| 10 | Snapshot uses `mock_response`, no live API | PASS | 08-06 Task 1 wraps `litellm.completion` to inject `mock_response=MOCK_README`. Uses `pytest.importorskip("litellm")` so default `[dev]` env skips cleanly. |
| 11 | Three open questions resolved per recommendations | PASS — substance | All three resolutions land: Q1 stderr (08-03 `_log.warning`); Q2 error+exit 2 (08-04); Q3 cap unchanged (08-04 integration test `test_max_cost_cap_fires_on_litellm_path`). Section header marker is cosmetic — see Warning 2. |

## XML Integrity

All six PLAN files parse cleanly. `<tasks>` blocks closed; all `<task>`/`<files>`/`<action>`/`<verify>`/`<done>` elements paired. Frontmatter YAML valid. No malformed citations.

## `files_modified` Honesty

| Plan | Action body modifies | Declared | Match? |
|---|---|---|---|
| 08-01 | litellm_backend.py, pyproject.toml, scripts/measure_citation_rate.py (+ git-rm of spike script) | 3 files | OK — rename's source-side deletion implicit in `git mv` and explicit in Task 3 |
| 08-02 | _litellm_pricing.py, base.py, test_litellm_pricing.py | 3 files | OK |
| 08-03 | litellm_backend.py, test_litellm_backend.py | 2 files | OK |
| 08-04 | cli.py, budget.py, orchestrator.py, test_cli_backend_flag.py, test_orchestrator_budget_litellm.py | 5 files | OK |
| 08-05 | litellm_backend.py, test_litellm_backend_tool_loop.py | 2 files | OK |
| 08-06 | test_litellm_backend_snapshot.py, snapshot file | 2 files | OK |

## Architectural Tier Compliance

| Capability | Tier | Plan(s) assigning | Match? |
|---|---|---|---|
| Tool-use loop driver | Backend | 08-01, 08-03, 08-05 | OK |
| Tool dispatch + sandbox | Backend | 08-01, 08-03 | OK |
| Token accumulation | Backend | 08-01, 08-03, 08-05 | OK |
| Per-call cost lookup | Pricing module (_litellm_pricing.py) | 08-02 | OK |
| Cumulative cost + cap | Orchestrator (BudgetTracker) | 08-04 | OK |
| Backend selection (--backend) | CLI | 08-04 | OK |
| Unsupported-model WARN dedup | Two parallel sets per Option A | 08-02 (pricing) + 08-03 (allowlist) | OK |

No tier mismatches.

## Findings

### WARNING 1 — Plan 08-04 misses the second `tracker.add()` call site in orchestrator

**Dimension:** key_links_planned
**Severity:** WARNING (not BLOCKER — LiteLLM happy path still works; cost cap still fires; only how_to_guides discovery cost on LiteLLM is mis-attributed)
**Plan:** 08-04
**Location:** Task 2 step (2), line 233 of 08-04-PLAN.md

`docagent/core/orchestrator.py` has TWO `tracker.add()` call sites:

- **Line 166** — drains `last_responses` produced inside `artifact.plan()` (e.g. `how_to_guides`' discovery call) BEFORE the per-task loop clears them. Currently calls `self.tracker.add(model, r.input_tokens, r.output_tokens, r.tool_calls)` — NO `external_cost`.
- **Line 223** — per-task post-write cost attribution. Currently calls `self.tracker.add(model, response.input_tokens, ...)` — NO `external_cost`.

Plan 08-04 explicitly addresses ONLY line 223 ("Single-line change", interfaces section "Orchestrator call site update (single line change on line 223)"). It does NOT mention line 166.

**Consequence for the LiteLLM path on a multi-task artifact (`how_to_guides`):**

1. Discovery call runs inside `plan()`, produces `GenerationResponse(..., cost_usd=<litellm-shim-value>)`.
2. Drain loop at line 166 calls `tracker.add(model, r.input_tokens, r.output_tokens, r.tool_calls)` WITHOUT `external_cost`.
3. `BudgetTracker.add` falls through to `pricing.estimate_cost(model, ...)` on a LiteLLM model string (e.g. `gemini/gemini-2.5-pro`).
4. Phase 5's `_warned_models` fires "unknown model ... falling back to Opus rates" WARN.
5. Discovery call is priced at Opus rates instead of the LiteLLM shim value → BACKEND-02's "delegate pricing to LiteLLM" contract is broken for the discovery call.
6. `r.cost_usd` is silently discarded.

The per-task loop (line 223) is fixed by 08-04, so the bulk of cost lands correctly. The miss is contained to artifacts that perform LLM work inside `plan()` — today, only `how_to_guides`.

**Fix hint:** Extend 08-04 Task 2 step (2) to a TWO-line change. Add `external_cost=r.cost_usd` to the line-166 call:

```python
per_call_cost = self.tracker.add(
    model, r.input_tokens, r.output_tokens, r.tool_calls,
    external_cost=r.cost_usd,
)
```

Add an integration test to `test_orchestrator_budget_litellm.py` that drives a fake LiteLLM backend through the drain path (prime `last_responses` with a `GenerationResponse(cost_usd=0.05)`, run orchestrator, assert tracker absorbs 0.05 not the Opus estimate). Update 08-04 frontmatter `key_links` from "line ~223" to "lines ~166 and ~223".

**Why WARNING not BLOCKER:** Phase goal (BACKEND-01 + BACKEND-02 end-to-end LiteLLM run) is still achieved for the most common artifacts (`readme`, single-call paths). `_warned_models` fallback ensures the user is at least warned. `--max-cost` cap still fires because cumulative cost still accumulates (just with wrong values for one call type). Phase 6's `how_to_guides` is the only artifact with `plan()`-side LLM work, and the impact is one discovery call per `--only how_to_guides` run. Not data-corrupting; not user-blocking. Should be fixed before execution to satisfy BACKEND-02 strictly.

---

### WARNING 2 — RESEARCH.md `## Open Questions` section missing `(RESOLVED)` suffix

**Dimension:** research_resolution
**Severity:** WARNING (cosmetic — substance is fully resolved)
**File:** `.planning/phases/08-multi-provider-backends/RESEARCH.md` line 769

Per Dimension 11, the canonical pass marker is `## Open Questions (RESOLVED)`. RESEARCH.md line 769 reads `## Open Questions`. Each of the three questions below contains a `**Recommendation (confirms CONTEXT.md):**` block that resolves it, and the plans implement those recommendations correctly. Substance is complete; only the section-header marker is missing.

**Fix hint:** Rename line 769 from `## Open Questions` to `## Open Questions (RESOLVED)`. One-line edit. No semantic change.

**Why WARNING not BLOCKER:** Every question has an explicit recommendation, and the recommendations are reflected in the plans (verified via Critical Check #11). The cosmetic marker isn't load-bearing.

---

## Dimension Coverage

| Dimension | Status | Notes |
|---|---|---|
| 1. Requirement Coverage | PASS | BACKEND-01 + BACKEND-02 both covered |
| 2. Task Completeness | PASS | All `<task type="auto">` and `tdd="true"` tasks carry files/action/verify/done; checkpoint task carries what-built/how-to-verify/resume-signal |
| 3. Dependency Correctness | PASS | Linear DAG; no cycles |
| 4. Key Links Planned | WARNING | Warning 1: line-166 tracker.add not wired |
| 5. Scope Sanity | PASS | 2-3 tasks/plan; max 5 files (08-04) — surgical edits, well within budget |
| 6. Verification Derivation | PASS | `must_haves.truths` are user-observable; `key_links` connect artifacts |
| 7. Context Compliance | PASS | All locked decisions implemented; Ollama absent; six tested models exact; LiteLLM gated; stderr WARN; error on missing --model |
| 7b. Scope Reduction Detection | PASS | No "v1/v2", "static for now", "future enhancement" patterns. 08-06 task 3 explicitly defers how-to doc generation to user's first `docagent update` — matches CONTEXT.md "generated by the Phase 6 `how_to_guides` artifact during the Phase 8 execution"; correct delegation, not scope reduction |
| 7c. Architectural Tier Compliance | PASS | Every capability assigned to correct tier |
| 8. Nyquist Compliance | PASS | All implementation tasks have `<automated>` verify; no watch-mode flags; sampling ≥2/3 per wave (each wave is a TDD pair: test task + impl task, both with automated verify); Wave 0 test files paired with impl tasks within same plan |
| 9. Cross-Plan Data Contracts | PASS | `GenerationResponse.cost_usd: float | None = None` introduced in 08-02; SDK path leaves None; LiteLLM populates; `external_cost: float | None = None` in 08-04 honors None-fallthrough. Zero treated as explicit override (not fallthrough) — test pins it |
| 10. CLAUDE.md Compliance | PASS | Lazy import pattern matches agent_sdk.py; ruff/mypy strict-clean asserted in `<done>` blocks; no markdown fence; `_SYSTEM_PROMPT` not modified (CONTEXT.md "single prompt for all providers") |
| 11. Research Resolution | WARNING | Warning 2: `(RESOLVED)` suffix missing on section header |
| 12. Pattern Compliance | SKIPPED | No PATTERNS.md found for Phase 8 |

## Recommendation

Both warnings are non-blocking. The phase goal will be achieved as planned. However, **Warning 1 should be patched into 08-04 before execution** to fully satisfy BACKEND-02's "LiteLLM-delegated pricing" contract for the how_to_guides artifact. The patch is mechanical (add `external_cost=r.cost_usd` to the line-166 call site and mirror the test assertion).

**Suggested edit to 08-04 Task 2 step (2):**

> Edit `docagent/core/orchestrator.py`: (a) line ~223 add `external_cost=response.cost_usd`; (b) line ~166 add `external_cost=r.cost_usd`. TWO-line change. Update `files_modified` and key_links wording from "line ~223" to "lines ~166 and ~223". Add `test_litellm_cost_flows_through_drain_path` to `test_orchestrator_budget_litellm.py`.

Warning 2 is purely cosmetic; rename the section header or proceed.

## Verdict

**Status:** PASSED with WARNINGS

Plans collectively deliver Phase 8 goals. Two warnings; no blockers. Caller may proceed to `/gsd:execute-phase 8` either after applying the Warning 1 patch (recommended) or as-is (acceptable; the gap is contained to one artifact type).
