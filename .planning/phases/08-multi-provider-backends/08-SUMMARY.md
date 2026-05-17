---
phase: 08-multi-provider-backends
status: shipped
shipped_at: 2026-05-17
plans: 6
waves: 6
commits: 7
tests_delta: 385 -> 454 (+69)
requirements_completed: [BACKEND-01 (narrowed), BACKEND-02]
key_gate: 'grep -cE "external_cost" docagent/core/orchestrator.py == 2 (PASS)'
---

# Phase 8: Multi-provider backends — SHIPPED

v1 feature-complete. The DocAgent stack now routes documentation
generation through any of three model families
(Gemini / OpenRouter / Anthropic-direct) via a single `LiteLLMBackend`
behind `pip install docagent[multi]`, with `AgentSDKBackend` remaining
the default (zero regression for existing Anthropic SDK users).

## Plans shipped (6/6)

| Plan | Wave | Commit | What |
|------|------|--------|------|
| 08-01 | 1 | `b0fe3ae` | Port LiteLLMBackend prototype to main + 5 polish deltas + [multi] extras + pydantic≥2.10 floor + script rename |
| 08-02 | 2 | `1f6e9f1` | `_litellm_pricing.py` three-tier fallback + `GenerationResponse.cost_usd` field |
| 08-03 | 3 | `761003b` | `_TESTED_MODELS` allowlist + WARN dedup + per-turn cost accumulation + OpenRouter `usage.include` opt-in |
| 08-04 | 4 | `5cbd624` | CLI `--backend` + `BudgetTracker.external_cost` + orchestrator threads `cost_usd` at BOTH call sites |
| 08-05 | 5 | `eae604e` | Close 9 spike-prototype gaps + RateLimitError single-retry |
| 08-06 | 6 | `3582559` | Golden snapshot via `litellm.completion(mock_response=...)` + how-to discovery audit |
| meta  | — | (this commit) | Phase 8 SHIPPED — v1 feature-complete |

## Test count delta

385 → 454 (+69) across the phase:
- 08-01: +0 (port only)
- 08-02: +13 (`tests/unit/test_litellm_pricing.py`)
- 08-03: +23 (`tests/unit/test_litellm_backend.py`)
- 08-04: +16 (`tests/unit/test_orchestrator_budget_litellm.py` + `tests/unit/test_cli_backend_flag.py`)
- 08-05: +15 (`tests/unit/test_litellm_backend_tool_loop.py`)
- 08-06: +2 (`tests/golden/test_litellm_backend_snapshot.py`)

## Requirements completed

- **BACKEND-01 (narrowed)** — Multi-provider via LiteLLM:
  Gemini / OpenRouter / Anthropic-direct. Ollama explicitly deferred
  to v1.1 per the 2026-05-17 spike (0% citation rate on `llama3.1:8b`).
  Six-model tested allowlist locked.
- **BACKEND-02** — Provider-aware pricing: three-tier shim with
  OpenRouter authoritative cost as Tier 1; `litellm.completion_cost`
  as Tier 2; broad-exception fallback + WARN dedup + 0.0 as Tier 3.

## Critical gates passed

- **W1 self-policing**: `grep -cE 'external_cost' docagent/core/orchestrator.py == 2`.
  Both `tracker.add()` call sites (line ~166 plan-call drainage + line
  ~223 per-task post-write) thread `response.cost_usd` as
  `external_cost`. The symmetric COST-half of Phase 6's P0
  token-attribution fix. Missing either site would have silently
  dropped plan-call cost on `how_to_guides`-shaped multi-task LiteLLM
  artifacts AND emitted spurious Phase-5 Opus-fallback WARNs.
- **Tier 3 broad catch**: `_litellm_pricing.cost_for_response` catches
  bare `Exception`, not just `BadRequestError`. RESEARCH.md Pitfall 1
  verified `openrouter/anthropic/claude-sonnet-4-5` raises bare
  `Exception`.
- **No Ollama on allowlist**:
  `! any(m.startswith("ollama") for m in _TESTED_MODELS)`.
