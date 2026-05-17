# Roadmap: DocAgent

## Overview

DocAgent's path from a v1 alpha cut (4 single-file artifacts + working
`update` mode) through the post-alpha hardening that made the verifier
shippable (wiring `verify` against on-disk artifacts + a GitHub Action +
audit-fix list), a TypeScript adapter to broaden language coverage into the
agent-files niche, and the first multi-file artifact (`api_reference`).
Active work shifts to budget telemetry next, then `how_to_guides`, then TS
`api_reference`.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, …): planned milestone work
- Decimal phases (2.1, …): urgent insertions (marked INSERTED)

- [x] **Phase 1: v1 alpha cut** — 4 single-file artifacts + update mode shipped
- [x] **Phase 2: Post-alpha hardening + GitHub Action** — verify wired, audit fixes, Action live
- [x] **Phase 3: TypeScript adapter** — JS/TS deep adapter with own tags.scm
- [x] **Phase 4: `api_reference` artifact (Python)** — first multi-file artifact, schema v2
- [x] **Phase 5: Budget telemetry** — token counts + `--max-cost` (Anthropic-only)
- [x] **Phase 6: `how_to_guides` artifact** — Diátaxis how-to quadrant
- [ ] **Phase 7: TypeScript `api_reference`** — broaden the multi-file artifact to TS repos
- [ ] **Phase 8: Multi-provider backends** — Ollama / Gemini / litellm (reopens "one canonical backend")

## Phase Details

### Phase 1: v1 alpha cut (SHIPPED)

**Goal**: Four artifacts (`readme`, `agents_md`, `claude_md`, `llms_txt`) wired end-to-end through plan → generate → verify → write, with `update` mode running.
**Depends on**: Nothing (first phase)
**Requirements**: GEN-01, ART-01, ART-02, ART-03, ART-04, VER-01, VER-02, LANG-01, LANG-03, DIST-01
**Success Criteria**:
  1. `docagent init` produces grounded artifacts for the tinylib fixture.
  2. `docagent update` resolves affected artifacts via the two-signal resolver and re-runs only what changed.
  3. The deterministic verifier pipeline runs and reports per-gate findings.
**Status**: Shipped (commit `4a494df` and prior). Tests: 70 at this point.

### Phase 2: Post-alpha hardening + GitHub Action (SHIPPED)

**Goal**: Make `docagent verify` a real, CI-runnable feature, ship the GitHub Action, and close the audit-fix list found by the post-alpha dispatch.
**Depends on**: Phase 1
**Requirements**: VER-03, VER-04, VER-05, GEN-02 (registry-discovery fallback), GEN-03 (claude-cli preflight), DIST-02, DIST-03
**Success Criteria**:
  1. `docagent verify` exits 0 on this repo's own artifacts.
  2. `action.yml` runs `docagent verify` on a PR runner and posts a sticky failure comment.
  3. Audit-fix list closed: judge stub honest, citation regex unified, mention extractor tightened, paths normalized to repo-relative POSIX, logging + `--debug` flag, friendly missing-`claude` error.
**Status**: Shipped (commits `48c33e4` + follow-ups). Tests: 116.

### Phase 3: TypeScript adapter (SHIPPED)

**Goal**: Deep symbol extraction for `.ts/.tsx/.js/.jsx/.mjs/.cjs/.d.ts` — same shape as the Python adapter, dedicated `tags.scm`, scope-aware qualified names.
**Depends on**: Phase 2
**Requirements**: LANG-02
**Success Criteria**:
  1. `TypeScriptAdapter` extracts function/class/method/interface/type/enum/namespace symbols with byte/line ranges.
  2. CJS `module.exports.foo = () => …` captured; constructors and `#private` members filtered.
  3. End-to-end `update` flow works on a TS fixture (`tinylib_ts/`).
**Status**: Shipped (commits `fe041dd` → `8606190`). Tests: 147.

### Phase 4: `api_reference` artifact (SHIPPED)

**Goal**: First multi-file artifact. One curated `docs/reference/<dotted>.md` per public Python module. Schema v2 introduces composite PK on `artifacts` table + per-unit fingerprint table.
**Depends on**: Phase 3 (not strictly — independent, but built after for sequencing reasons)
**Requirements**: ART-05
**Success Criteria**:
  1. `docagent init` writes one page per public Python module under `docs/reference/`.
  2. Per-module fingerprint cache makes re-runs no-ops (idempotence).
  3. Source change re-generates only the affected module.
  4. `--max-modules` cap honored; `0` means unlimited.
  5. Intra-artifact sibling links pass the verifier mid-run via the `_future_paths` carve-out.
