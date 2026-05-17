# Phase 8 CONTEXT: Multi-provider backends

**Phase:** 8 of 8 (final v1 phase)
**Status:** Discussed — ready to plan
**Decided:** 2026-05-17 (informed by `0001-phase-8-multi-provider-backend.md` ADR + spike measurement)

## Scope (one sentence)

Add a single `LiteLLMBackend` alongside `AgentSDKBackend` that covers
Gemini, OpenRouter, and Anthropic-direct via the LiteLLM SDK, with a
hand-written tool loop, a tested-model allowlist for verifier-citation
reliability, pricing via `litellm.completion_cost()`, gated behind
`docagent[multi]` extras.

## Decisions locked

All major architectural decisions are recorded in:
- `.planning/decisions/0001-phase-8-multi-provider-backend.md` (ADR)
- `.planning/decisions/0001-spike-results.md` (empirical measurement)
- `.planning/decisions/0001-spike-results.json` (raw verdict)

Summary of what's locked:

### Backend architecture

- **`AgentSDKBackend` remains the default.** No regression on the
  validated Anthropic path. Preserves the SDK's prompt caching + sandbox.
- **One new backend: `LiteLLMBackend`.** Selected via `--backend litellm
  --model <litellm-model-string>`. No separate `OllamaBackend`,
  `GeminiBackend`, `OpenRouterBackend` — LiteLLM routes all of them.
- **Ollama is OUT of v1.** Spike on `ollama_chat/llama3.1:8b` measured 0
  tool calls + 1 invented citation = 0% citation-emission rate. Deferred
  to v1.1 with a future-spike trigger on Llama 3.3 70B+ / Qwen 2.5 Coder
  32B+ / GLM-4.6+.

### Tool-loop strategy

- **Hand-written loop on `litellm.completion(..., tools=[...])`.** ~80
  LOC. The spike branch already has a working prototype at
  `docagent/backends/litellm_backend.py` (commits `e945838` + `5179d4d`
  on `spike/phase-8-litellm`). Phase 8 polishes + tests + integrates it.
- **NOT `experimental_mcp_client`** — still flagged experimental in
  late-2025 docs; we don't need MCP plumbing for a fixed Read/Glob/Grep
  tool surface.
- **NOT the `AgenticLoop` callback infrastructure** — cleaner for
  non-MCP loops but adds LiteLLM-side indirection for so narrow a use case.

### Provider scope (v1)

In-scope models:
- **Gemini** — `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-pro`
- **OpenRouter** — `openrouter/<provider>/<model>` (routes to Claude,
  GPT-4, Gemini, high-end open weights)
