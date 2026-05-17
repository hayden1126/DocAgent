---
phase: 06-how-to-guides-artifact
status: SHIPPED
date_completed: 2026-05-17
requirements_satisfied: [HOWTO-01]
plans_total: 6
plans_complete: 6
test_count_delta: 249 → 304 (+55)
commits:
  - 3dbeab7  # 06-01: P0 orchestrator drain
  - 5cab74d  # 06-02: _topic_discovery
  - afaba29  # 06-03: _how_to_render
  - 55b4951  # 06-04: prompt module
  - 3552caa  # 06-05: HowToGuidesArtifact end-to-end
  - 537e455  # 06-06: RecordedBackend queue + snapshot
---

# Phase 6: `how_to_guides` artifact — SHIPPED

One-liner: First DAG-dependent multi-file artifact ships end-to-end. LLM topic discovery → per-page generation with deterministic frontmatter/See-also wrappers → per-page fingerprint cache → orphan flagging with a `==` sentinel. P0 orchestrator token-attribution bug discovered during research and fixed first. 6 commits, +55 tests, all green.

## Commits

```
537e455  feat(06-06): RecordedBackend queue + how_to_guides golden snapshot
3552caa  feat(06-05): HowToGuidesArtifact end-to-end (HOWTO-01)
55b4951  feat(06-04): discovery + per-page prompts for how_to_guides
afaba29  feat(06-03): deterministic render helpers for how_to_guides
5cab74d  feat(06-02): topic_slug + dedupe_topics for how_to_guides
3dbeab7  fix(06-01): attribute plan() backend tokens to run.* (P0)
```

## Test count delta

249 → 304 (+55), broken down:
- 06-01: +3 (regression tests for plan-call token attribution)
- 06-02: +13 (slug rules + dedupe semantics)
- 06-03: +12 (frontmatter/see-also/assemble + determinism)
- 06-04: +10 (prompt-shape invariants + title-injection guard)
- 06-05: +13 (artifact end-to-end: plan/cap/cache-hit/collision/fingerprint/generate/orphan sentinel/zero-task fallback/CLI help)
- 06-06: +2 golden + multi-call backend coverage

Full `pytest tests/` suite green: **304 passed**, no skips.

## Deviations from PLAN.md (worth recording)

1. **W1 (sentinel `==` not `>=`) — honored.** Plan 06-05's implementation uses `==` exactly. Defensive: any post_write past `len(_slugs_to_write)` is a bug elsewhere and should silent-skip, not re-fire the orphan check.

2. **W2 (test_readme_snapshot.py listed but unmodified) — confirmed.** Plan 06-06 references the readme snapshot test only as a backwards-compat guard. The file was NOT modified; the recorded-backend extension keeps the legacy `recording_path` path working and the readme tests prove it.

3. **CLI orphan surfacing required a 1-line orchestrator change** (Plan 06-05). The original plan said "ctx.config['how_to_orphans']" → "CLI reads ctx.config.get(…)" but the orchestrator deep-copies `self.config` into `ctx.config`, so mutations on the ctx side were invisible to the CLI. Fixed by exposing `orchestrator._last_ctx_config` after `run()`. This is the kind of "missing critical functionality" Rule 2 covers — the planned orphan-render path would have been a silent no-op otherwise.

4. **Prompt rewording during TDD** (Plan 06-04). The "forbid `## See also`" test caught a real ambiguity: the prompt body said "the '## See also' block" in instructions. Reworded to "a related-links block" so the literal token only appears in the explicit forbid line.

5. **Tinylib fixture didn't have README.md or docs/reference/** (Plan 06-06). The plan assumed Phase 4's `api_reference` had populated them on disk. It hadn't (those live under `tests/golden/recordings/`, not the fixture itself). The snapshot test now seeds both inside `tmp_path` with line content matching the citation ranges in the recordings. Cleaner than baking a synthetic README into the fixture.

6. **Lenient JSON parser tolerance broader than planned** (Plan 06-05). Plan said "strict JSON-shape validation; reject extra fields". Real LLMs add extra keys regularly; rejecting all of them would waste discovery calls. The parser is strict on required-fields-present-and-correctly-typed, lenient on unknown extras. The threat model (T-06-11) is still mitigated because malformed elements are skipped → zero topics → no injection vector.

## Gotchas (newly discovered)

- `BackendUnavailableError` import in CLI runner tests doesn't hit the real backend — Typer's `CliRunner` short-circuits at `--help`.
- The marker pair `<<<HOWTO_PAGE_BEGIN>>>` / `<<<HOWTO_PAGE_END>>>` is non-negotiable for clean body extraction. `_split_marker_output` falls back to whole-text-stripped on missing markers, which would leak the literal `<<<` strings into the page body.
- Snapshot determinism depends on `RecordedBackend.model = "claude-sonnet-4-6"` because the per-page fingerprint includes model name. Today no test compares fingerprints across snapshots, but it's a load-bearing default.
- `Topic` is `@dataclass(frozen=True)` but **not hashable** because `sources: list[str]` is mutable. Dedup keys by slug via a dict — never put Topics in a set.
- Phase 6 ships ONE `PROMPT_VERSION` covering both discovery and per-page prompts. Bump it and EVERY how-to fingerprint invalidates. This is intentional coupling; do not split.

## Phase 5 known-issue list status

Re-checked Phase 5's known issues. No items added; one effectively addressed:
- **P0 token-attribution bug** (Phase 5 latent): plan-call tokens were being dropped by the per-task `last_responses.clear()`. Fixed in Plan 06-01. This was technically a Phase 5 leak surfaced by Phase 6's design (first artifact to make LLM calls inside `plan()`). The Phase 5 known-issue list net shrank by 1.

No other Phase 5 issues regrew. The `--max-cost` contract is now provably correct end-to-end for plan-call-producing artifacts.

## Verification gate (final)

- `pytest tests/` → 304 passed, 0 failed, 0 skipped.
- `mypy --strict` clean on all Phase 6 new modules (`_topic_discovery.py`, `_how_to_render.py`, `how_to_guides.py`, `prompts/how_to_guides.py`).
- `ruff check` clean on all Phase 6 new files. Pre-existing B008 (typer.Option in defaults) on cli.py + builtins.py UP032 are out of scope.
- `docagent init --help | grep max-howtos` → `--max-howtos N`.
- `docagent update --help | grep max-howtos` → `--max-howtos N`.
- `register_v1_builtins(reg).get("how_to_guides").depends_on == ("readme", "api_reference")`.
- `grep "_slugs_written ==" docagent/artifacts/how_to_guides.py` → 1 match (W1 honored).

## What ships now

A user running `docagent init --only how_to_guides` on a repo with a README + `docs/reference/*.md` set will:
1. Get a single discovery LLM call (cost attributed correctly to `run.*`).
2. Get one LLM call per discovered, cache-missed topic (capped at `--max-howtos`, default 15).
3. See per-page progress lines and a final budget summary.
4. See `Flagged orphans: docs/how-to/<slug>.md (source removed)` if any prior pages no longer have discovered topics.

The verifier passes 0 on the generated pages because every imperative step carries `<!-- ground: path:start-end -->` per the prompt contract, and sibling See-also links resolve via the `_future_paths` carve-out during the same run.

## Next phase

Phase 7 (TypeScript `api_reference`) — ready to plan. No blocking dependencies; Phase 4's `api_reference` shape transfers directly with a TS module-discovery swap.