**Status**: Shipped (commits `bd2144a` + `4afe3e6` + `3a64a19` + `f99d882`). Tests: 200.

### Phase 5: Budget telemetry

**Goal**: Surface per-run token counts and add a soft `--max-cost` guard so users can `Ctrl-C` before bankruptcy on large multi-call runs.
**Depends on**: Phase 4
**Requirements**: BUDGET-01, BUDGET-02, BUDGET-03
**Success Criteria**:
  1. `docagent init` prints cumulative input + output token counts at end of run.
  2. Multi-call artifacts (api_reference) emit a per-call progress line including running token + cost estimate.
  3. `--max-cost $X` aborts the orchestrator loop before exceeding the cap.
**Plans**: 1 plan, 5 waves (~150 source LOC + ~250 test LOC)
- [ ] PLAN.md — Wave 1: agent_sdk dict-extraction bugfix; Wave 2: pricing.py; Wave 3: budget.py; Wave 4: orchestrator threading + per-call lines + cap check; Wave 5: CLI --max-cost + DOCAGENT_MAX_COST + summary footer + exit code 3

### Phase 6: `how_to_guides` artifact (SHIPPED 2026-05-17)

**Goal**: Generated Diátaxis how-to docs under `docs/how-to/`. Multi-file like `api_reference`. Depends on the existence of a README and `api_reference` pages to ground "how to use X" claims.
**Depends on**: Phase 4 (api_reference must exist), Phase 5 (cost-control is non-negotiable for a multi-file LLM artifact)
**Requirements**: HOWTO-01
**Success Criteria**:
  1. `docagent init --only how_to_guides` writes one Markdown page per detected user-task topic.
  2. Each page grounds claims to README sections + api_reference pages + actual code.
  3. Verifier exits 0; no orphan how-to pages after a source rename (incremental update flags them).
**Plans**: 6 plans across 4 waves (all shipped 2026-05-17)
- [x] 06-01-PLAN.md — Wave 1: P0 orchestrator bug fix — drain last_responses into run.* between plan() and per-task loop, with regression test (`3dbeab7`)
- [x] 06-02-PLAN.md — Wave 2: `_topic_discovery.py` — Topic dataclass + topic_slug() + dedupe_topics() with first-write-wins + WARN (`5cab74d`)
- [x] 06-03-PLAN.md — Wave 2: `_how_to_render.py` — deterministic frontmatter + See also block + page assembler
- [x] 06-04-PLAN.md — Wave 2: `docagent/prompts/how_to_guides.py` — discovery + per-page prompts under single PROMPT_VERSION
- [x] 06-05-PLAN.md — Wave 3: `HowToGuidesArtifact` end-to-end — plan/generate/post_write + DAG registration + --max-howtos CLI flag + orphan-flag sentinel
- [x] 06-06-PLAN.md — Wave 4: `RecordedBackend.responses` queue extension + golden snapshot test on tinylib fixture (2 topics) (`537e455`)
**Status**: Shipped (6 commits, +55 tests). Tests: 304.

### Phase 7: TypeScript `api_reference`

**Goal**: Bring the multi-file artifact to TS repos. Module discovery via `tsconfig.include` + `package.json` exports.
**Depends on**: Phase 4
**Requirements**: TSAPI-01
**Success Criteria**:
  1. `docagent init` on a TS repo writes `docs/reference/<dotted>.md` per public module.
  2. JSDoc-aware where useful, but JSDoc *splicing* remains out of scope.
  3. Same idempotence + `--max-modules` semantics as the Python path.

### Phase 8: Multi-provider backends

**Goal**: Add Ollama, Gemini, and litellm backends alongside `AgentSDKBackend`. Reopens the "one canonical backend" decision deliberately — Phase 5's price-table abstraction was designed to slot per-provider rates in.
**Depends on**: Phase 5 (budget telemetry must be live so per-provider pricing has a home)
**Requirements**: BACKEND-01, BACKEND-02
**Success Criteria**:
  1. `docagent init --backend ollama` runs end-to-end against a local Ollama instance (free tier — pricing rows = $0).
  2. `docagent init --backend gemini` and `--backend litellm` work with user-supplied API keys via env vars; pricing tables added for each.
  3. Existing `AgentSDKBackend` remains the default; no regression on the Anthropic path.
  4. Prompt forks are minimized via a shared prompt template layer — divergence reviewed at plan time.
