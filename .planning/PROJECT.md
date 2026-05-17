# DocAgent

## What This Is

DocAgent is an open-source repository documentation agent that reads existing
repos, writes new documentation, and verifies that the documentation still
matches the code. Output is dual-track: human-readable Markdown (README,
how-to guides, API reference) plus agent-facing files (`AGENTS.md` per the
Linux Foundation spec, `CLAUDE.md` per Anthropic, `llms.txt` per llmstxt.org).
Pre-1.0 alpha; pip-installable CLI plus a GitHub Action wrapper.

## Core Value

**The verifier is the moat.** Every non-trivial claim in generated docs
carries a `<!-- ground: path:lines -->` HTML comment, and a deterministic
pipeline confirms the cited file and line range still match before CI passes.
If everything else fails, that one thing must keep working — it's what makes
DocAgent's docs falsifiable when every competitor's are not.

## Requirements

### Validated

<!-- Shipped end-to-end, passing tests + live dogfood on this repo. -->

- [x] **README artifact** — `docagent init --only readme` generates a grounded README that passes `docagent verify` (exit 0). Self-host: this repo's own README is generated and verified.
- [x] **AGENTS.md / CLAUDE.md / llms.txt artifacts** — agent-facing docs, same generation + verification pipeline.
- [x] **`update` mode** — incremental refresh via two-signal affected-artifact resolver (identifier-mention index + on-disk citation paths).
- [x] **`verify` command** — runs the deterministic gate pipeline (markdownlint → links → citations → docs_site → secrets → judge) against on-disk artifacts; `--strict` re-tightens at the CLI.
- [x] **GitHub Action wrapper** — composite action runs `docagent verify` on PRs; sticky comment on failure; pure-deterministic, no Claude API key required.
- [x] **TypeScript / JavaScript adapter** — dedicated tags.scm, scope-aware qualified names, .ts/.tsx/.js/.jsx/.mjs/.cjs/.d.ts coverage, CJS support.
- [x] **`api_reference` artifact (Python)** — one curated landing page per public module at `docs/reference/<dotted>.md`; deterministic surface table + LLM-written opener + workflows; per-module fingerprint idempotence; `--max-modules` cap.
- [x] **Budget telemetry + `--max-cost`** — per-run input/output tokens + tool-call totals from `GenerationResponse`; `BudgetTracker` accumulator; per-call progress lines for multi-task artifacts; soft cost cap via flag or `DOCAGENT_MAX_COST` env var with post-fact between-artifacts check (Phase 5; cost-half extended in Phase 8 via `external_cost`).
- [x] **`how_to_guides` artifact** — Diátaxis how-to pages generated under `docs/how-to/` with topic discovery in `plan()` + per-page generate; orphan flagging; `--max-howtos` cap.
- [x] **TypeScript `api_reference`** — same multi-file artifact shape on TS repos via three-tier module-discovery cascade (`package.json#exports` → `tsconfig.json#include` → glob) + JSDoc capture + `extract_exports()`; merged Python+TS `--max-modules` cap with deterministic sort.
- [x] **Multi-provider backends (LiteLLM)** — `LiteLLMBackend` alongside `AgentSDKBackend` (default unchanged), gated behind `pip install docagent[multi]`. Routes Gemini / OpenRouter / Anthropic-direct via LiteLLM 1.85+. Tested-model allowlist (`_TESTED_MODELS` frozenset) of 6 entries with one-WARN-per-unknown-model dedup. Three-tier pricing shim (OpenRouter authoritative `usage.cost` → `litellm.completion_cost` → broad-exception fallback to 0.0 with WARN dedup). `--backend {agent_sdk,litellm}` flag on init+update. RateLimitError single-retry; BadRequestError no-retry. Golden snapshot via `litellm.completion(mock_response=...)`. v1.1 re-spike trigger on Ollama once Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ / GLM-4.6+ are reachable (current spike: 0% citation rate on llama3.1:8b).

### Active

<!-- All v1 requirements shipped. -->

v1 feature-complete as of 2026-05-17. Remaining work before the v1 alpha
release is packaging / docs / dogfood:
- README "Multi-provider setup" subsection (auto-regenerates on first
  `docagent update` after Phase 8 lands).
- `docs/how-to/use-multi-provider-backends.md` (will be discovered
  organically by `how_to_guides` on next run with a real API key).
- v1.1 re-spike trigger: Ollama on Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ /
  GLM-4.6+ — one-constant edit to `_TESTED_MODELS` once the citation-rate
  spike re-runs at ≥80%.

### Out of Scope

<!-- Explicit boundaries. Reasoning prevents re-adding. -->

