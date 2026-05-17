# Project State

## Project Reference

See: .planning/PROJECT.md (scaffolded 2026-05-16)

**Core value:** The verifier is the moat — every claim grounds to source, and CI breaks if the source moves.
**Current focus:** v1 feature-complete — Phase 8 (multi-provider backends) shipped 2026-05-17.

## Current Position

Phase: 8 of 8 (multi-provider backends) — SHIPPED 2026-05-17
Plan: complete (08-01 through 08-06, 6 plans across 6 waves)
Status: v1 FEATURE-COMPLETE. All 8 phases shipped. Ready for `/gsd:verify-work` and any
remaining packaging / docs work before the v1 alpha release.
Last activity: 2026-05-17 — Phase 8 (multi-provider backends) shipped end-to-end across
6 waves, 7 commits, +69 tests (385 → 454). LiteLLMBackend ported from
`spike/phase-8-litellm` with five polish deltas (logger silencer, AuthenticationError
wrap, defensive `not response.choices` guard, max_turns `else:` warn, RateLimitError
single-retry). `[multi]` extras pin `litellm>=1.50`; pydantic floor bumped 2.7 → 2.10
to match LiteLLM 1.85. Three-tier pricing shim
(`docagent/backends/_litellm_pricing.py`): Tier 1 OpenRouter `response.usage.cost`
(opt-in via `extra_body={"usage":{"include":True}}`); Tier 2
`litellm.completion_cost`; Tier 3 broad-Exception swallow + ONE-WARN-per-model dedup
returning 0.0. New `GenerationResponse.cost_usd: float | None` field threads
authoritative cost from backend to tracker. `_TESTED_MODELS` frozenset locks the v1
allowlist (gemini flash/pro, openrouter sonnet/opus, anthropic-direct sonnet/opus —
NO Ollama, deferred to v1.1 per spike verdict). CLI gains `--backend
{agent_sdk,litellm}` on init + update (default `agent_sdk`, zero regression);
`--backend litellm` without `--model` exits 2 with multi-line env-var hint.
`BudgetTracker.add(external_cost=...)` accepts shim values; orchestrator threads
`response.cost_usd` at BOTH `tracker.add()` call sites — line ~166 (plan()-call
drainage, the Phase 6 P0 fix path) AND line ~223 (per-task post-write).
Self-policing W1 grep gate `grep -cE 'external_cost'
docagent/core/orchestrator.py == 2` enforced. Golden snapshot test
(`tests/golden/test_litellm_backend_snapshot.py`) uses LiteLLM's built-in
`mock_response` kwarg for CI-stable behavior pinning — no live API, no env vars
required, skips cleanly without `[multi]` installed.

Progress: [██████████] 100% (8 of 8 phases shipped — v1 feature-complete)

## Performance Metrics

**Velocity (this session):**
- Total commits: 35 (7 new in Phase 8)
- Tests added: 70 → 454 (+384)
- Phases shipped: Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 8

**By Phase:**

| Phase | Commits | Tests added | Status |
|-------|---------|-------------|--------|
| 1: v1 alpha cut | 7 | 0 → 70 | Shipped (prior session) |
| 2: Hardening + Action | 1 (`48c33e4`) | 70 → 116 | Shipped |
| 3: TypeScript adapter | 4 (`fe041dd`–`8606190`) | 116 → 147 | Shipped |
| 4: `api_reference` | 4 (`bd2144a`–`f99d882`) | 147 → 200 | Shipped |
| 5: Budget telemetry | 5 (`c78c260`–`c70dca7`) | 200 → 249 | Shipped 2026-05-17 |
| 6: `how_to_guides` | 6 (`3dbeab7`–`537e455`) | 249 → 304 | Shipped 2026-05-17 |
| 7: TS api_reference | 6 (`424430e`–`1781c39`) | 304 → 385 | Shipped 2026-05-17 |
| 8: Multi-provider backends | 7 (`b0fe3ae`–meta) | 385 → 454 | Shipped 2026-05-17 |

