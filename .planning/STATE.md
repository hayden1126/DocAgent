# Project State

## Project Reference

See: .planning/PROJECT.md (scaffolded 2026-05-16)

**Core value:** The verifier is the moat — every claim grounds to source, and CI breaks if the source moves.
**Current focus:** Phase 6 (`how_to_guides`) — Phase 5 shipped.

## Current Position

Phase: 6 of 8 (next: `how_to_guides`)
Plan: TBD
Status: Phase 5 SHIPPED 2026-05-17 (5 wave commits + executor SUMMARY).
Last activity: 2026-05-17 — Phase 5 (Budget telemetry) executed end-to-end. Latent bug in `agent_sdk.py` token extraction fixed, pricing+budget+orchestrator+CLI wired with 49 new tests. All 249 tests green; ruff/mypy clean on new code. W6–W9 warnings folded in cleanly.

Progress: [██████░░░░] ~63% (5 of 8 phases shipped)

## Performance Metrics

**Velocity (this session):**
- Total commits: 16
- Tests added: 70 → 249 (+179)
- Phases shipped: Phase 2, Phase 3, Phase 4, Phase 5

**By Phase:**

| Phase | Commits | Tests added | Status |
|-------|---------|-------------|--------|
| 1: v1 alpha cut | 7 | 0 → 70 | Shipped (prior session) |
| 2: Hardening + Action | 1 (`48c33e4`) | 70 → 116 | Shipped |
| 3: TypeScript adapter | 4 (`fe041dd`–`8606190`) | 116 → 147 | Shipped |
| 4: `api_reference` | 4 (`bd2144a`–`f99d882`) | 147 → 200 | Shipped |
| 5: Budget telemetry | 5 (`c78c260`–`c70dca7`) | 200 → 249 | Shipped 2026-05-17 |
| 6: `how_to_guides` | — | — | Planned (next) |
| 7: TS api_reference | — | — | Planned |
| 8: Multi-provider backends | — | — | Planned (new) |

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
- Latest commit: `c70dca7` — feat(05-budget): wave 5 — --max-cost flag, DOCAGENT_MAX_COST env, summary
- Repo memory lives at `~/.claude/projects/-home-hayden-DocAgent/memory/` (overview, alpha cut, post-alpha roadmap, architecture, feedback patterns, GitHub references). `.planning/` is a synchronized snapshot derived from those files on 2026-05-16.