- **`pydantic>=2.10` floor**: `pyproject.toml` bumped from `>=2.7` to
  match LiteLLM 1.85's resolver floor.
- **LiteLLM gated behind `[multi]`**: default `pip install docagent`
  does not pull LiteLLM. `--backend litellm` without `[multi]` raises
  `BackendUnavailableError` with the install hint.
- **RateLimitError single retry**: exactly ONE retry with `time.sleep(2)`
  then re-raise. No exponential backoff. Pinned by two regression
  tests in `test_litellm_backend_tool_loop.py`.

## Key decisions

- **`AgentSDKBackend` remains default.** No regression on the
  validated Anthropic path. Preserves the SDK's prompt caching +
  sandbox. The `--backend` flag is opt-in.
- **One new backend (`LiteLLMBackend`), not three.** No separate
  `OllamaBackend` / `GeminiBackend` / `OpenRouterBackend` — LiteLLM
  routes all of them with a single hand-written tool loop.
- **Hand-written ~80 LOC tool loop, NOT `experimental_mcp_client` or
  `AgenticLoop`.** The fixed Read/Glob/Grep tool surface doesn't
  warrant MCP plumbing or callback indirection.
- **Allowlist is DATA, not code.** Future Ollama re-inclusion is a
  one-constant edit to `_TESTED_MODELS` once the citation-rate spike
  re-runs at ≥80%.
- **Single prompt across all providers.** The point of the allowlist
  is to enforce this constraint — any model that can't ground at
  ≥80% with the shared prompt doesn't belong on the allowlist. The
  `_SYSTEM_PROMPT` content matches `AgentSDKBackend`'s prompt
  verbatim. No per-provider prompt forks.
- **Three-tier pricing**, not one. OpenRouter authoritative cost wins
  over LiteLLM's upstream table because OpenRouter reprices in real
  time as providers shift; LiteLLM's static table lags by days/weeks.
  Pitfall 2.
- **Broad `except Exception` in Tier 3, on purpose**. LiteLLM's
  exception class for unmapped routes drifts. Catching narrowly =
  spurious uncaught exceptions on the cost path. Pitfall 1.
- **External-cost override honors explicit zero.** Tier 3 of the
  pricing shim returns 0.0 intentionally; the tracker must use that
  value, not fall through to estimate_cost's Opus-fallback. Test
  `test_external_cost_zero_is_used_not_overridden` pins this.

## Deviations from plan

None at the phase level. Each plan's individual SUMMARY documents
any per-plan adjustments (all minimal — `# type: ignore[attr-defined]`
on the litellm.AuthenticationError except clause, mostly).

## v1.1 follow-ups

- **Ollama re-spike trigger**: Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ /
  GLM-4.6+. Use `scripts/measure_citation_rate.py` (now permanent, not
  spike-named) to measure. ≥80% citation rate → add to
  `_TESTED_MODELS`. <60% → skip; 60-79% → ship with
  `[unsupported-model]` WARN as already implemented.
- **README "Multi-provider setup" subsection**: auto-regenerates on
  first `docagent update` after Phase 8 lands.
- **`docs/how-to/use-multi-provider-backends.md`**: will surface
  organically via `how_to_guides` topic-discovery on next live
  `docagent update` (Wave 6 audit confirmed).
- **Cache-discount pricing exposure** in the CLI summary: deferred to
  v2 (LiteLLM reports it via `total_cost_usd`; we just sum it now).
- **Streaming output**: deferred to v2 (`litellm.completion()` supports
  it; we don't).

## Phase 8 self-check

- All 6 plans shipped with green tests.
- 7 commits (one per plan + this meta-commit).
- 454 / 454 tests green across the full suite.
- W1 critical gate enforced: exactly 2 `external_cost` references in
  orchestrator.py.
- Ollama deliberately absent from `_TESTED_MODELS`.
- No regression on the SDK path: `docagent init` (no `--backend` flag)
  routes through `AgentSDKBackend` exactly as before. All Phase 6
  token-attribution regression tests still green.