## Accumulated Context

### Decisions

- One canonical backend (`AgentSDKBackend`) — no pure-LLM / Ollama paths in v1.
- SQLite over JSON for the symbol + mention + fingerprint indexes.
- Deterministic-first verifier with non-blocking stylistic gates.
- Multi-language via tree-sitter + opt-in per-language deepeners.
- Identifier-mention index populated by orchestrator post-write hook.
- Multi-file artifact shape: composite PK on `artifacts`, per-unit fingerprint table, per-artifact `post_write` hook.
- `model=None` records as `"sdk-default"` for fingerprint stability across SDK updates.
- Budget telemetry (Phase 5): `DocPatch` NOT extended for tokens; orchestrator wraps the backend with `_InstrumentedBackend` to observe `GenerationResponse` per call. `Orchestrator.run()` return type unchanged (`list[ArtifactRun]`); tracker exposed as `orchestrator.tracker` instance attribute. Cap check is post-fact (one-artifact slack); pre-flight estimation is v2.
- Pricing fallback: unknown model → Opus 4.7 rates + ONE WARN per distinct model name (deduplicated via module-private `_warned_models: set[str]`).
- CLI summary: shared `_render_summary` helper for `init` + `update` parity; `--max-cost` negative validation via typer `callback=` so exit code 2 is clean; env-var path is intentionally lenient (logs DEBUG, falls back to 0).
- Phase 6 (`how_to_guides`): topic-discovery LLM call lives in `plan()`, requiring the P0 orchestrator drain fix (Plan 06-01) — last_responses drained between `plan()` and the per-task loop. Per-page fingerprint = `sha256(prompt_version | model | slug | sorted(path@source_hash))`. Orphan flagging fires exactly once per run on the sentinel `_slugs_written == len(_slugs_to_write)` (== not >=); zero-task cache-hit runs fall back to flagging from the end of `plan()`. Single `PROMPT_VERSION` covers both discovery + per-page prompts (intentional coupling — any prompt change invalidates all how-to fingerprints). `orchestrator._last_ctx_config` exposes the per-run ctx so the CLI can read artifact-emitted entries (orphans/warnings) that live on the per-run copy, not the orchestrator's input config.
- Phase 7 (TS `api_reference`): one artifact id `api_reference` for both languages — the dispatch happens inside `plan()`, NOT in registry/DAG (Diátaxis "reference" is language-agnostic). Discovery is a three-tier cascade with first-non-empty-signal short-circuit (NOT union): `package.json#exports` → `tsconfig.json#include` → glob. Wildcard-only `exports` maps downgrade to "absent" with one WARN. `--max-modules` caps the MERGED Python+TS list, deterministic-sorted by dotted name (RESEARCH.md Pitfall 5 closed). JSDoc capture is a tree-sitter `(comment)` capture filtered to `/**` blocks in Python and paired with the nearest immediately-following def whose intervening lines are all blank. `extract_exports()` lives on a separate `.scm` query file (`typescript_exports.scm`) so the existing `extract_symbols` contract ("definitions only") is unchanged. JSONC stripper switched from the three-regex approach in the plan to a string-aware single-pass scanner because the regex form ate `/**/` inside glob strings like `"src/**/*"` (Rule 1 deviation — fix documented in 07-03 summary). PROMPT_VERSION 1→2 bump invalidates Phase-4 Python fingerprints once; this repo has no Python `api_reference` golden snapshots so the bump doesn't drift any committed test artifact. Aliased re-export row shape locked at RESEARCH.md Q1: `name=Bar, kind=re_export, exported-as cell = "Bar (from other.Foo)"`.
- Phase 8 (multi-provider backends): one new `LiteLLMBackend` alongside `AgentSDKBackend` (the latter remains default). LiteLLM 1.85 only — no `experimental_mcp_client`, no `AgenticLoop` callback infra. Hand-written ~80 LOC tool loop on `litellm.completion(..., tools=[...])`. `[multi]` extras gates `litellm`; default `pip install docagent` keeps the small dep tree. **Ollama OUT of v1** — spike on `ollama_chat/llama3.1:8b` measured 0 tool calls + 1 invented citation = 0% citation-emission rate; re-spike trigger in v1.1 on Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ / GLM-4.6+. Six-model v1 allowlist locked: gemini flash/pro, openrouter sonnet/opus, anthropic-direct sonnet/opus. Unknown model → ONE `[unsupported-model]` WARN per name per process via `_warned_allowlist_models` dedup; non-blocking. Three-tier pricing ladder in `_litellm_pricing.py`: Tier 1 OpenRouter authoritative `response.usage.cost` (opt-in via `extra_body={"usage":{"include":True}}`); Tier 2 `litellm.completion_cost`; Tier 3 **broad `except Exception`** (LiteLLM raises bare Exception for unmapped models — Pitfall 1) + ONE-WARN-per-model dedup returning 0.0. `GenerationResponse.cost_usd: float | None` threads authoritative cost from backend through orchestrator. `BudgetTracker.add(external_cost=...)` honors `external_cost` (including 0.0) over `pricing.estimate_cost()`. Orchestrator threads `response.cost_usd` at BOTH `tracker.add()` call sites — the symmetric cost-half of the Phase 6 P0 token-attribution fix; self-policing grep gate `grep -cE 'external_cost' docagent/core/orchestrator.py == 2`. RateLimitError gets exactly ONE retry (sleep 2s then re-raise); BadRequestError never retried; no exponential backoff (rate-limited bills are worse with compounding retries). `pydantic>=2.10` floor bump from `>=2.7` to match LiteLLM's resolver floor. Logger silencer at module load (`logging.getLogger("LiteLLM").setLevel(logging.ERROR)`) hides the cosmetic Bedrock/SageMaker pre-load WARNs. Golden snapshot uses LiteLLM's built-in `mock_response` SDK kwarg — CI-stable, no live API, no env vars.