- **Anthropic-direct** — `anthropic/claude-sonnet-4-6`,
  `anthropic/claude-opus-4-7` (LiteLLM path; alternative to the SDK
  default for users who want LiteLLM's pricing instrumentation)

Out of v1 scope:
- Ollama (any model) — deferred to v1.1 per spike.
- OpenAI direct — works through OpenRouter; no need for a separate path.
- Bedrock / Vertex / Azure OpenAI — works through LiteLLM transparently
  if users set the env vars, but not on the tested allowlist; emits
  `[unsupported-model]` WARN.

### Tested-model allowlist

- Module-private constant in `docagent/backends/litellm_backend.py`:
  `_TESTED_MODELS: frozenset[str]` containing every model string that
  has been measured to produce ≥80% verifier-citation resolution on
  tinylib_ts/.
- Initial set (Phase 8 ships with these tested in CI):
  - `gemini/gemini-2.5-pro`, `gemini/gemini-2.5-flash`
  - `openrouter/anthropic/claude-sonnet-4-6`, `openrouter/anthropic/claude-opus-4-7`
  - `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-7`
- **Unknown model** → emit ONE `[unsupported-model]` WARN per model
  name per process. Same dedup pattern as Phase 5's `_warned_models`
  (extend that primitive — don't duplicate it).
- Allowlist is data, not code: future-spike results add a row without
  a code change. Adding Ollama in v1.1 = one constant edit.

### Pricing integration

- **SDK path (default backend):** existing `docagent/pricing.py` table
  unchanged. Anthropic Sonnet + Opus rates stay hand-maintained.
- **LiteLLM path:** delegate to `litellm.completion_cost(response)`.
  Replaces the hand-maintained price table for everything LiteLLM speaks.
  Cache-discount pricing (which Phase 5 deferred to v2) becomes free.
- `BudgetTracker` is provider-agnostic — already takes USD amounts.
  The `_InstrumentedBackend` wrapper from Phase 5 transparently wraps
  whichever backend is active.

### Token accumulation

- LiteLLM's `completion()` returns a response with `.usage` per call —
  attribute object, NOT a dict (different shape from `claude-agent-sdk`).
  Fields: `prompt_tokens`, `completion_tokens`, `total_tokens`.
- The hand-written loop sums per-call `prompt_tokens` and
  `completion_tokens` across every turn. **No final-message-only read
  trap** (the bug we shipped Phase 1-5 with the SDK backend doesn't
  re-emerge here because we own the loop).
- Regression test: multi-turn fake stream → both `prompt_tokens` sum
  correctly. Mirror the shape from
  `tests/unit/test_backend_token_extraction.py`.

### Packaging

- LiteLLM is an **optional extra**: `pip install docagent[multi]`.
  Default `pip install docagent` keeps the small dep tree (no LiteLLM,
  no Bedrock/SageMaker pre-load warnings, no 25-40 transitive deps).
- `LiteLLMBackend.run()` import error → `BackendUnavailableError`
  with the install hint, matching `AgentSDKBackend`'s pattern.
- `pyproject.toml` mypy override for `litellm.*` already in place from
  the spike (commit `e945838`).

### CLI surface

- New flag: `--backend {agent_sdk,litellm}` on both `init` and `update`.
  Default: `agent_sdk` (no behavior change for existing users).
- `--model <model-string>` already exists; semantics extend:
  - With `--backend agent_sdk`: model string passed to the Claude
    Agent SDK as before.
  - With `--backend litellm`: model string is the LiteLLM routing
    string (`gemini/...`, `openrouter/...`, etc.).
- Help text + man-page guidance: README.md gets a "Multi-provider
  setup" subsection documenting env vars per provider.

### Tool sandbox

- `LiteLLMBackend` already implements `_safe_path` (commit `e945838`)
  resolving every Read/Glob/Grep arg under `request.repo_root` and
  refusing path escapes. Mirrors the SDK's `permission_mode="bypassPermissions"
  + cwd=request.repo_root` ergonomics. Keep this; Phase 8 just adds
  tests around the escape-refusal cases.

### Documentation deliverables

- **`docs/how-to/use-multi-provider-backends.md`** — generated by the
  Phase 6 `how_to_guides` artifact during the Phase 8 execution. Topic
  discovery should pick this up from the README + new code. Must
  include a plain-language statement about the Ollama gap so users
  don't try `--model ollama_chat/...` and get burned by the verifier.
- **README.md** — adds a section about `docagent[multi]` install +
  model selection. Auto-regenerated on first `docagent update` after
  Phase 8 lands.
- **AGENTS.md / CLAUDE.md** — no changes; these target Anthropic's
  Claude family by convention.

## Out of scope (documented to prevent creep)

- **Ollama in any form for v1** — deferred to v1.1 with a re-spike
  trigger.
- **Local-LLM endpoints other than Ollama** (llama.cpp server, vLLM,
  TGI) — covered by `--model openai/local` LiteLLM routing in theory
  but not on the tested allowlist; ship as documented gap.
- **Custom system prompts per provider** — every model in scope gets
  the same DocAgent system prompt. If a provider can't ground citations
  with the shared prompt, it doesn't belong on the allowlist.
- **Streaming output** — `litellm.completion()` supports it; we don't.
  Same as the SDK path.
- **Concurrent multi-provider runs** (`--backend litellm` for one
  artifact, SDK for another in the same run) — single backend per run.
- **Cache-discount pricing exposure** in the CLI summary — LiteLLM
  reports it via `total_cost_usd`; we just sum it. No per-bucket
  breakdown in v1.
- **Bedrock / Vertex / Azure** — work transparently via LiteLLM but
  not on the tested allowlist. WARN; no further support.
- **Per-provider prompt forks** — single prompt for all providers in
  scope. The point of the allowlist is to enforce this constraint.

## Open questions deferred to planning

- Should the WARN about unsupported models go to stderr (via
  `_logging.get_logger("litellm_backend").warning(...)`) or to the
  CLI summary footer? Recommend stderr; matches Phase 5's pattern.
- Should `--backend litellm` without `--model` error or default? Two
  reasonable answers:
  - **Error** ("specify a model via `--model gemini/...`") — explicit,
    no surprise bills.
  - **Default to `anthropic/claude-sonnet-4-6`** — works out of the
    box if `ANTHROPIC_API_KEY` is set; symmetric with SDK default.
  Planner recommends erroring; the SDK path is the "default that just
  works" path.
- How does `--backend litellm` interact with `--max-cost`? Cap should
  apply unchanged; LiteLLM-reported per-call costs flow into the same
  `BudgetTracker`. Confirm in plan.

## Success criteria (mirrors REQUIREMENTS.md but concrete)

1. `docagent init --backend litellm --model gemini/gemini-2.5-pro` runs
   end-to-end on tinylib_ts/ with `GEMINI_API_KEY` set; pricing flows
   through `litellm.completion_cost(response)`; verifier exits 0.
2. `--backend litellm --model openrouter/anthropic/claude-sonnet-4-6`
   works with `OPENROUTER_API_KEY`.
3. `--backend litellm --model anthropic/claude-sonnet-4-6` works with
   `ANTHROPIC_API_KEY` and produces output indistinguishable in quality
   from the SDK path (snapshot test).
4. `AgentSDKBackend` remains the default; existing tests still pass
   unchanged.
5. Tested-model allowlist ships; unknown models emit ONE
   `[unsupported-model]` WARN per model name per process.
6. LiteLLM gated behind `docagent[multi]` extras. Default install
   imports nothing from LiteLLM.
7. Multi-turn token accumulation works correctly; regression test
   mirrors `test_backend_token_extraction.py`.
8. New `docs/how-to/use-multi-provider-backends.md` page generated by
   the existing `how_to_guides` artifact on first run after Phase 8.

## Codebase touchpoints

Pre-existing surface area (no rewrites):
- `docagent/backends/base.py` — `LLMBackend` protocol unchanged.
- `docagent/backends/agent_sdk.py` — untouched; remains default.
- `docagent/core/orchestrator.py` — `_InstrumentedBackend` wraps either
  backend transparently.
- `docagent/core/budget.py` — provider-agnostic.
- `docagent/pricing.py` — Anthropic table stays; LiteLLM path bypasses
  it via `litellm.completion_cost`.
- `docagent/cli.py` — `--backend` and `--model` extension.

New surface area (some already on the spike branch):
- `docagent/backends/litellm_backend.py` — promote from spike branch;
  polish + tests + integrate.
- `docagent/backends/_litellm_pricing.py` — thin wrapper around
  `litellm.completion_cost` with the same WARN-dedup primitive Phase 5
  uses (`_warned_models` extension).
- `tests/unit/test_litellm_backend.py` — token accumulation, tool-call
  loop, path-sandbox escapes, allowlist WARN dedup.
- `tests/golden/test_litellm_backend_snapshot.py` — snapshot test
  against tinylib_ts using a recorded LiteLLM stream (no live API
  calls in CI). Anthropic-direct path so the snapshot is stable.
- `pyproject.toml` — `[multi]` extra already added (commit `e945838`).

Spike branch artifacts to bring forward:
- `docagent/backends/litellm_backend.py` (prototype, ~250 LOC, ruff
  + mypy strict-clean against the new pyproject override).
- `scripts/spike_phase8_citation_rate.py` — keep as a future-spike
  tool for re-measuring Ollama (or any new model) without a code
  change. Move to a permanent location: `scripts/measure_citation_rate.py`
  (rename; the "spike" naming was branch-only).

## Migration path for users

- Existing users on Anthropic via `AgentSDKBackend`: **zero changes
  required.** Default is unchanged.
- New users wanting Gemini: `pip install docagent[multi]` + `export
  GEMINI_API_KEY=...` + `--backend litellm --model gemini/gemini-2.5-pro`.
- Users wanting Ollama: **wait for v1.1.** The README "Multi-provider
  setup" section should state this plainly with the spike-result
  rationale.
