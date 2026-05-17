# Phase 8: Multi-provider backends - Research

**Researched:** 2026-05-17
**Domain:** Multi-provider LLM backend integration (LiteLLM SDK) layered onto an existing single-backend (Claude Agent SDK) Python codebase
**Confidence:** HIGH for spike-derived findings (working prototype on `spike/phase-8-litellm`); HIGH for pricing/exception behavior (empirically verified via installed `litellm==1.85.0`); MEDIUM for streaming-edge OpenRouter cost-field behavior (verified via GitHub issues, not first-hand)

## Summary

Phase 8 is mostly a productionization phase, not a discovery phase. The `spike/phase-8-litellm` branch contains a 250-LOC `LiteLLMBackend` that already implements: the `LLMBackend` protocol shape, a hand-written `litellm.completion(..., tools=[...])` loop, the path-sandboxed Read/Glob/Grep tool dispatcher, per-turn token accumulation, and the `BackendUnavailableError` install-hint pattern. The ADR + spike-results documents lock every major architectural decision; the planner's job is wiring + tests + pricing-delegation + CLI plumbing + small fix-ups on the spike code. Three concrete bug/gap risks the planner needs to cover:

1. **`litellm.completion_cost()` raises on unknown models** — empirically verified: `litellm.BadRequestError` for malformed/unknown provider strings, bare `Exception` ("This model isn't mapped yet") for valid-syntax-but-unmapped models like `openrouter/anthropic/claude-sonnet-4-5`. The `_litellm_pricing.py` shim MUST catch broad `Exception` (not just BadRequestError/NotFoundError) and fall back to the WARN+sentinel-zero path.
2. **OpenRouter pricing fragility** — `litellm.completion_cost()` works for some OpenRouter routes but not all; OpenRouter itself provides authoritative `usage.cost` server-side when you pass `extra_body={"usage": {"include": true}}`. The shim should prefer OpenRouter's server-reported cost when present and fall back to `completion_cost()` otherwise. Streaming has a known LiteLLM bug here (`#16021`) — DocAgent doesn't stream, so the bug doesn't bite us, but document the rationale.
3. **`response.choices[0].message.tool_calls[i].model_dump()` works** despite `ChatCompletionMessageToolCall` inheriting from `OpenAIObject` (not Pydantic BaseModel). Verified empirically with `litellm==1.85.0`. The spike code is correct here. Pin this to a regression test so a future LiteLLM refactor that drops `model_dump()` doesn't silently break tool-call thread-back.

**Primary recommendation:** Plan as 4 waves: (1) port spike's `litellm_backend.py` to main with strict-mypy + small polish; (2) `_litellm_pricing.py` shim with the three-tier fallback ladder (OpenRouter server cost → `litellm.completion_cost(response)` → WARN+0); (3) `--backend` flag on init/update + tested-model allowlist + `_warned_models` extension; (4) tests — unit (token accumulation, sandbox escapes, allowlist WARN dedup, pricing fallback ladder) + golden snapshot using `RecordedBackend` (zero new test deps; the existing recording pattern works because the backend interface is the boundary).

## Project Constraints (from CLAUDE.md)

These directives are extracted from `./CLAUDE.md` and are binding on every plan/task this phase produces:

| Directive | Source | Implication for Phase 8 |
|-----------|--------|-------------------------|
| Every non-trivial factual claim in generated Markdown must carry `<!-- ground: path:line-start-line-end -->` | `docagent/backends/agent_sdk.py:29-34` + `verify/citations.py` | The LiteLLM system prompt (already in spike at lines 27-38) replicates this directive. Don't drift the prompt text between backends — both must enforce identical grounding rules. |
| No outer ```` ```markdown ```` fence; no preamble like "I'll use the Skill tool…" | `docagent/artifacts/_cleaners.py:4-9, 24-40` | LiteLLM system prompt already says "Do not invent files, symbols, commands, or behavior you have not verified by reading the source." Add the no-fence/no-preamble line for parity with the SDK prompt. |
| Top-level artifacts (README/AGENTS.md/CLAUDE.md) must start with `# ` H1 | `docagent/artifacts/_cleaners.py:34-39` | Cleaner already handles this — the cleaner runs on backend output regardless of source backend, so no Phase 8 change. |
| Bump `PROMPT_VERSION` when prompts change | `docagent/artifacts/registry.py:25-31` | If the LiteLLM backend adds a backend-specific system-prompt fragment (it shouldn't per Decisions), bump nothing. Backend swap is NOT a prompt change. CONTEXT.md confirms: "Custom system prompts per provider — out of scope." |
| Ruff `line-length=100`, target `py311`, rules `E,F,I,B,UP,SIM,RUF` (E501 ignored); mypy strict | `pyproject.toml:60-71` | Spike file already complies (verified by hand-read). New `_litellm_pricing.py` + test files must match. `pyproject.toml` mypy override for `litellm.*` already added in spike — keep. |
| `model=None` records as `"sdk-default"` for fingerprint stability | Project memory + `pricing.py:32` | LiteLLM path always passes a concrete model (`gemini/...`, `openrouter/...`, etc.) — there is no "litellm default model" sentinel. CONTEXT.md confirms erroring when `--backend litellm` is passed without `--model`. |

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Backend architecture:**
- `AgentSDKBackend` remains the default. No regression on the validated Anthropic path. Preserves SDK prompt caching + sandbox.
- One new backend: `LiteLLMBackend`. Selected via `--backend litellm --model <litellm-model-string>`. No separate `OllamaBackend`, `GeminiBackend`, `OpenRouterBackend`.
- **Ollama is OUT of v1.** Spike on `ollama_chat/llama3.1:8b` measured 0 tool calls + 1 invented citation = 0% citation-emission rate. Deferred to v1.1 with a future-spike trigger on Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ / GLM-4.6+.

**Tool-loop strategy:**
- Hand-written loop on `litellm.completion(..., tools=[...])`. ~80 LOC. Already prototyped on `spike/phase-8-litellm` at `docagent/backends/litellm_backend.py`.
- NOT `experimental_mcp_client`.
- NOT the `AgenticLoop` callback infrastructure.

**Provider scope (v1):**
- In-scope: `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-pro`, `openrouter/<provider>/<model>`, `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-7`.
- Out: Ollama (any model), OpenAI direct (use OpenRouter), Bedrock/Vertex/Azure (work via LiteLLM but not on tested allowlist → WARN).

**Tested-model allowlist:**
- Module-private `_TESTED_MODELS: frozenset[str]` in `docagent/backends/litellm_backend.py`.
- Initial set: the six in-scope models above.
- Unknown model → ONE `[unsupported-model]` WARN per model name per process. Extend Phase 5's `_warned_models` primitive (don't duplicate it).
- Allowlist is data, not code: future Ollama add = one constant edit.

**Pricing integration:**
- SDK path: existing `docagent/pricing.py` table unchanged. Anthropic Sonnet + Opus rates stay hand-maintained.
- LiteLLM path: `litellm.completion_cost(response)`. Cache-discount pricing (Phase 5 v2) becomes free.
- `BudgetTracker` is provider-agnostic — already takes USD amounts. `_InstrumentedBackend` wrapper transparently wraps whichever backend is active.

**Token accumulation:**
- LiteLLM's `completion()` returns response with `.usage` per call — **attribute object, NOT a dict** (different shape from `claude-agent-sdk`). Fields: `prompt_tokens`, `completion_tokens`, `total_tokens`.
- Hand-written loop sums per-call across every turn (no final-message-only read trap).
- Regression test mirrors `tests/unit/test_backend_token_extraction.py`.

**Packaging:**
- LiteLLM is `docagent[multi]` extras. Default `pip install docagent` keeps small dep tree.
- `LiteLLMBackend.run()` ImportError → `BackendUnavailableError`.
- `pyproject.toml` mypy override for `litellm.*` already in place (spike commit `e945838`).

**CLI surface:**
- New flag: `--backend {agent_sdk,litellm}` on both `init` and `update`. Default: `agent_sdk`.
- `--model <model-string>` semantics extend by backend.

**Tool sandbox:**
- `LiteLLMBackend._safe_path` resolves Read/Glob/Grep args under `request.repo_root` and refuses escapes. Mirrors SDK ergonomics. Phase 8 adds tests for escape-refusal cases.

**Documentation deliverables:**
- New `docs/how-to/use-multi-provider-backends.md` — generated by Phase 6 `how_to_guides` artifact during Phase 8 execution.
- README.md adds "Multi-provider setup" subsection (auto-regenerated on first `docagent update` after Phase 8).
- AGENTS.md / CLAUDE.md unchanged.

### Claude's Discretion (open questions deferred from CONTEXT.md to planning)

CONTEXT.md leaves three planner choices open:
1. WARN channel for unsupported models — **stderr vs CLI summary footer.**
2. `--backend litellm` without `--model` — **error vs default to anthropic/claude-sonnet-4-6.**
3. `--backend litellm` interaction with `--max-cost` — cap should apply unchanged; confirm in plan.

See "Open Questions" section below for my resolutions.

### Deferred Ideas (OUT OF SCOPE for Phase 8)