### Mid-session bugs caught & fixed (alpha hardening era)

- Pipeline blocking semantics: non-blocking gate failures were flipping `ok` (Action self-hosting caught this).
- tree-sitter `Query.captures` API drift across versions — added 3-shape compat layer.
- TS def↔name pairing: outer class def stealing inner method names → fixed with "tightest enclosing def wins."
- PythonAdapter byte ranges were always zero — fixed with UTF-8-safe column→byte conversion via per-line offset table.
- See-also parent link broke when parent module had only private symbols.
- Link checker was resolving relative URLs against `repo_root` instead of `patch.target_path.parent` (Markdown semantics).

### Field-derived improvements queued

- Token-budget gate on AGENTS.md/CLAUDE.md (≤200 lines per Augment/InfoQ research).
- Commands-first prose-last in AGENTS.md prompts (OpenAI pattern).
- Cap "DO NOT"/"Never" bullets — Pink Elephant Problem.
- Symbolic grounding (`<!-- ground: docagent.core.X -->`).
- Conditional llms.txt — only when docs site exists; split with `llms-full.txt`.

### Packaging frame (adopted)

Lead public announcement with `docagent verify` as the headline, not `init`. "Docs-CI that works on any markdown, regardless of who wrote it" reaches a 10× larger audience than "another README generator."

## Git Reference

- Branch: `main`
- Remote: https://github.com/hayden1126/DocAgent (public, MIT)
- Latest commit: `3582559` — feat(08-06): LiteLLM golden snapshot via mock_response (Phase 8 complete; meta-commit pending)
- Repo memory lives at `~/.claude/projects/-home-hayden-DocAgent/memory/` (overview, alpha cut, post-alpha roadmap, architecture, feedback patterns, GitHub references). `.planning/` is a synchronized snapshot derived from those files on 2026-05-16.