- **`python_docstrings` artifact** — cut from v1 per the Plan agent's skeptical critique. In-place source mutation, cost-shock surface, and format-preservation bar are too high for an `--experimental` flag. Revisit post-1.0.
- **Per-symbol `api_reference` pages** — mkdocstrings/pdoc render per-symbol bodies well; DocAgent's value-add is the curated landing, not duplication.
- **Local LLMs / Ollama** — `AgentSDKBackend` remains the default. `LiteLLMBackend` (Phase 8) ships behind `[multi]` extras for Gemini / OpenRouter / Anthropic-direct, **not** Ollama. Ollama deferred to v1.1: the 2026-05-17 spike on `ollama_chat/llama3.1:8b` measured 0 tool calls + 1 invented citation = 0% citation-emission rate. Re-spike trigger on Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ / GLM-4.6+ is a one-constant edit to `_TESTED_MODELS`. The "one canonical backend" load-bearing bet is now scoped to v1.0 only (Phase 8 narrowed BACKEND-01 to LiteLLM-only).
- **MCP-server-as-docs-delivery** — Mintlify/GitBook own this lane. Our audience is repos; flat files beat a live server because the agent already has filesystem tools.
- **Monorepo workspace support** — if multiple `pyproject.toml` files exist, document the root one and warn. Real workspace ergonomics is post-1.0.
- **`watch` mode** — deferred to v1.1.
- **Cross-file symbol resolution beyond leaf-name matching** — v2 deepener territory (tsserver/LSP); not in v1.

## Context

- **Closest prior art:** OpenBMB/RepoAgent (Python-only, single-shot LLM calls, no verification, stalled since Dec 2024); DocuWriter.ai (closed SaaS). The lane for OSS verifier-grounded multi-language docs is open.
- **Competitive read (4-agent research, 2026-05-16):** Three of four research agents converged on the verifier as the genuinely novel thing. The generator gets commoditized in 12 months; the verifier + citation-grounding does not.
- **Packaging frame:** lead public announcement with `docagent verify` as the headline use case, not `init`. "Docs-CI that works on any markdown, regardless of who wrote it" reaches a 10× larger audience than "another README generator."
- **Test state:** 454 passing across unit + golden + integration (as of 2026-05-17, end of Phase 8).

## Constraints

- **Tech stack**: Python ≥ 3.11, Typer CLI, Claude Agent SDK backend, SQLite index (`.docagent/index.db`), libcst + tree-sitter for parsing.
- **Backend**: `AgentSDKBackend` is the sole v1 backend (sync wrapper around async SDK; tools restricted to Read/Glob/Grep; `permission_mode="bypassPermissions"`).
- **Storage**: SQLite, schema v2. The artifacts table has composite PK `(artifact_id, path)` to support multi-file artifacts. Schema bumps hard-fail with "delete `.docagent/index.db`" — v1-alpha-acceptable.
- **Verifier ordering**: stylistic gates (markdownlint, docs_site, judge) are NON-blocking; truth-checking gates (links, citations, secrets) are blocking. `--strict` flips "fail on any finding" at the CLI, not in the pipeline.
- **Grounding contract**: every non-trivial claim in generated docs MUST carry `<!-- ground: path:line-start-line-end -->` immediately after the sentence it grounds. Paths repo-relative, line ranges inclusive, `:` reserved as delimiter.

## Key Decisions

- **One canonical backend in v1.0; LiteLLM extras in v1 release.** Pure-LLM and Ollama paths were initially rejected because they'd force per-backend prompt forks. Phase 8 added `LiteLLMBackend` behind `[multi]` extras (Gemini / OpenRouter / Anthropic-direct) under the constraint that the SAME DocAgent system prompt grounds citations at ≥80% on every allowlisted model — so the no-prompt-forks invariant is preserved. The allowlist enforces it: any new model must clear the spike-measured rate before it joins. Ollama deferred to v1.1 per the 2026-05-17 spike.
- **SQLite, not JSON.** Mention index is queried by identifier (set-membership); JSON balloons on monorepos.
- **Deterministic-first verifier with non-blocking stylistic gates.** One MD013 nit must not nuke an otherwise-valid artifact before the cheaper citation check runs.
- **Multi-language via tree-sitter + per-language deepeners** (libcst+Jedi for Python now; LSPs as opt-in deepeners later).
- **Identifier-mention index** populated by the orchestrator's post-write hook. Without it, prose silently rots when symbols rename.
- **Multi-file artifact shape** introduced for `api_reference`: composite PK on `artifacts`, per-unit fingerprint table, per-file post-write hook, intra-artifact sibling-link carve-out in the link gate.
- **Model fingerprint stability:** `model=None` records as the string `"sdk-default"` so the SDK silently bumping Sonnet doesn't invalidate every cache entry. First-time use of `--model` invalidates prior fingerprints once.