- Ollama in any form for v1 (re-spike trigger on Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ / GLM-4.6+).
- Local-LLM endpoints other than Ollama (llama.cpp, vLLM, TGI) — covered by LiteLLM routing in theory; ship as documented gap.
- Custom system prompts per provider.
- Streaming output.
- Concurrent multi-provider runs in one invocation.
- Cache-discount pricing exposure in CLI summary (LiteLLM aggregates; we sum).
- Bedrock / Vertex / Azure tested-allowlist coverage.
- Per-provider prompt forks.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACKEND-01 (narrowed) | Multi-provider backends — Gemini, OpenRouter, Anthropic-direct via `--backend litellm --model <litellm-model-string>`; user supplies API keys via env vars; `AgentSDKBackend` remains default. **Ollama deferred to v1.1.** | Spike prototype `litellm_backend.py` covers the loop + sandbox + protocol shape. Empirically verified env vars: `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`. Dep-tree audit confirms no `claude-agent-sdk` collision (both co-install cleanly with `pydantic 2.13.4`, `httpx 0.28.1`). |
| BACKEND-02 | LiteLLM-delegated pricing via `litellm.completion_cost(response)` for LiteLLM path; existing Anthropic price table in `docagent/pricing.py` stays for SDK path. Unknown models → Opus-fallback WARN behavior (extends Phase 5's `_warned_models`). | Empirically verified `completion_cost()` signature + behavior on unknown models — see "Pitfall 1" below. Phase 5's `_warned_models` is at `docagent/pricing.py:42` and the dedup pattern at `pricing.py:55-59`. Plan must extend, not duplicate, that set. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Backend selection (`--backend` flag) | CLI | — | Typer Option, validated at CLI parse time. Wires the chosen backend into Orchestrator. |
| LLM tool-use loop driver | Backend (`LiteLLMBackend`) | — | Hand-written loop owns the turn-by-turn `completion()` → tool-result → `completion()` cycle. The orchestrator does NOT see individual turns; it sees one `GenerationResponse` per task. |
| Tool dispatch (Read/Glob/Grep) | Backend (sandboxed helpers) | — | Plain Python functions invoked by name from inside the backend; sandboxed to `request.repo_root` via `_safe_path`. No MCP server. |
| Token accumulation across turns | Backend | — | Sum per-turn `response.usage.prompt_tokens` + `.completion_tokens`. The orchestrator's `_InstrumentedBackend` sees only the aggregated `GenerationResponse`. |
| Per-call cost lookup | Pricing module (`_litellm_pricing.py`) | — | New shim file. Delegates to `litellm.completion_cost()` with fallback ladder. The SDK path keeps using `pricing.py:estimate_cost()` unchanged. |
| Cumulative cost + cap check | Orchestrator (`BudgetTracker`) | — | `BudgetTracker` is provider-agnostic; `_InstrumentedBackend` already wraps either backend transparently. The orchestrator's existing cap-check loop works unchanged. |
| Unsupported-model WARN dedup | Pricing module (`_warned_models` extended) | — | Reuse the existing `set[str]` and dedup pattern. Add a parallel set or reuse the same one with a key-prefix convention — see Pattern 2 below. |
| Path-sandbox enforcement | Backend (`_safe_path`) | — | Hard refusal of `..` escapes via `Path.relative_to()`. Mirrors SDK's `permission_mode="bypassPermissions"+cwd=request.repo_root` ergonomics. |

## Standard Stack

### Core (existing, unchanged)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude-agent-sdk` | `>=0.1` | Default `AgentSDKBackend` (Anthropic via local `claude` CLI). | Already shipped; CONTEXT.md locks no regression on this path. `[VERIFIED: pyproject.toml main branch]` |
| `pydantic` | `>=2.7` | Existing project pin. | Compatible with LiteLLM's `pydantic >=2.10` floor — `pyproject.toml` may need to bump to `pydantic>=2.10` to match the LiteLLM floor without forcing an env split. `[VERIFIED: empirical co-install yielded pydantic 2.13.4 with no conflict]` |

### New (Phase 8)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `litellm` | `>=1.50` | Multi-provider routing (Gemini / OpenRouter / Anthropic-direct via one API). | Already pinned in spike `pyproject.toml`. Current PyPI release `1.85.0` installs cleanly alongside `claude-agent-sdk==0.2.82`. `[VERIFIED: PyPI metadata + empirical co-install 2026-05-17]` |

**Installation (already on spike branch):**

```toml
[project.optional-dependencies]
multi = [
    "litellm>=1.50",
]
```

```bash
pip install -e ".[multi]"
```

**Version verification (empirical, 2026-05-17):**

```bash
$ /tmp/litellm-audit/bin/pip install litellm
Successfully installed litellm-1.85.0 ...

$ /tmp/litellm-audit/bin/python -c "import litellm; print(litellm.__version__)"
1.85.0
```

Total transitive deps in a `litellm + claude-agent-sdk` co-install: ~68 packages (audited in fresh venv). Direct LiteLLM pins captured in "Package Legitimacy Audit" below.

### Alternatives Considered (rejected per ADR-0001 + CONTEXT.md)

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LiteLLM (chosen) | Write `OllamaBackend` + `GeminiBackend` + `OpenRouterBackend` as peers | 3 backends + 3 price tables + 3 tool loops to maintain. Token-accumulation bug now lives in 3 places. **Rejected by ADR-0001 Option A.** |
| LiteLLM (chosen) | Adopt OpenRouter only | Fails BACKEND-01 — OpenRouter is cloud-only. **Rejected by ADR-0001 Option C.** |
| Hand-written tool loop (chosen) | `litellm.experimental_mcp_client` | Still flagged experimental in late-2025 docs; overkill for fixed Read/Glob/Grep surface. **Rejected by CONTEXT.md.** |
| Hand-written tool loop (chosen) | LiteLLM `AgenticLoop` callback hooks | Cleaner for non-MCP loops but adds LiteLLM-side indirection. ~80 LOC of hand-written code is cheaper to own. **Rejected by CONTEXT.md.** Documented as fallback if hand-written hits edge cases. |

**Fallback path documentation (for "rejected alternatives" block in plan):**

> `AgenticLoop` callback fallback: LiteLLM exposes `async_should_run_agentic_loop` + `async_build_agentic_loop_plan` hooks (https://docs.litellm.ai/docs/proxy/agentic_loop_hook). The callback delegates loop control to LiteLLM, eliminating the manual `for turn in range(max_turns)` pattern. We don't use this because (a) our tool surface is fixed and small, (b) the loop logic is already correct in the spike, (c) routing tool-result threading through async callbacks adds debugging surface area we don't need. If the hand-written loop later hits a hard-to-debug edge case (e.g., a provider that returns tool calls in a non-OpenAI shape), switching to `AgenticLoop` is a one-file change.

## Package Legitimacy Audit

Pre-existing slopcheck flag for `pyjsonc` already saved us in Phase 7. For Phase 8 the only new package is `litellm`:

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `litellm` | PyPI | 2+ years (released Sep 2023; commits daily) | ~10M+/month | https://github.com/BerriAI/litellm (>20k stars) | not run (CLI not installed in this environment) | **Approved** — `[CITED: github.com/BerriAI/litellm]` |

**slopcheck status:** The `slopcheck` CLI was not invocable in this research environment. Per the protocol, that downgrades the verification level — the planner should run `slopcheck install litellm` before the install step in Wave 1 as a defense-in-depth check. Both `litellm` and `claude-agent-sdk` are verified by:
1. **Official documentation** — https://docs.litellm.ai/ has been a stable, well-maintained docs site since 2023 `[CITED]`
2. **Empirical install** — verified locally in `/tmp/litellm-audit/` venv; the package imports cleanly and exposes the documented `completion()`, `completion_cost()`, and `BadRequestError` symbols `[VERIFIED: empirical 2026-05-17]`
3. **GitHub provenance** — BerriAI/litellm repo has >25k commits, >100 contributors, daily releases `[CITED: github.com/BerriAI/litellm]`

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

### Direct LiteLLM dep-tree pins (from empirical `pip install litellm` 2026-05-17)

These are the LiteLLM `requires_dist` pins relevant to the ADR's "dep-tree compatibility" invalidator:

| Package | LiteLLM 1.85.0 pin | Co-install with `claude-agent-sdk==0.2.82` | Conflict? |
|---------|--------------------|--------------------------------------------|-----------|
| `pydantic` | `<3.0.0,>=2.10.0` | claude-agent-sdk has no direct pin (uses MCP's `pydantic` transitively) | **No** — both install with pydantic 2.13.4. Note: DocAgent's `pyproject.toml` says `pydantic>=2.7`; the LiteLLM floor of `>=2.10.0` raises the effective floor. Document this. |
| `openai` | `<3.0.0,>=2.20.0` | claude-agent-sdk has no direct pin | **No** — openai 2.37.0 installed |
| `httpx` | `<1.0,>=0.28.0` | claude-agent-sdk has no direct pin | **No** — httpx 0.28.1 installed |
| `aiohttp` | `<4.0,>=3.10` | claude-agent-sdk has no direct pin | **No** — aiohttp 3.13.5 installed |
| `jinja2` | `<4.0,>=3.1.6` | not required by claude-agent-sdk | **No** |
| `jsonschema` | `<5.0,>=4.0.0` | not required by claude-agent-sdk | **No** |
| `click` | `<9.0,>=8.0.0` | DocAgent uses `typer` (which pulls click) | **No** — click 8.4.0 installed |

**Empirical co-install verdict (executed 2026-05-17):**

```bash
$ python3 -m venv /tmp/litellm-audit
$ /tmp/litellm-audit/bin/pip install litellm claude-agent-sdk
Successfully installed litellm-1.85.0 claude-agent-sdk-0.2.82 ...
```

No `ResolutionImpossible`, no warnings. **The ADR's "dep-tree compatibility" invalidator does NOT trigger.** `[VERIFIED: empirical 2026-05-17]`

**Side findings during the empirical install:**
- LiteLLM emits two `WARNING` log lines on import in absence of `botocore`:
  - `litellm: could not pre-load bedrock-runtime response stream shape`
  - `litellm: could not pre-load sagemaker-runtime response stream shape`
- These are cosmetic but noisy. Plan should either (a) silence via `logging.getLogger('LiteLLM').setLevel(logging.ERROR)` at backend import time, or (b) document them in the README's troubleshooting section. **Recommendation:** silence to ERROR at module load in `litellm_backend.py` to keep `docagent init` output clean.

## Runtime State Inventory

Phase 8 is **not** a rename/refactor/migration phase, but it does touch state across several layers. Reporting explicitly:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** The SQLite index (`.docagent/index.db`) is backend-independent — it stores symbols/mentions/artifacts/fingerprints. Backend choice does NOT enter any digest, fingerprint, or stored row. Verified: `_patch_digest()` at `docagent/core/orchestrator.py:25-30` hashes only `prompt_version + new_content`. | None. |
| Live service config | **None.** No external service registrations changed by Phase 8. | None. |
| OS-registered state | **None.** | None. |
| Secrets/env vars | New env vars consumed (NOT stored): `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`. These are READ by LiteLLM at call time. DocAgent never stores them. The README "Multi-provider setup" section must document each. | Document only — no code-side secret storage. |
| Build artifacts | `pyproject.toml` adds an `[multi]` extra (already on spike branch at line 47-52). Users who previously installed `pip install -e ".[dev]"` get nothing new automatically — they must explicitly run `pip install -e ".[multi]"` to opt into LiteLLM. | Document in README + how-to. No automatic migration. |

**Critical sub-finding (NOT immediately obvious):** Phase 5's per-model price-fingerprint stability used `model=None → "sdk-default"` (verified at `docagent/pricing.py:32`, project memory in STATE.md decisions list). For the LiteLLM path, `model` is ALWAYS a concrete string like `gemini/gemini-2.5-pro` — there is no "litellm default" sentinel. If the planner wants symmetry, they could fall back to `anthropic/claude-sonnet-4-6` as the LiteLLM "default" (one of CONTEXT.md's two open questions resolved below as "error" — no fingerprint stability concern arises if we error instead of default).

## Architecture Patterns

### System Architecture Diagram

```
docagent init / update --backend [agent_sdk|litellm] --model <m>
        │
        ▼
   docagent/cli.py
        │  selects backend per --backend flag (default: agent_sdk)
        │  validates --model presence for litellm path
        ▼
   AgentSDKBackend   OR   LiteLLMBackend       ◄── pluggable LLMBackend protocol
        │                       │
        │                       │  hand-written loop:
        │                       │   for turn in range(max_turns):
        │                       │     resp = litellm.completion(...)
        │                       │     accumulate resp.usage.prompt_tokens/completion_tokens
        │                       │     for tc in resp.choices[0].message.tool_calls:
        │                       │       result = _dispatch_tool(tc.function.name, args, repo_root)
        │                       │       messages.append({role:"tool", tool_call_id:tc.id, content:result})
        │                       │     if no tool_calls: break
        │                       ▼
        │                  _safe_path / _read / _glob / _grep   (sandboxed to repo_root)
        ▼                       │
   _InstrumentedBackend  ◄──────┘  (wrapper from orchestrator.py:50-78 — works for either)
        │
        ▼
   GenerationResponse → BudgetTracker.add(model, in, out, tool_calls)
                              │
                              ▼
                        Cost lookup:
                          - SDK path: docagent/pricing.py:estimate_cost() (existing table)
                          - LiteLLM path: _litellm_pricing.py:cost_for_response() (new shim)
                                           │  Three-tier fallback ladder:
                                           │   1. OpenRouter server-reported usage.cost (if present)
                                           │   2. litellm.completion_cost(response)
                                           │   3. WARN + 0.0 (model not on tested allowlist)
                                           ▼
                                       USD float → BudgetTracker
```

### Recommended Project Structure (delta from main)

```
docagent/
├── backends/
│   ├── base.py                  # unchanged
│   ├── agent_sdk.py             # unchanged (default backend)
│   ├── litellm_backend.py       # NEW (ported from spike branch with polish)
│   └── _litellm_pricing.py      # NEW (Wave 2)
├── pricing.py                   # unchanged Anthropic table
├── core/budget.py               # unchanged (already provider-agnostic)
├── core/orchestrator.py         # unchanged (already wraps via _InstrumentedBackend)
└── cli.py                       # MODIFIED — --backend flag added to init + update

tests/
├── unit/
│   ├── test_litellm_backend.py            # NEW (token accum, sandbox, tool loop)
│   ├── test_litellm_pricing.py            # NEW (fallback ladder, WARN dedup)
│   ├── test_backend_token_extraction.py   # unchanged
│   └── test_backend_preflight.py          # unchanged
└── golden/
    ├── _harness.py              # unchanged — RecordedBackend already supports the queue
    └── test_litellm_backend_snapshot.py   # NEW (Anthropic-direct snapshot only)

scripts/
└── measure_citation_rate.py     # MOVED from scripts/spike_phase8_citation_rate.py
                                  # (rename per CONTEXT.md — drop "spike" branch-name leak)
```

### Pattern 1: Hand-written tool loop (existing in spike — polish + test)

**What:** Synchronous loop that drives `litellm.completion(..., tools=_TOOLS_SPEC)`, dispatches tool calls via in-process Python, and threads results back into `messages` for the next turn.

**When to use:** Fixed, small tool surface (Read/Glob/Grep) where dynamic MCP discovery is overkill. CONTEXT.md locks this choice.

**Example (from spike `docagent/backends/litellm_backend.py:106-160`):**

```python
# Source: docagent/backends/litellm_backend.py:106-160 on spike/phase-8-litellm
for _turn in range(self.max_turns):
    response = completion(
        model=self.model,
        messages=messages,
        tools=_TOOLS_SPEC,
        tool_choice="auto",
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        input_tokens += getattr(usage, "prompt_tokens", 0) or 0
        output_tokens += getattr(usage, "completion_tokens", 0) or 0

    choice = response.choices[0]
    msg = choice.message
    tool_calls = getattr(msg, "tool_calls", None) or []

    if msg.content:
        chunks.append(msg.content)

    if not tool_calls:
        break

    messages.append({
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [tc.model_dump() for tc in tool_calls],
    })

    for tc in tool_calls:
        tool_calls_total += 1
        fn = tc.function
        try:
            args = json.loads(fn.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        result = _dispatch_tool(fn.name, args, repo_root)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })
```

**Spike-code gaps the planner needs to close (production-grade hardening):**

1. **No retry on transient API errors.** `litellm.completion()` can raise `litellm.APIError`, `litellm.RateLimitError`, `litellm.Timeout`. Spike code lets them bubble to the orchestrator's exception handler. Plan: add ONE bounded retry (e.g., `tenacity`-free, just a 1-shot `try/except`) on `litellm.RateLimitError` + `litellm.Timeout` with a fixed 2s sleep. Don't retry on `BadRequestError` (bad request stays bad). Document rationale.
2. **No max-turn-exhaustion handling.** If `max_turns=24` is hit without a tool-call-free terminating turn, the loop exits silently and emits whatever `chunks` accumulated. Plan: emit a WARN to the logger and add a `_log.warning` line. Mirror SDK's behavior (which also lets this slide).
3. **Empty assistant message + no tool calls = infinite-loop risk?** No — `if not tool_calls: break` terminates. Verified in spike code lines 137-138. Cover with a test.
4. **Tool call with malformed JSON args.** Spike falls back to `args = {}` at line 154-156. This is OK — the tool's `_safe_path` / regex compile / etc. will return an `error:` string from inside the tool, which the model sees as a tool-result and corrects in the next turn. Cover with a test.
5. **`tool_calls` is `None`.** Spike line 132: `tool_calls = getattr(msg, "tool_calls", None) or []`. Good — covers both attribute-missing and None-valued cases. No fix needed.
6. **Missing `response.usage`.** Spike line 122-126: `usage = getattr(response, "usage", None); if usage is not None: ...`. Safe.
7. **`response.choices` empty.** NOT defended. If the provider returns no choices (rare but possible on some error paths), `response.choices[0]` raises `IndexError`. Plan: add `if not response.choices: continue` or treat as terminal.
8. **`tc.model_dump()` could fail on a future LiteLLM rev that drops the method.** Verified empirically that `model_dump()` works on `ChatCompletionMessageToolCall` despite its `OpenAIObject` base, but the class is `OpenAIObject` not `BaseModel`. Pin a regression test that round-trips: `tc.model_dump()` returns dict with `id`/`type`/`function`/`function.name`/`function.arguments`. If LiteLLM ever swaps the base class without keeping the method, the test fails fast.
9. **`fn.name` could be `None`.** Tool-call schema theoretically allows it; in practice never happens on the providers we care about. `_dispatch_tool` already returns `f"unknown tool: {name}"` for any string that doesn't match Read/Glob/Grep — `None` matches the unknown-tool branch. Acceptable.

### Pattern 2: `_warned_models` extension (CONTEXT.md locked — extend, don't duplicate)

Phase 5 added `_warned_models: set[str]` at `docagent/pricing.py:42` for unknown-model WARN dedup. The Phase 8 planner has two options for extension:

**Option A (recommended) — Two separate sets, both module-private:**

```python
# docagent/backends/_litellm_pricing.py
_warned_pricing_models: set[str] = set()    # for "no completion_cost mapping" warnings
_warned_allowlist_models: set[str] = set()  # for "[unsupported-model]" allowlist warnings
```

**Option B — Reuse `docagent.pricing._warned_models` with a key prefix:**

```python
_warned_models.add(f"pricing:{model}")
_warned_models.add(f"allowlist:{model}")
```

**Recommendation: Option A.** Two sets, two semantic categories, no key encoding to remember. Phase 5's existing `_warned_models` stays untouched (Anthropic table only). The new sets live in `_litellm_pricing.py` (private — leading underscore). Tests monkeypatch them to a fresh `set()` per test, same as Phase 5's pattern (see `docagent/pricing.py:40` comment).

**Example:**

```python
# docagent/backends/_litellm_pricing.py
from docagent._logging import get_logger
_log = get_logger("litellm_pricing")
_warned_pricing_models: set[str] = set()
_warned_allowlist_models: set[str] = set()

def cost_for_response(model: str, response) -> float:
    # Tier 1: OpenRouter server-reported cost
    if model.startswith("openrouter/"):
        server_cost = _extract_openrouter_cost(response)
        if server_cost is not None:
            return server_cost
    # Tier 2: litellm.completion_cost
    try:
        import litellm
        return litellm.completion_cost(completion_response=response)
    except Exception as exc:
        if model not in _warned_pricing_models:
            _log.warning(
                "litellm could not price model %r (%s); recording 0.0 cost. "
                "Token counts still accurate.",
                model, exc.__class__.__name__,
            )
            _warned_pricing_models.add(model)
        return 0.0
```

### Pattern 3: Tested-model allowlist gate (CONTEXT.md locked)

```python
# docagent/backends/litellm_backend.py
_TESTED_MODELS: frozenset[str] = frozenset({
    "gemini/gemini-2.5-pro",
    "gemini/gemini-2.5-flash",
    "openrouter/anthropic/claude-sonnet-4-6",
    "openrouter/anthropic/claude-opus-4-7",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-opus-4-7",
})
```

Gate fires at the top of `LiteLLMBackend.run()`, before any API call:

```python
def run(self, request: GenerationRequest) -> GenerationResponse:
    if self.model not in _TESTED_MODELS:
        _warn_unsupported_model(self.model)  # dedups via _warned_allowlist_models
    # ... rest of run()
```

`_warn_unsupported_model` emits a one-time stderr WARN with the `[unsupported-model]` tag — see "Open Questions" resolution below.

### Anti-Patterns to Avoid

- **DON'T duplicate the Phase 5 `_warned_models` set in `litellm_backend.py`.** Use a fresh module-private set in the new pricing shim. Phase 5's set is for `pricing.estimate_cost()` only (Anthropic table). Mixing semantics = future bug.
- **DON'T import `litellm` at module top of `litellm_backend.py`.** Spike already does the lazy `import litellm` inside `run()` (lines 109-114) — this is correct. Importing at top breaks the `pip install docagent` (no `[multi]` extras) install path: importing the module-level symbols (e.g., for type-checking) would trigger the missing import error.
- **DON'T pass `model=None` to `LiteLLMBackend`.** The SDK path has a `model=None → "sdk-default"` sentinel for fingerprint stability. The LiteLLM path requires an explicit model string. Open question resolution below: error at CLI parse time when `--backend litellm` lacks `--model`.
- **DON'T call `litellm.completion_cost(response)` without wrapping in try/except.** Verified empirically: it raises bare `Exception` on unmapped models like `openrouter/anthropic/claude-sonnet-4-5`. The fallback ladder MUST catch broad `Exception` for the OpenRouter routes, not just BadRequestError.
- **DON'T trust LiteLLM's documented exception hierarchy without empirical check.** The docs claim "Raises exception if model not in cost map" (`completion_cost` docstring) — the actual exception type is `litellm.BadRequestError` for some failure modes and bare `Exception` for others. Catch broad.
- **DON'T put backend selection in the orchestrator.** Backend selection happens at the CLI layer; the orchestrator receives an already-constructed backend. Spike code already follows this pattern (orchestrator.py:96 takes `backend: LLMBackend`).
- **DON'T re-derive the system prompt per backend.** CONTEXT.md locks "single prompt for all providers." Spike's `_SYSTEM_PROMPT` (lines 27-38) IS the same text as `AgentSDKBackend.system_prompt` (agent_sdk.py:43-52). Plan a small refactor: extract the system prompt to `docagent/backends/_shared.py` so a single edit propagates to both backends.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-provider routing | Write `OllamaBackend` / `GeminiBackend` / `OpenRouterBackend` separately | `litellm.completion(model=...)` | LiteLLM handles 100+ providers via one API + maintains `model_prices_and_context_window.json` upstream (updated multiple times/week). Three custom backends = three places the token-accumulation bug lives. |
| Cost lookup per provider | Hand-maintain a price table for Gemini/OpenRouter/Anthropic-direct | `litellm.completion_cost(response)` | Upstream price table is auto-refreshed. DocAgent's existing `pricing.py` table is kept for the SDK path only because the SDK doesn't speak LiteLLM. |
| Tool-use schema per provider | Write per-provider JSON schemas for Read/Glob/Grep | OpenAI-shape `_TOOLS_SPEC` passed via `tools=` | LiteLLM normalizes tool-use schema across providers. Verified: same `tools=[...]` array works for Anthropic, OpenAI, Gemini, OpenRouter. |
| HTTP retry logic on transient errors | Build a retry wrapper around `completion()` | LiteLLM's built-in `num_retries` parameter (default 0; pass via kwarg) | Empirically tested in the LiteLLM ecosystem. Don't write retry logic; pass `num_retries=1` to `completion()` and let LiteLLM handle backoff. |
| Streaming response handling | Build a streaming aggregator | Don't stream | CONTEXT.md locks streaming as out of scope. Use the non-streaming `completion()` path only. |
| Path-sandbox enforcement | Naive `os.path.join(root, rel)` | `Path.resolve().relative_to(root)` pattern in `_safe_path` | Already in spike (`litellm_backend.py:185-192`). The `relative_to()` check catches `..` escapes that naive concat misses. |

**Key insight:** ADR-0001 already made the "don't build N backends" call. The discipline now is to resist re-introducing per-provider branching inside `LiteLLMBackend` — the whole point of choosing LiteLLM is that the loop, sandbox, and pricing are all provider-agnostic.

## Common Pitfalls

### Pitfall 1: `litellm.completion_cost()` raises on unmapped models — and the exception type varies

**What goes wrong:** The shim that delegates pricing to LiteLLM crashes the run when a user passes a model LiteLLM hasn't mapped in `model_prices_and_context_window.json`.

**Empirical evidence (executed 2026-05-17 against `litellm==1.85.0`):**

| Input | Output |
|-------|--------|
| `completion_cost(model="nonexistent/totally-fake-model", prompt="hi", completion="ok")` | Raises `litellm.BadRequestError`: "LLM Provider NOT provided. Pass in the LLM provider..." |
| `completion_cost(model="anthropic/claude-sonnet-4-6", prompt="hi", completion="ok")` | Returns `1.8e-05` (works even though `4-6` is newer than what's in the table — LiteLLM does fuzzy version matching for Anthropic) |
| `completion_cost(model="gemini/gemini-2.5-pro", prompt="hi"*100, completion="ok")` | Returns `0.000135` |
| `completion_cost(model="openrouter/anthropic/claude-sonnet-4-5", prompt="hi", completion="ok")` | Raises bare `Exception`: "This model isn't mapped yet. model=openrouter/anthropic/claude-sonnet-4-5, custom_llm_provider=openrouter. Add it here..." |
| `completion_cost(completion_response=ModelResponse(...))` for Anthropic with Usage(in=100,out=20) | Returns `0.0006` (the canonical "pass the response" path works) |

**Why it happens:** LiteLLM's `model_prices_and_context_window.json` is upstream-maintained and lags. Some OpenRouter routes (especially `openrouter/anthropic/*`) are not pre-mapped; the upstream tracks the raw provider IDs first.

**How to avoid:**
1. Catch BROAD `Exception` in the shim — not `BadRequestError`, not `NotFoundError`, not `litellm.exceptions.*`. The actual class varies.
2. On exception: log WARN once per model name (`_warned_pricing_models` dedup), return `0.0`. Token counts are still accurate; only cost is missing. The CLI's summary footer will show `cost=$0.000` for unmapped runs — document this in the README troubleshooting section.
3. Prefer `completion_cost(completion_response=response)` over `completion_cost(model=..., prompt=..., completion=...)`. The response-object path infers the model from `response.model` AND has access to the full `usage` object including cache breakdowns. The spike's pricing-shim should use this form.

**Warning signs:** A `docagent init --backend litellm --model openrouter/anthropic/claude-sonnet-4-6` run shows `cost=$0.000` in the summary footer even though token counts are non-zero. That's the WARN-and-zero fallback firing. Either the model is unmapped upstream (file an issue + PR to LiteLLM) or use the OpenRouter server-cost path (Tier 1).

### Pitfall 2: OpenRouter `usage.cost` is authoritative but requires opt-in

**What goes wrong:** Even when `litellm.completion_cost()` returns a number for an OpenRouter route, it can disagree with OpenRouter's actual billed cost (OpenRouter applies routing fees, BYOK discounts, prompt-cache discounts that LiteLLM's static table doesn't model).

**Why it happens:** OpenRouter's API supports `extra_body={"usage": {"include": true}}` (or `usage={"include": true}` on top-level) which returns the actual server-side computed cost in `response.usage.cost`. LiteLLM does NOT auto-add this opt-in flag — the caller must pass it. There's a known LiteLLM bug for streaming where even when the flag is passed, the streaming aggregator drops the `cost` field (BerriAI/litellm#16021). DocAgent doesn't stream, so the streaming bug doesn't bite us — but we still need to opt in.

**How to avoid:** In the LiteLLM `completion()` call inside `LiteLLMBackend.run()`, when `self.model.startswith("openrouter/")`, pass `extra_body={"usage": {"include": True}}` (or `usage={"include": True}` — both forms work per LiteLLM docs). In `_litellm_pricing.py:cost_for_response()`, check the response shape:

```python
def _extract_openrouter_cost(response) -> float | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    # OpenRouter populates .cost as a float USD when {"usage":{"include":true}} was sent.
    cost = getattr(usage, "cost", None)
    if cost is None:
        return None
    try:
        return float(cost)
    except (TypeError, ValueError):
        return None
```

If present, return it (skip `completion_cost()`). If absent, fall through to the LiteLLM-computed estimate. Empirical validation will require a live OpenRouter call — the planner should add this as a manual smoke step (or a recorded VCR-style fixture if doing recorded HTTP testing).

**Warning signs:** OpenRouter billing dashboard disagrees with DocAgent's `cost=` summary by more than 10% for the same prompt/completion pair. That's a sign the opt-in flag isn't propagating or the response shape changed upstream.

### Pitfall 3: `response.usage` is an attribute object, NOT a dict

**What goes wrong:** A test mock or fake-response harness builds `usage={"prompt_tokens": 100, ...}` as a dict. The backend's `getattr(usage, "prompt_tokens", 0)` returns `0` because dict attribute access yields the default. Tokens silently zero out.

**Why it happens:** LiteLLM's `Usage` class is an `OpenAIObject` (Pydantic-ish with `model_dump()`) NOT a plain dict. The shape difference from `claude-agent-sdk`'s `AssistantMessage.usage: dict[str, Any] | None` is exactly the "different shape from claude-agent-sdk" CONTEXT.md flags.

**How to avoid:**
1. In tests, construct `Usage` instances via `litellm.types.utils.Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120)`, NOT raw dicts. This is the SAME pattern the `agent_sdk` tests use — they construct `_FakeAssistantMessage` dataclasses with attribute access, not raw dicts.
2. Mirror `tests/unit/test_backend_token_extraction.py` exactly. The CONTEXT.md "regression test mirrors `test_backend_token_extraction.py`" line is precise — use the same fixture pattern (one fake `_query` async generator, parameterized turns list, asserts on `resp.input_tokens` / `resp.output_tokens` accumulation).
3. Add a test where `response.usage = None` and assert tokens stay 0. The spike code has `if usage is not None:` defense (line 122) — pin it with a test.

**Warning signs:** A test passes locally but the production token count is wildly off, or vice versa. Always test with attribute-access mocks.

### Pitfall 4: `tc.model_dump()` works today but the contract is fragile

**What goes wrong:** A future LiteLLM release refactors `ChatCompletionMessageToolCall` to remove `model_dump()` (it's not a Pydantic BaseModel — it inherits from `OpenAIObject`). The tool-call thread-back at spike line 149 (`[tc.model_dump() for tc in tool_calls]`) starts raising `AttributeError`. The agentic loop terminates after one turn with garbage state.

**Why it happens:** Per Pitfall 1's empirical check, `ChatCompletionMessageToolCall` has `model_dump`, `dict`, AND `to_dict` methods today (LiteLLM 1.85.0). The class technically inherits from `OpenAIObject`, which appears to forward to Pydantic-style methods. There's no formal contract — the method could disappear in a refactor.

**How to avoid:**
1. Add a regression test that:
   ```python
   from litellm.types.utils import ChatCompletionMessageToolCall, Function
   tc = ChatCompletionMessageToolCall(id="x", type="function",
                                       function=Function(name="Read", arguments='{"path":"a"}'))
   d = tc.model_dump()
   assert d["id"] == "x"
   assert d["function"]["name"] == "Read"
   assert d["function"]["arguments"] == '{"path":"a"}'
   ```
   Empirically verified output (executed 2026-05-17): `{'function': {'arguments': '{"path":"x"}', 'name': 'Read'}, 'id': 'call_1', 'type': 'function'}`.
2. Defensive alternative: write a tiny `_dump_tool_call(tc)` helper that tries `model_dump()`, falls back to manual dict construction from `tc.id`, `tc.type`, `tc.function.name`, `tc.function.arguments`. Two-line function; protects against the contract drifting.

**Warning signs:** `pytest tests/unit/test_litellm_backend.py` fails with `AttributeError: 'ChatCompletionMessageToolCall' object has no attribute 'model_dump'` after a `pip install -U litellm`. Pin the LiteLLM version range tightly (`>=1.50,<2.0` is fine) and run the regression test in CI.

### Pitfall 5: `pyproject.toml` `pydantic>=2.7` is below LiteLLM's `>=2.10` floor

**What goes wrong:** A user with `pydantic==2.8` in their environment (DocAgent's documented minimum) installs `docagent[multi]`. pip resolves to `pydantic==2.10+` to satisfy LiteLLM. Existing DocAgent code that runs against `pydantic 2.7` semantics may hit a breaking change.

**Why it happens:** DocAgent's `pyproject.toml` line declares `pydantic>=2.7`. LiteLLM 1.85.0 requires `pydantic >=2.10.0,<3.0.0`. The pip resolver picks the intersection, but the README still claims `>=2.7` works.

**How to avoid:**
1. In Wave 1 of the plan, bump DocAgent's `pydantic` pin to `>=2.10` in `pyproject.toml` (line ~37). This aligns with LiteLLM's floor without forcing an environment split. Pydantic 2.10 is over a year old at this point — virtually nobody is on 2.7-2.9 anymore.
2. Verify in the test suite that nothing in `docagent/` uses Pydantic 2.7-2.9-only behavior. Quick grep for `from pydantic import` reveals usage in `docagent/artifacts/registry.py` — verify those imports work on 2.10.
3. Document in the README "Multi-provider setup" section that `docagent[multi]` requires `pydantic>=2.10` (which will be the new floor for everyone after the pin bump).

**Warning signs:** A `pip install -e ".[multi]"` succeeds but `docagent init` raises a Pydantic-internals error. The pin bump prevents the version split from happening.

### Pitfall 6: `BedrockRuntime` / `SageMakerRuntime` pre-load warnings spam stderr

**What goes wrong:** Every `docagent init --backend litellm` run prints two `WARNING` lines to stderr at LiteLLM import time:

```
litellm: could not pre-load bedrock-runtime response stream shape — Bedrock event-stream decoding will be unavailable. Error: No module named 'botocore'
litellm: could not pre-load sagemaker-runtime response stream shape — SageMaker event-stream decoding will be unavailable. Error: No module named 'botocore'
```

**Why it happens:** LiteLLM tries to pre-load AWS SDK shapes for streaming support. The `[multi]` extras intentionally don't pull `botocore` (Bedrock isn't in the tested allowlist), so these warnings always fire.

**How to avoid:** In `LiteLLMBackend.run()` before the `import litellm` line, silence the LiteLLM logger:

```python
import logging
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
import litellm
```

This suppresses INFO+WARNING from LiteLLM but lets ERROR through (so a real LiteLLM error like rate-limiting still surfaces). Alternative: catch the warnings with `warnings.catch_warnings()` — less robust because these are `logging.WARNING`, not Python `warnings.warn`.

**Warning signs:** Users complain `docagent init` output is noisy. The fix is module-local and tested by capturing stderr in a unit test.

## Code Examples

### Example 1: Reading `litellm.completion_cost()` via response object (preferred form)

```python
# Source: empirical execution against litellm==1.85.0 on 2026-05-17
import litellm
from litellm.types.utils import ModelResponse, Choices, Message, Usage

# Build a fake response (what the backend will pass in production)
response = ModelResponse(
    id="x", model="anthropic/claude-sonnet-4-5", object="chat.completion",
    choices=[Choices(index=0, message=Message(content="hi", role="assistant"), finish_reason="stop")],
    usage=Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
)
cost = litellm.completion_cost(completion_response=response)
# returns: 0.0006 (USD)
```

### Example 2: Test pattern (mirror of `test_backend_token_extraction.py`)

```python
# tests/unit/test_litellm_backend.py — new file, Wave 4
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from docagent.backends.base import GenerationRequest


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _FakeFunction:
    name: str
    arguments: str


@dataclass
class _FakeToolCall:
    id: str
    type: str
    function: _FakeFunction
    def model_dump(self) -> dict:
        return {"id": self.id, "type": self.type,
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


@dataclass
class _FakeMessage:
    content: str | None
    tool_calls: list[Any] = None


@dataclass
class _FakeChoice:
    message: _FakeMessage
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    usage: _FakeUsage | None = None


def _install_fake_litellm(monkeypatch, turns: list[tuple[_FakeResponse]]) -> None:
    """Each entry in `turns` is one response that completion() returns."""
    iterator: Iterator[_FakeResponse] = iter(turns)

    def _completion(**kwargs: Any) -> _FakeResponse:
        return next(iterator)

    fake = types.ModuleType("litellm")
    fake.completion = _completion
    fake.drop_params = True
    monkeypatch.setitem(sys.modules, "litellm", fake)
```

### Example 3: Pricing shim with three-tier fallback

```python
# docagent/backends/_litellm_pricing.py — new file, Wave 2
from __future__ import annotations
from typing import Any
from docagent._logging import get_logger

_log = get_logger("litellm_pricing")
_warned_pricing_models: set[str] = set()


def cost_for_response(model: str, response: Any) -> float:
    """Compute USD cost for one LiteLLM completion response.

    Three-tier fallback:
    1. OpenRouter server-reported `usage.cost` (if the call passed
       `extra_body={"usage":{"include":true}}` and the field is present).
    2. `litellm.completion_cost(completion_response=response)`.
    3. WARN once + 0.0 (token counts remain accurate).
    """
    # Tier 1
    if model.startswith("openrouter/"):
        server_cost = _openrouter_server_cost(response)
        if server_cost is not None:
            return server_cost
    # Tier 2
    try:
        import litellm
        return float(litellm.completion_cost(completion_response=response))
    except Exception as exc:
        if model not in _warned_pricing_models:
            _log.warning(
                "litellm could not price model %r (%s); recording $0.00 for this call. "
                "Token counts unaffected. See README troubleshooting for details.",
                model, exc.__class__.__name__,
            )
            _warned_pricing_models.add(model)
        return 0.0


def _openrouter_server_cost(response: Any) -> float | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    cost = getattr(usage, "cost", None)
    if cost is None:
        return None
    try:
        return float(cost)
    except (TypeError, ValueError):
        return None
```

### Example 4: README/how-to drift handling

`docagent/prompts/readme.py:7-55` is the existing README prompt template. The prompt is structurally agnostic about CLI flags — it tells the LLM to "Read the most important source entry points — CLI entry, package `__init__.py`, ..." (line 16-17). The LLM will Read `docagent/cli.py` and discover the new `--backend` and `--model` flags as part of normal exploration.

**Verdict: no PROMPT_VERSION bump required.** The prompt template itself doesn't mention specific flags; it asks the model to discover and document the CLI. Adding two new flags is an organic discovery, not a prompt-template change.

**However:** the planner should add a one-line hint inside the new `docs/how-to/use-multi-provider-backends.md` topic-discovery prompt (in `docagent/prompts/how_to_guides.py`) — but ONLY if topic discovery would otherwise miss the multi-provider topic. Phase 6's `how_to_guides` artifact discovers topics from README + api_reference, so the multi-provider topic will surface naturally on first run after Phase 8 lands (which will have updated README + new `_litellm_pricing.py` + new test files in the discovery corpus). **Verdict: no prompt change needed.** Cover in plan as a verification step: after Phase 8 runs, confirm `docs/how-to/use-multi-provider-backends.md` exists.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-maintain a price table per provider | `litellm.completion_cost(response)` | Phase 8 (LiteLLM path only) | Eliminates quarterly Anthropic-price-refresh obligation for non-Anthropic providers. Anthropic SDK path keeps the hand table for prompt-caching reasons. |
| `experimental_mcp_client` for tool loops | Hand-written `completion(..., tools=[...])` loop | Phase 8 | MCP plumbing is overkill for fixed Read/Glob/Grep. CONTEXT.md locked. |
| `final_message.usage` token read (Phase 1-4 bug, fixed `63e69fe`) | Per-turn `getattr(response.usage, "prompt_tokens", 0)` summation | Phase 5 (SDK) + Phase 8 (LiteLLM) | Multi-turn token accounting correct on both backends. |
| Single-tier price lookup | Three-tier fallback ladder (OpenRouter server-cost → `completion_cost()` → WARN+0) | Phase 8 | OpenRouter authoritative cost when available; graceful degradation on unmapped models. |

**Deprecated/outdated:**
- `experimental_mcp_client` — still works but flagged experimental in late-2025 LiteLLM docs. Avoid.
- Streaming response handling — works but out of scope for v1 per CONTEXT.md.
- `completion_cost(model=..., prompt=..., completion=...)` form — works but the response-object form is preferred (gets cache breakdowns + `response.model` provenance).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OpenRouter `usage.cost` field is present when `extra_body={"usage":{"include":true}}` is passed in non-streaming mode | Pitfall 2 + Pricing shim | Tier 1 pricing fallback always misses, all OpenRouter cost goes through Tier 2 (`completion_cost`). Token counts unaffected; cost might disagree with OpenRouter dashboard. The planner should test with a real OpenRouter call before relying on this in production. `[CITED: docs.litellm.ai/docs/providers/openrouter + BerriAI/litellm#13653]` |
| A2 | `litellm` 1.85.0 will install cleanly on Python 3.11+3.12 in CI | Standard Stack | If LiteLLM's transitive deps conflict with another DocAgent dep we haven't seen, the `tests.yml` workflow breaks. Mitigation: empirical install in fresh venv passed today; CI runs the same pip resolver. `[VERIFIED: empirical 2026-05-17]` |
| A3 | `ChatCompletionMessageToolCall.model_dump()` remains stable across LiteLLM 1.x | Pitfall 4 | Future LiteLLM minor release drops `model_dump()` → spike code line 149 breaks. Mitigation: pin a regression test + use a defensive helper. `[VERIFIED: empirical 2026-05-17 on litellm==1.85.0]` |
| A4 | Bumping `pydantic>=2.7 → >=2.10` in `pyproject.toml` doesn't break existing DocAgent code | Pitfall 5 | A Pydantic 2.10 deprecation hits the artifacts/registry layer. Mitigation: run full test suite after the bump in Wave 1. `[ASSUMED]` — pydantic 2.7 → 2.10 changelog scan not performed in this research session. |
| A5 | LiteLLM's logger silencing via `logging.getLogger("LiteLLM").setLevel(logging.ERROR)` survives across LiteLLM versions | Pitfall 6 | LiteLLM renames the logger → warnings re-emerge. Cosmetic only. `[ASSUMED]` |
| A6 | The Phase 6 `how_to_guides` artifact will auto-discover the multi-provider topic from README + new code without prompt changes | Code Example 4 + Documentation | Topic discovery misses it; `docs/how-to/use-multi-provider-backends.md` is not generated. Mitigation: planner adds a verification step. `[ASSUMED]` |
| A7 | OpenRouter routing works identically to direct Anthropic for tool-use shape | OpenRouter section in CONTEXT.md | A tool-call from `openrouter/anthropic/...` has a different `tool_calls[]` shape vs `anthropic/...` direct → the loop misreads. Mitigation: snapshot test runs against the direct-Anthropic path first; OpenRouter path needs manual smoke. `[CITED: docs.litellm.ai/docs/providers/gemini confirms OpenAI-shape across providers]` but not first-hand verified for OpenRouter tool-use. |
| A8 | `gemini/gemini-2.5-pro` ranks "≥80% citation-emission rate on tinylib_ts" per CONTEXT.md's tested-model allowlist | Tested-model allowlist | The allowlist starts with an unmeasured assumption. The spike only measured `ollama_chat/llama3.1:8b`. Plan should include a Wave (or document as a follow-up smoke check) that runs `scripts/measure_citation_rate.py --model gemini/gemini-2.5-pro` against tinylib_ts and confirms ≥80% rate before declaring the allowlist accurate. `[ASSUMED]` |
| A9 | Bedrock/SageMaker preload warnings are cosmetic (not signaling a real config error) | Pitfall 6 | The warning indicates a missing config that LiteLLM will hit at runtime. Mitigation: silenced via logger; if a real Bedrock call breaks downstream, the BadRequestError will surface. We don't support Bedrock in v1. `[CITED: BerriAI/litellm common_utils.py error message]` |

## Open Questions

CONTEXT.md leaves three planner choices unresolved. My recommendations follow.

### Question 1: WARN channel for unsupported models — stderr vs CLI summary footer?

**What we know:**
- Phase 5's `_warned_models` uses `_log.warning(...)` via `docagent._logging.get_logger("pricing")` (`pricing.py:56`). That writes to stderr by default with the standard `setup_logging` config (`docagent/cli.py:124`).
- CONTEXT.md preliminarily recommends stderr; matches Phase 5's pattern.

**What's unclear:** Whether the CLI summary footer should also surface a count of unsupported-model warnings (e.g., "2 unsupported-model warnings — see logs above"). Phase 5 doesn't.

**Recommendation (confirms CONTEXT.md):** **stderr only.** Reasons:
1. Symmetry with Phase 5's pricing WARN pattern — users learn the convention once.
2. The summary footer is for cost/tokens/wall-time — adding warning-count noise complicates parsing.
3. The WARN is per-process, per-model deduped. In a typical run there's at most ONE WARN line. It won't get lost in stderr.
4. CI workflows (`verify.yml` self-host) already capture stderr; the warning will appear in CI logs without footer changes.

### Question 2: `--backend litellm` without `--model` — error vs default to `anthropic/claude-sonnet-4-6`?

**What we know:**
- CONTEXT.md preliminarily recommends erroring.
- The SDK backend supports `model=None → "sdk-default"` sentinel for the Claude Agent SDK. The SDK auto-resolves to its current default.
- LiteLLM has no equivalent — every `completion(model=...)` call needs a concrete string.

**What's unclear:** Whether erroring blocks "happy path" usage for someone who just wants to try LiteLLM with their `ANTHROPIC_API_KEY`.

**Recommendation (confirms CONTEXT.md):** **Error with a helpful hint.** Reasons:
1. The "default that just works" path is `--backend agent_sdk` (the actual default). A user choosing `--backend litellm` is explicitly opting OUT of that default — they should specify which provider.
2. Silent default to `anthropic/claude-sonnet-4-6` invites surprise bills. The user opting into LiteLLM may want Gemini's cheaper pricing or OpenRouter's BYOK setup; defaulting to Anthropic could send them to a more expensive provider.
3. The error message can be helpful:
   ```
   Error: --backend litellm requires --model.
   Try: --model gemini/gemini-2.5-pro    (set GEMINI_API_KEY)
        --model openrouter/anthropic/claude-sonnet-4-6   (set OPENROUTER_API_KEY)
        --model anthropic/claude-sonnet-4-6  (set ANTHROPIC_API_KEY)
   Or omit --backend to use the default (Claude Agent SDK).
   ```
4. CLI consistency: Typer's standard pattern is "required when X" via a `callback=` validator. Exit code 2 (parameter validation) is the right code.

### Question 3: `--backend litellm` interaction with `--max-cost`?

**What we know:**
- CONTEXT.md states "Cap should apply unchanged; LiteLLM-reported per-call costs flow into the same `BudgetTracker`. Confirm in plan."
- The orchestrator's existing `BudgetTracker.would_exceed()` check at `orchestrator.py:141` is provider-agnostic — it reads `tracker.cumulative_cost()` regardless of backend.
- The cap-check is POST-FACT, BETWEEN-ARTIFACTS — one artifact may push past the cap before the next iteration's check fires. This is Phase 5's documented behavior, unchanged.

**Recommendation (confirms CONTEXT.md):** **Yes, the cap applies unchanged — no Phase 8 work needed.** Just verify in a unit test:
1. Wrap `LiteLLMBackend` in `_InstrumentedBackend`.
2. Run a synthetic `Orchestrator.run()` with `max_cost=0.001` and a backend that returns 100k tokens (cost > $0.05 with any reasonable model).
3. Assert `tracker.aborted == True` after the first artifact.
4. Assert subsequent artifacts are NOT processed.

The existing Phase 5 test `tests/unit/test_orchestrator_budget.py` (if it exists — confirm in Wave 1) probably already has this assertion against `RecordedBackend`; just add a parallel test against a fake `LiteLLMBackend`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `litellm` Python package | `LiteLLMBackend.run()` (lazy import) | ✓ (when `pip install -e ".[multi]"` run) | `>=1.50` (1.85.0 latest) | `BackendUnavailableError` with install hint |
| `claude-agent-sdk` Python package | `AgentSDKBackend.run()` | ✓ | `>=0.1` (0.2.82 latest) | unchanged |
| `claude` CLI on PATH | `AgentSDKBackend._preflight()` | depends on user | n/a | `BackendUnavailableError` (existing behavior) |
| `GEMINI_API_KEY` env var | `LiteLLMBackend` with `gemini/*` model | depends on user | n/a | LiteLLM's `AuthenticationError` propagates from `completion()` — bubbles to orchestrator error path |
| `OPENROUTER_API_KEY` env var | `LiteLLMBackend` with `openrouter/*` model | depends on user | n/a | same |
| `ANTHROPIC_API_KEY` env var | `LiteLLMBackend` with `anthropic/*` model | depends on user | n/a | same |
| Python `>=3.11` | DocAgent base | ✓ | 3.11+3.12 | n/a (already pinned) |

**Missing dependencies with no fallback:** none — the `[multi]` extras gating is the explicit fallback for missing `litellm`.

**Missing dependencies with fallback:** API key env vars — surfaced as runtime `AuthenticationError` from LiteLLM. The plan should ensure the error is wrapped clearly:

```python
# In LiteLLMBackend.run(), wrap the first completion() call
try:
    response = completion(model=self.model, messages=messages, tools=_TOOLS_SPEC, tool_choice="auto")
except litellm.AuthenticationError as exc:
    raise BackendUnavailableError(
        f"LiteLLM authentication failed for model {self.model!r}. "
        f"Ensure the appropriate API key env var is set (GEMINI_API_KEY, "
        f"OPENROUTER_API_KEY, or ANTHROPIC_API_KEY)."
    ) from exc
```

This isn't in the spike code. Add to Wave 1 polish.

## Validation Architecture

The `workflow.nyquist_validation` key is absent from `.planning/config.json`; per the contract, that means enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest>=8.0` |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` — verify via `grep "tool.pytest" pyproject.toml`) |
| Quick run command | `pytest tests/unit/test_litellm_backend.py tests/unit/test_litellm_pricing.py -x` |
| Full suite command | `pytest` (currently 385 tests; Phase 8 should land at ~410-420) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACKEND-01 | `LiteLLMBackend` implements `LLMBackend` protocol | unit | `pytest tests/unit/test_litellm_backend.py::test_protocol_conformance -x` | ❌ Wave 0 |
| BACKEND-01 | Hand-written loop drives multi-turn tool use correctly | unit | `pytest tests/unit/test_litellm_backend.py::test_multi_turn_loop -x` | ❌ Wave 0 |
| BACKEND-01 | Token accumulation across turns (`prompt_tokens` + `completion_tokens` per turn summed) | unit | `pytest tests/unit/test_litellm_backend.py::test_token_accumulation -x` | ❌ Wave 0 |
| BACKEND-01 | `_safe_path` refuses `..` escapes | unit | `pytest tests/unit/test_litellm_backend.py::test_sandbox_refuses_escape -x` | ❌ Wave 0 |
| BACKEND-01 | `_safe_path` refuses absolute paths outside repo_root | unit | `pytest tests/unit/test_litellm_backend.py::test_sandbox_refuses_absolute -x` | ❌ Wave 0 |
| BACKEND-01 | `ChatCompletionMessageToolCall.model_dump()` round-trips id/type/function | unit | `pytest tests/unit/test_litellm_backend.py::test_tool_call_serialization -x` | ❌ Wave 0 |
| BACKEND-01 | Unknown model emits ONE `[unsupported-model]` WARN per process | unit | `pytest tests/unit/test_litellm_backend.py::test_unsupported_model_warn_dedup -x` | ❌ Wave 0 |
| BACKEND-01 | `BackendUnavailableError` on missing `litellm` import | unit | `pytest tests/unit/test_litellm_backend.py::test_missing_litellm_raises -x` | ❌ Wave 0 |
| BACKEND-01 | CLI `--backend litellm` without `--model` errors with exit code 2 | unit | `pytest tests/unit/test_cli_backend_flag.py::test_litellm_requires_model -x` | ❌ Wave 0 |
| BACKEND-01 | CLI `--backend litellm --model gemini/...` wires `LiteLLMBackend` | unit | `pytest tests/unit/test_cli_backend_flag.py::test_litellm_backend_wires -x` | ❌ Wave 0 |
| BACKEND-01 | Snapshot test: tinylib_ts → recorded LiteLLM stream → matches committed snapshot | golden | `pytest tests/golden/test_litellm_backend_snapshot.py -x` | ❌ Wave 0 |
| BACKEND-02 | `_litellm_pricing.cost_for_response()` returns float for known anthropic model | unit | `pytest tests/unit/test_litellm_pricing.py::test_anthropic_pricing -x` | ❌ Wave 0 |
| BACKEND-02 | Unknown model → WARN once + return 0.0 | unit | `pytest tests/unit/test_litellm_pricing.py::test_unknown_model_warn_dedup -x` | ❌ Wave 0 |
| BACKEND-02 | OpenRouter server-cost field preferred when present | unit | `pytest tests/unit/test_litellm_pricing.py::test_openrouter_server_cost -x` | ❌ Wave 0 |
| BACKEND-02 | `BudgetTracker` aborts when `LiteLLMBackend` cumulative cost > cap | unit | `pytest tests/unit/test_orchestrator_budget_litellm.py::test_litellm_cap_abort -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/test_litellm_backend.py tests/unit/test_litellm_pricing.py -x`
- **Per wave merge:** `pytest tests/unit/ -x` (currently ~250 unit tests; should run in <10s)
- **Phase gate:** Full suite green before `/gsd:verify-work` (385 → ~415 tests).

### Wave 0 Gaps

- [ ] `tests/unit/test_litellm_backend.py` — covers BACKEND-01 (LiteLLM backend behavior, sandbox, token accumulation, tool-call serialization, WARN dedup, BackendUnavailableError).
- [ ] `tests/unit/test_litellm_pricing.py` — covers BACKEND-02 (three-tier pricing fallback ladder).
- [ ] `tests/unit/test_cli_backend_flag.py` — covers CLI wiring of `--backend` on `init` + `update`.
- [ ] `tests/unit/test_orchestrator_budget_litellm.py` — covers BudgetTracker + cap interaction with LiteLLMBackend.
- [ ] `tests/golden/test_litellm_backend_snapshot.py` — golden snapshot via `RecordedBackend` queue against `tinylib_ts/`. Anthropic-direct path only (CONTEXT.md: "snapshot is stable").
- [ ] `tests/golden/recordings/tinylib_litellm_readme.txt` — recorded LLM response for the snapshot.
- [ ] `tests/golden/snapshots/tinylib_litellm_readme.md` — committed expected output.

## Security Domain

Security enforcement is implied enabled (config has no `security_enforcement: false`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (API key handling) | Read env vars at call time; never log or persist. `_log.debug` lines must NOT include `os.environ.get("ANTHROPIC_API_KEY")` or similar. Verified in spike: no key handling code present (LiteLLM reads env vars internally). |
| V3 Session Management | no | DocAgent is a CLI, not a service. |
| V4 Access Control | yes (filesystem sandbox) | `_safe_path()` refuses path escapes — equivalent to Phase 1's `permission_mode="bypassPermissions" + cwd=request.repo_root` ergonomics. Wave 4 unit tests pin `..`, absolute-path, and symlink-escape cases. |
| V5 Input Validation | yes (tool-call args from LLM) | `_safe_path()` validates `path` arg before any FS access. `_grep` validates regex via `re.compile()` and returns `error: bad regex` on failure (already in spike line 234). `_glob` accepts only the pattern string — `fnmatch.fnmatch()` is safe by construction. |
| V6 Cryptography | no | No DocAgent-side crypto operations. API keys pass through to LiteLLM/Anthropic SDK which handle TLS. |

### Known Threat Patterns for LiteLLM-backend stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via tool-call `path` arg from LLM | Tampering / Information Disclosure | `_safe_path()` `Path.resolve().relative_to(repo_root)` check — refuses any path that resolves outside repo_root. Tests in Wave 4. |
| Symlink escape (LLM Read'ing a symlink pointing outside repo) | Information Disclosure | `Path.resolve()` follows symlinks before `relative_to()`, so a symlink to `/etc/passwd` resolves to `/etc/passwd` and fails the `relative_to(repo_root)` check. Verified by inspection of spike code. Add an explicit test that creates a symlink in tinylib_ts pointing to `/tmp` and asserts Read refuses it. |
| Regex DoS via Grep pattern from LLM | Denial of Service | `re.compile()` accepts arbitrary patterns; catastrophic backtracking is theoretically possible. Mitigation: the loop is bounded by `max_turns=24` and the grep helper caps `hits >= 500` (spike line 238). Acceptable for v1 — DocAgent runs are bounded and non-public. |
| API key leak via logging | Information Disclosure | `_log.debug` in spike line 162-165 logs only `artifact_id`, token counts, char count — NO request/response content. Verified by inspection. |
| Prompt injection via repo contents | Tampering | Out of scope per project value: "every claim grounds to source." If the model invents claims, the verifier catches them at the `citations` gate. This is the moat. |
| Cost-budget bypass via long-running tool calls | DoS / cost overrun | `max_turns=24` bounds the loop. `BudgetTracker.would_exceed()` aborts between artifacts. Phase 5's `--max-cost` flag is unchanged and applies to the LiteLLM path. |

## Sources

### Primary (HIGH confidence)

- **Spike branch `spike/phase-8-litellm`** — `docagent/backends/litellm_backend.py` (~270 LOC), `scripts/spike_phase8_citation_rate.py` (~146 LOC), `pyproject.toml` `[multi]` extras + mypy override. Walked line-by-line.
- **ADR `.planning/decisions/0001-phase-8-multi-provider-backend.md`** — architectural decisions locked.
- **Spike results `.planning/decisions/0001-spike-results.md`** — empirical Ollama drop decision.
- **CONTEXT.md `.planning/phases/08-multi-provider-backends/08-CONTEXT.md`** — locked Phase 8 decisions.
- **Empirical install + execution** — `litellm==1.85.0` + `claude-agent-sdk==0.2.82` co-install in `/tmp/litellm-audit/` venv on 2026-05-17. `completion_cost()` behavior + `ChatCompletionMessageToolCall.model_dump()` round-trip verified directly.
- **Existing codebase patterns** — `docagent/backends/agent_sdk.py` (sibling backend), `docagent/pricing.py` (`_warned_models` pattern), `docagent/core/budget.py`, `docagent/core/orchestrator.py:50-78` (`_InstrumentedBackend`), `tests/unit/test_backend_token_extraction.py` (test pattern to mirror), `tests/golden/_harness.py` (`RecordedBackend` queue).

### Secondary (MEDIUM confidence)

- **LiteLLM docs** — https://docs.litellm.ai/docs/providers/openrouter (env var `OPENROUTER_API_KEY`, optional `OPENROUTER_API_BASE`); https://docs.litellm.ai/docs/providers/gemini (env var `GEMINI_API_KEY`, OpenAI-shape tool-use response, `thought_signature` provider-specific field); https://docs.litellm.ai/docs/completion/token_usage (`completion_cost` two-form signature). All verified via WebFetch 2026-05-17.
- **LiteLLM source on GitHub** — https://github.com/BerriAI/litellm `cost_calculator.py` (full `completion_cost` signature), `types/utils.py` (`Message` is Pydantic, `ChatCompletionMessageToolCall` is `OpenAIObject`). Verified via WebFetch + empirical.
- **PyPI metadata** — `litellm==1.85.0` direct deps (`pydantic <3.0.0,>=2.10.0`, `openai <3.0.0,>=2.20.0`, `httpx <1.0,>=0.28.0`, `aiohttp <4.0,>=3.10`, `jinja2 <4.0,>=3.1.6`, `jsonschema <5.0,>=4.0.0`, `click <9.0,>=8.0.0`); `claude-agent-sdk==0.2.82` direct deps (`anyio>=4.0.0`, `mcp>=1.23.0`, `sniffio>=1.0.0`, `typing-extensions>=4.0.0`). Verified via WebFetch of `pypi.org/pypi/<pkg>/json`.

### Tertiary (LOW confidence — flag for validation)

- **OpenRouter `usage.cost` field details + LiteLLM streaming bug** — verified via WebSearch hitting GitHub issues `BerriAI/litellm#11626`, `BerriAI/litellm#13653`, `BerriAI/litellm#15448`, `BerriAI/litellm#16021`. Not first-hand tested with a live OpenRouter call (no API key in research env). The Phase 8 plan should include a manual smoke step before the snapshot test goes green.
- **LiteLLM exception hierarchy** — official docs (https://docs.litellm.ai/docs/exception_mapping) confirm `BadRequestError`, `NotFoundError`, etc. inherit from OpenAI exception types. Empirically observed `completion_cost()` raises `BadRequestError` for provider-misspecified models AND bare `Exception` for unmapped routes. The mix is real; catch broad in the pricing shim.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `litellm==1.85.0` empirically installed + spike pyproject.toml already includes the `[multi]` extra.
- Architecture: HIGH — spike prototype implements the locked design; only polish + tests + wiring remain.
- Spike-code gaps: HIGH — walked line-by-line; gaps enumerated in Pattern 1.
- Pricing fallback ladder: HIGH for Tier 2 (`completion_cost`) + Tier 3 (WARN+0); MEDIUM for Tier 1 (OpenRouter server cost) — needs a live API smoke test in plan.
- Open questions: HIGH — three rationale-backed recommendations align with CONTEXT.md preliminaries.
- Documentation drift risk: MEDIUM — verdict is "no prompt change needed" but unverified that topic discovery will surface the multi-provider how-to organically.

**Research date:** 2026-05-17
**Valid until:** 2026-07-17 (fast-moving LiteLLM ecosystem — re-verify pricing-shim assumptions if more than 60 days pass before plan execution)
