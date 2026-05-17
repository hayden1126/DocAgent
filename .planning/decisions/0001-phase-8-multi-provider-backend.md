# ADR-0001: Phase 8 Multi-Provider Backend — Adopt LiteLLM, Keep AgentSDKBackend as Default

**Status:** Accepted (pending spike validation on Ollama citation-emission rate)
**Date:** 2026-05-17
**Phase:** 8 (Multi-provider backends — final v1 phase)
**Supersedes:** The "one canonical backend" decision from `.planning/PROJECT.md`'s
load-bearing bets list, scoped to v1.0 only.

## Context

DocAgent shipped v1.0 with `AgentSDKBackend` (Claude Agent SDK → local
`claude` CLI → user's Anthropic credentials) as the sole inference path.
That was the right v1 cut: it preserved the SDK's prompt caching, sandboxed
tool loop, and Read/Glob/Grep ergonomics without forcing prompt forks per
provider. But BACKEND-01 explicitly names Ollama + Gemini + litellm — the
"one canonical backend" decision was always provisional.

The question for Phase 8: **how do we add 3 providers without writing 3
backends + 3 price tables + 3 tool loops?**

## Considered Options

A. **Write our own per-provider backends.** `OllamaBackend`, `GeminiBackend`,
   `LiteLLMBackend` as three peers. Maximum control, minimum dep tree.
   Cost: three tool loops to maintain, three pricing tables, the
   cumulative-input-tokens bug (fixed in commit `63e69fe`) now lives in
   three places.

B. **Adopt LiteLLM as the sole multi-provider abstraction.** Replace
   nothing for Anthropic users (keep `AgentSDKBackend` as default); add
   `LiteLLMBackend` covering Ollama / Gemini / OpenRouter / Anthropic-direct
   for `--backend litellm`.

C. **Adopt OpenRouter only.** Single API key, server-side cost in responses.
   Fails BACKEND-01: OpenRouter is cloud-only, no local Ollama route.

D. **Dual support — LiteLLM + OpenRouter as peer backends.** Category error:
   OpenRouter is itself a LiteLLM provider (`openrouter/<provider>/<model>`).
   A separate `OpenRouterBackend` would duplicate ~100% of LiteLLM's OR
   codepath for a ~3% pricing-accuracy edge.

## Decision

**Option B.** Adopt LiteLLM as the sole multi-provider abstraction.

- `AgentSDKBackend` **remains the default** for Anthropic users. The
  Claude Agent SDK preserves prompt caching, sandbox, and tool-loop
  ergonomics on the validated path — no regression risk for the
  highest-traffic user group.
- New `LiteLLMBackend` handles `--backend litellm` for everything else
  (Ollama, Gemini, OpenRouter, Anthropic-direct, OpenAI). One backend
  file, one tool loop, one usage aggregator.
- `docagent/pricing.py` keeps the hand-maintained Anthropic table for the
  SDK path; the LiteLLM path delegates to `litellm.completion_cost(response)`.
  Sentinel `sdk-default` stays.
- Gate LiteLLM behind a `docagent[multi]` extras install. Default
  `pip install docagent` keeps the small dep tree intact.

BACKEND-01's "ollama / gemini / litellm" wording becomes literally true:
`docagent init --backend litellm --model ollama_chat/llama3.1` and
`--backend litellm --model gemini/gemini-2.5-flash` are the supported
invocations.

## Rationale

**Why LiteLLM:**
- Native `ollama_chat/<model>` + `gemini/<model>` + `openrouter/<provider>/<model>`
  routing. Three providers ship in one dependency.
- `model_prices_and_context_window.json` updated multiple times per week
  upstream — eliminates DocAgent's quarterly Anthropic-price refresh
  obligation for non-Anthropic providers.
- `litellm.completion_cost(response)` replaces our hand-maintained price
  table for the LiteLLM path. Cache-discount pricing, which Phase 5
  deferred to v2, becomes free.
- Per-call usage accounting (verified via Context7 docs lookup
  2026-05-17): `completion()` returns a response object with `.usage`
  per call. Cumulative aggregation across an agentic loop is the
  caller's job — but since *we* own the loop, we sum per-call rather
  than relying on a final-message read (the bug we fixed in `63e69fe`).

**Why keep `AgentSDKBackend` as default:**
- Zero regression risk on the validated Anthropic path.
- The Claude Agent SDK's built-in tool loop + sandbox + prompt caching
  are real ergonomics wins. LiteLLM gives us flexibility, not
  superiority on Anthropic.
- Falls back gracefully: if `pip install docagent[multi]` isn't run,
  LiteLLM isn't imported, default SDK path keeps working.

**Why not OpenRouter-only (C):** BACKEND-01 names Ollama explicitly.
OpenRouter is cloud-only — it routes to upstream provider APIs but does
not connect to a local Ollama daemon. C doesn't satisfy the requirement.

**Why not dual LiteLLM + OpenRouter (D):** Verified via Context7 docs
2026-05-17 — OpenRouter is a LiteLLM provider. Adopting LiteLLM gives
users OpenRouter for free via `--model openrouter/anthropic/claude-opus-4-7`.
Writing a separate `OpenRouterBackend` duplicates routing code for an
incremental pricing-accuracy edge. Category error.

## Tool-Loop Strategy

LiteLLM offers three paths for driving the tool-use loop:

1. **`experimental_mcp_client`** (verified late-2025 / `experimental_` tag
   persists). Useful when tools are exposed via MCP server — overkill for
   DocAgent's in-process Read/Glob/Grep.
2. **`AgenticLoop` callback infrastructure**
   (`async_should_run_agentic_loop` + `async_build_agentic_loop_plan`).
   Cleaner for non-MCP tool loops. Documented stable surface.
3. **Hand-written loop on `litellm.completion(..., tools=[...])`.** ~80
   LOC. Maximum control.

**Default pick: hand-written loop (option 3).** DocAgent's tool surface
is fixed (Read/Glob/Grep, no dynamic discovery), and the existing
orchestrator already drives one. A 80-LOC loop in `LiteLLMBackend` is
cheaper to own than wiring through LiteLLM's callback layer for so
narrow a use case. The `AgenticLoop` callback path remains a fallback
if hand-written runs into edge cases we don't want to debug.

## Consequences

**Positive:**
- BACKEND-01's three providers ship in one dep + one backend file.
- Cumulative-tokens correctness becomes a property of *our* loop, not
  the SDK we happen to be using.
- Cache-discount pricing for non-Anthropic providers comes free.
- Phase 5's pricing-refresh obligation shrinks to Anthropic-only.

**Negative:**
- 12 direct deps + ~25-40 transitive on the `[multi]` install path.
- Verifier-citation reliability is provider-dependent. A 7B-class Ollama
  model will skip `<!-- ground: -->` citations under load even with the
  same system prompt. **Mitigation: tested-model allowlist + WARN.**
- `experimental_mcp_client` tag is stable behavior but signaling concern
  — if we end up needing it, the API may shift between releases.

## Risks

1. **Verifier regression on small models.** Llama-3-8B citation-emission
   rate is the spike's gating signal. **If <60%, drop Ollama from
   BACKEND-01 scope** before planning. Mitigation in shipped form:
   `--backend litellm` ships with a tested-model allowlist; unknown
   models emit `[unsupported-model]` WARN. Allowlist starts with
   Claude/Gemini/GPT-4-class only; expands by evidence.

2. **`experimental_mcp_client` lingering experimental.** Verified 2026-05-17
   docs still flag it. Default tool-loop pick is hand-written, so this
   doesn't bite us unless we change strategy.

3. **Dep-tree bloat.** Mitigation: `docagent[multi]` extras gate. Default
   users keep the small tree.

## Spike Requirements (Gating)

Before `/gsd:plan-phase 8` runs, complete this 1-day spike:

1. **Isolated branch** `spike/phase-8-litellm`.
2. **Prototype `LiteLLMBackend`** on `tests/golden/fixtures/tinylib_ts/`
   running end-to-end against:
   - `ollama_chat/llama3.1:8b` (local Ollama; requires
     `ollama pull llama3.1:8b` + ollama daemon running)
   - `gemini/gemini-2.5-flash` (requires `GEMINI_API_KEY` env var)
3. **Measure citation-emission rate on the Ollama path.**
   Definition: of the `<!-- ground: path:lines -->` comments the prompt
   asks for, what fraction appear in the output, and what fraction
   resolve via the existing citations gate?
   - ≥80%: Ollama ships in BACKEND-01 as-is.
   - 60-79%: Ollama ships with a `[unsupported-model]` WARN by default;
     opt-in for users who accept the verifier risk.
   - <60%: Drop Ollama from BACKEND-01 scope; Phase 8 narrows to
     Gemini + OpenRouter + Anthropic-direct only.
4. **`pyproject.toml` dep-tree audit.** Confirm LiteLLM's pins do not
   conflict with `claude-agent-sdk`'s pins (especially `pydantic`).

The spike produces a 1-page `.planning/decisions/0001-spike-results.md`
appended to this ADR before Phase 8 planning starts.

## Invalidators

This ADR is binding unless one of these hits:

- **LiteLLM dep-tree conflict** with `claude-agent-sdk`'s pins (audit
  blocks the gate). → Re-evaluate; possibly Option A (write-own).
- **Citation-emission rate on Ollama <60%** in spike. → Narrow
  BACKEND-01 scope, drop Ollama; ADR survives, requirement changes.
- **`experimental_mcp_client` becomes the only tool-loop path** AND
  is materially broken at Phase 8 kickoff. → Fall back to hand-written
  loop (this is already our default; ADR survives).

## References

- Plan-agent verdict synthesized 2026-05-17: `~/.claude/projects/-home-hayden-DocAgent/memory/todo_phase8_litellm_prep.md`
- Cumulative-input-tokens bug fix: commit `63e69fe`
- Phase 5 pricing table: `docagent/pricing.py`
- LiteLLM docs (Context7 lookup 2026-05-17):
  - Ollama tool calling: https://docs.litellm.ai/docs/providers/ollama
  - Gemini tool calling: https://docs.litellm.ai/docs/providers/gemini
  - MCP / experimental_mcp_client: https://docs.litellm.ai/docs/mcp
  - Agentic loop hook: https://docs.litellm.ai/docs/proxy/agentic_loop_hook
