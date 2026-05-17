# Requirements: DocAgent

**Defined:** 2026-05-16 (scaffolded from project memory)
**Core Value:** The verifier is the moat — every claim grounds to source and CI breaks if the source moves.

## v1 Requirements

Requirements for the v1 alpha. Each maps to a roadmap phase. Items marked
shipped have passing tests + live verification on this repo (`docagent verify` exit 0).

### Generation pipeline (shipped)

- [x] **GEN-01**: `docagent init` scans the repo, indexes symbols, and runs the artifact DAG. `--only` filters by id; `--dry-run` prints diffs; `--skip-index` reuses existing `.docagent/index.db`; `--max-modules N` caps per-module artifacts.
- [x] **GEN-02**: `docagent update` resolves affected artifacts via two signals (identifier-mention index ∪ on-disk path citations) and refreshes only what's affected.
- [x] **GEN-03**: Generation backend is `AgentSDKBackend` (Claude Agent SDK; tools=Read/Glob/Grep; sync wrapper around `query()`); friendly install hint when `claude` CLI is missing.

### Artifacts (shipped)

- [x] **ART-01**: `readme` — top-level README.md, H1-anchored, generated via `SingleFileArtifact`.
- [x] **ART-02**: `agents_md` — root `AGENTS.md` per the Linux Foundation spec.
- [x] **ART-03**: `claude_md` — root `CLAUDE.md` per Anthropic's convention.
- [x] **ART-04**: `llms_txt` — root `llms.txt` per llmstxt.org.
- [x] **ART-05**: `api_reference` — one curated `docs/reference/<dotted>.md` per public Python module. Deterministic public-surface table + LLM-written opener + workflows; per-module fingerprint idempotence.

### Verifier (shipped)

- [x] **VER-01**: Pipeline gates in order: markdownlint, links, citations, docs_site, secrets, judge.
- [x] **VER-02**: Blocking semantics — only blocking-gate failures flip `ok`. `--strict` re-tightens to "fail on any finding" at the CLI.
- [x] **VER-03**: Citation grammar — `<!-- ground: path:start-end -->`; single source in `docagent/citations.py`. Paths repo-relative POSIX, no `:` or whitespace.
- [x] **VER-04**: `docagent verify` runs gates against on-disk artifacts with a registry-discovery fallback (works on a fresh CI checkout without prior `init`).
- [x] **VER-05**: `judge` gate is non-blocking and emits `skipped: judge not yet implemented` until wired (no silent passes).

### Language support (shipped)

- [x] **LANG-01**: Python deep adapter — libcst + tree-sitter, UTF-8-safe byte ranges, scope-aware qualified names.
- [x] **LANG-02**: TypeScript / JavaScript deep adapter — dedicated `tags.scm` lifted from upstream, `.ts/.tsx/.js/.jsx/.mjs/.cjs/.d.ts` coverage, CJS `module.exports.foo = …` capture, scope-aware qualified names.
- [x] **LANG-03**: Fallback adapter — tree-sitter symbol extraction only for Rust, Go, Java, C++.

### Distribution (shipped)

- [x] **DIST-01**: pip-installable as `docagent`, console script entry point.
- [x] **DIST-02**: GitHub Action wrapper (`action.yml`, composite) — runs `docagent verify` on PRs; sticky failure comment; no API key required.
- [x] **DIST-03**: CI workflows — `tests.yml` runs pytest on push/PR (py3.11+3.12); `verify.yml` is self-hosting against this repo.

### Active v1 work

