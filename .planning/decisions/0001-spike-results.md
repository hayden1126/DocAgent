# ADR-0001 Spike Results

**Date:** 2026-05-17
**Branch:** `spike/phase-8-litellm`
**Fixture:** `tests/golden/fixtures/tinylib_ts/`
**Outcome:** **Ollama dropped from BACKEND-01 scope.** Phase 8 ships
Gemini + OpenRouter + Anthropic-direct via LiteLLM only. Ollama deferred
to v1.1 with a stronger-model story.

## Measurement

| Model | Tool calls | Citations emitted | Resolved | Rate | Verdict |
|---|---:|---:|---:|---:|---|
| `ollama_chat/llama3.1:8b` | 0 | 1 | 0 | 0.0% | drop_from_backend_01 |

Wall: 34.3s. Tokens: in=488, out=431. Content: 1707 chars of fluent
prose with one invented `<!-- ground: index.d.ts:1-3 -->` citation —
the referenced file does not exist in `tinylib_ts/`.

## Diagnosis

The failure mode is sharper than the ADR anticipated. The
expected v1 failure pattern was "8B-class model skips citations under
load." The actual failure is upstream of that: **the model did not invoke
any tools at all.** It generated a README from prompt context alone and
fabricated a single grounding tag pointing at a non-existent file.

Two non-exclusive root causes:

1. **LiteLLM → Ollama tool-use bridging.** LiteLLM's docs note that for
   models without native function-calling, it falls back to JSON-mode
   tool calls. Llama 3.1 8B has native tool-calling on paper but the
   bridging may not have engaged here. We did not investigate further;
   it would not change the user-facing outcome.

2. **Llama 3.1 8B reasoning ceiling.** Even when tool-use fires, an
   8B model has known weaknesses in multi-step plan-then-tool-use loops.
   The 70B variant performs materially better on agentic benchmarks
   like BFCL and is the smallest Llama variant we'd consider supporting.

Either way, **out of the box with a sensible default, Ollama produces
0% verifier-grounded output.** Shipping that as `--backend litellm
--model ollama_chat/llama3.1:8b` would set users up to ship hallucinated
docs that fail the verifier on first `docagent verify`. The verifier
moat — the project's stated core value — would be undermined by the
backend itself.

## Decision

**Drop Ollama from BACKEND-01 scope.** Reflected in REQUIREMENTS.md by
narrowing the BACKEND-01 row.

Phase 8 ships:
- **Gemini** (`gemini/gemini-2.5-flash`, `gemini/gemini-2.5-pro`)
- **OpenRouter** (`openrouter/<provider>/<model>` — gives users access
  to Claude, GPT-4, Gemini, and high-quality open-weights via one key)
- **Anthropic-direct** (`anthropic/claude-sonnet-4-6`,
  `anthropic/claude-opus-4-7` — useful for users who prefer LiteLLM's
  pricing instrumentation over the Claude Agent SDK's prompt caching)

Ollama is **deferred to v1.1** with a future-spike trigger: when one of
(a) Llama 3.3 70B+, (b) Qwen 2.5 Coder 32B+, (c) GLM-4.6+ becomes
locally-runnable on developer hardware, re-spike with that model. Add to
`docagent[multi]`'s allowlist if rate ≥80%.

## Implications for Phase 8 plan

1. **No Ollama prompt fork needed.** The ADR's "tested-model allowlist"
   primitive ships anyway — Gemini-2.5-pro is the floor, Claude/GPT-4 are
   above. The allowlist is the place to add Ollama later without a code
   change. Plan should structure it as a module-private constant in
   `docagent/backends/litellm_backend.py`.

2. **`docagent[multi]` extras remain.** Pricing-as-LiteLLM-delegation,
   the hand-written tool loop, the `_warned_models` extension to cover
   per-provider unknown models — all unchanged.

3. **Documentation should be explicit.** The README and
   `docs/how-to/use-multi-provider-backends.md` (Phase 6 artifact)
   must say plainly: "Ollama support is on the roadmap; current v1
   Ollama models do not reliably ground citations and would break the
   verifier." Don't hide the gap.

4. **`tests/golden/test_litellm_backend.py`** should snapshot the
   Gemini + OpenRouter happy paths only; no Ollama snapshot until v1.1.

5. **No `--backend ollama` shortcut.** Users wanting Ollama can still
   pass `--backend litellm --model ollama_chat/...` and discover the
   verifier-failure problem themselves. We just don't advertise it.

## What invalidates THIS decision

- A future spike on Llama 3.3 70B (or equivalent) showing ≥60% citation
  resolution → add Ollama to the allowlist; Phase 8 plan doesn't need
  to change, only the constant.
- Llama 4.x lands with materially better function-calling at the 7-13B
  size → re-spike.
- LiteLLM ships a "function-calling shim" for Ollama that emulates tool
  use via a wrapper-prompt and produces measurably better citation
  resolution → re-spike on the wrapped path.

## Files touched by this result

- `.planning/decisions/0001-spike-results.json` — raw measurement.
- `.planning/REQUIREMENTS.md` — BACKEND-01 narrowed (Ollama struck
  through with a v1.1 reference).
- `.planning/ROADMAP.md` — Phase 8 entry updated; remove Ollama from
  the goal line; v1.1 note added.
- This file — narrative + decision record.