- [ ] **BUDGET-01**: Per-run token counts (input + output + tool calls) surfaced from `GenerationResponse` to the CLI summary.
- [ ] **BUDGET-02**: Per-artifact progress line during multi-call runs (`[3/20] tinylib.cli  in=842 out=129 cum=$0.034`).
- [ ] **BUDGET-03**: `--max-cost $X` soft guard — abort the orchestrator loop before exceeding the cap. Defaults to off.
- [ ] **HOWTO-01**: `how_to_guides` artifact — generated under `docs/how-to/`; Diátaxis "how-to" quadrant only. Depends on `readme` and `api_reference`.
- [x] **TSAPI-01**: TypeScript `api_reference` — module discovery via tsconfig.include / package.json exports; same artifact shape, language-agnostic at the orchestration layer. Shipped 2026-05-17 (Phase 7).
- [ ] **BACKEND-01**: Multi-provider backends — Ollama, Gemini, litellm — selectable via `--backend <name>`; user supplies API keys via env vars; `AgentSDKBackend` remains default.
- [ ] **BACKEND-02**: Per-provider pricing rows in `docagent/pricing.py`; Ollama maps to $0 input/output; unknown models within a provider trigger the same Opus-fallback WARN behavior.

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### Symbolic grounding

- **SYMGROUND-01**: `<!-- ground: docagent.core.X -->` resolved via the symbol index, with line-range as fallback. Rustdoc intra-doc-link lesson: validate to symbols, not paths.

### llms.txt split

- **LLMS-FULL-01**: Implement the `llms.txt` (link index) + `llms-full.txt` (dump) split per llmstxt.org. Generate conditionally on detection of a docs site.

### LSP / tsserver deepeners

- **LSPDEEP-01**: TypeScript cross-file resolution via tsserver — alias following, import resolution, re-export tracking.
- **LSPDEEP-02**: Rust deepener via rust-analyzer LSP — semantic xref, macro-expanded items.
- **LSPDEEP-03**: Go deepener via `go list -json` — package metadata + xref.

### Splice / in-place edits

- **SPLICE-01**: `python_docstrings` artifact behind `--experimental` — in-place PEP 257 docstring generation via libcst. Requires fingerprinting by symbol hash, `--max-symbols` cap, git-clean refusal.
- **SPLICE-02**: JSDoc / TypeScript docstring splice — separate artifact, separate adapter splicer path.

### Concurrency

- **CONC-01**: `asyncio.gather` peer artifacts where the DAG allows. Requires the link gate's `_future_paths` carve-out to be thread-safe (currently mutates `ctx.config` in verify).

### Other deferred

- **WATCH-01**: `docagent watch` mode.
- **JUDGE-01**: Wire the `judge` gate's single-turn LLM call.
- **TOKBUDGET-01**: Token-budget gate on AGENTS.md/CLAUDE.md (≤200 lines, ≤~1500 tokens per Augment/InfoQ research).

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| `python_docstrings` in v1 | Plan agent's skeptical critique: in-place mutation + cost shock + format-preservation bar are too high for an experimental flag. Revisit post-1.0. |
| Per-symbol `api_reference` pages | mkdocstrings/pdoc render per-symbol bodies well. DocAgent's value-add is curated landing, not duplication. |
| Local LLMs / Ollama / OpenAI backend | One canonical backend (Claude Agent SDK). Reopening the abstraction forces per-backend prompt forks. |
| MCP-server-as-docs-delivery | Mintlify/GitBook own this lane. Repos use flat files; the agent already has filesystem tools. |
| Monorepo workspace support | Multiple `pyproject.toml` files → document the root one and warn. Real workspace ergonomics is post-1.0. |
| Cross-file symbol resolution beyond leaf-name matching | v2 deepener territory (tsserver/LSP). v1 relies on the mention index + citations gate. |

## Traceability

Which phases cover which requirements. Updated as the roadmap advances.

| Requirement | Phase | Status |
|-------------|-------|--------|
| GEN-01, ART-01–04, VER-01–02, LANG-01, LANG-03, DIST-01 | Phase 1 | Shipped |
| VER-03–05, GEN-02–03, DIST-02–03 | Phase 2 | Shipped |
| LANG-02 | Phase 3 | Shipped |
| ART-05 | Phase 4 | Shipped |
| BUDGET-01–03 | Phase 5 | Active |
| HOWTO-01 | Phase 6 | Planned |
| TSAPI-01 | Phase 7 | Shipped |
| BACKEND-01–02 | Phase 8 | Planned |
