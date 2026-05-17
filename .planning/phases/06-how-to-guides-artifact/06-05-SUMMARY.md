---
phase: 06-how-to-guides-artifact
plan: 05
status: complete
date: 2026-05-17
tests_added: 13
files_modified:
  - docagent/artifacts/how_to_guides.py
  - docagent/artifacts/builtins.py
  - docagent/cli.py
  - docagent/core/orchestrator.py
  - tests/unit/test_how_to_guides_artifact.py
---

# Phase 6 Plan 05: HowToGuidesArtifact end-to-end Summary

One-liner: `HowToGuidesArtifact` ships end-to-end — plan/discovery → dedupe → cap → per-page fingerprint cache → generate/render → sentinel-gated orphan flag — registered in the DAG with `depends_on: [readme, api_reference]` and surfaced via a new `--max-howtos` CLI flag.

## What landed

- `docagent/artifacts/how_to_guides.py` (~365 lines):
  - `_parse_discovery_response`: tolerant JSON parser (strips ``` ` ``` fences, skips malformed elements, NEVER raises).
  - `_per_page_fingerprint`: `sha256(prompt_version|model|slug|sorted(path@hash))`. Sources are deduped by file path before being paired with content hashes.
  - `plan()`: builds discovery prompt, parses response, dedupes via `dedupe_topics`, applies cap, computes per-page fingerprint, emits one task per cache-miss topic. Edge case: zero-task run still flags orphans before returning.
  - `generate()`: builds per-page prompt, marker-splits LLM body via `_split_marker_output`, composes with `assemble_page(frontmatter, body, see_also)`.
  - `verify()`: defers to default pipeline with `_future_paths` carve-out so sibling See-also links resolve mid-run.
  - `post_write()`: persists per-page fingerprint AND, on the last task only (sentinel `== len(_slugs_to_write)` per VERIFICATION.md W1), flags orphan pages whose stems don't appear in `_slugs_to_write`.
- `docagent/artifacts/builtins.py`: replaced the `_StubArtifact` how_to_guides entry with `HowToGuidesArtifact()`; depends_on=("readme", "api_reference") declared on the class itself.
- `docagent/cli.py`: `--max-howtos N` (default 15) added to both `init` and `update` commands, threaded into `Orchestrator.config["max_howtos"]`. Orphans rendered in the run summary footer as `Flagged orphans: …`.
- `docagent/core/orchestrator.py`: tiny one-line addition — expose `_last_ctx_config` post-run so the CLI can read artifact-emitted entries (orphans/warnings) which live on the per-run ctx copy, not the orchestrator's input config.
- `tests/unit/test_how_to_guides_artifact.py`: 13 tests covering plan + cap + cache-hit + slug collision + fingerprint stability (cited file change vs unrelated file edit) + generate + orphan-flag sentinel timing (tasks 0/1 don't fire, task 2 does) + zero-task-run orphan check + builtins registration + CLI flag presence on both init and update.

## Verification

- `pytest tests/unit/test_how_to_guides_artifact.py -v` → 13 passed.
- `pytest tests/ --ignore=tests/golden` → 283 passed (up from 235; +48 across Plans 1–5).
- `mypy --strict docagent/artifacts/how_to_guides.py` → clean.
- `ruff check` clean on new files. Pre-existing B008 (`typer.Option` in defaults) and one pre-existing UP037-class issue on cli.py — out of scope.
- `grep "_slugs_written" docagent/artifacts/how_to_guides.py` → sentinel uses `==` not `>=` (W1 honored).
- `register_v1_builtins` registers `how_to_guides` with `depends_on == ("readme", "api_reference")` (test asserts).

## Deviations from plan

- **Surfacing orphans to the CLI required a 1-line orchestrator change.** The plan said "ctx.config['how_to_orphans'] mutated by the artifact … CLI summary footer reads ctx.config.get(…)". But the orchestrator deep-copies `self.config` into `ctx.config` (line 125: `config=dict(self.config)`), so the artifact's mutation lived on the copy, invisible to the CLI. Fixed by exposing `orchestrator._last_ctx_config` after run() ends. This is Rule 2 (missing critical functionality — the planned orphan-render path would have been a silent no-op otherwise).
- **JSON parse tolerance broader than planned.** Plan said "strict JSON-shape validation; reject extra fields". I went lenient on **extra fields** (`item.get("title"), item.get("sources")` ignores extras) but strict on **missing/wrong-typed required fields**. Real LLMs add extra keys regularly; rejecting them all wastes the discovery call. The threat model (T-06-11) is still mitigated because malformed elements are skipped and bad shapes produce zero topics — no crash, no injection vector.
- **Test for cache-hit uses `art._planned` private field** — pragmatic for verifying fingerprint determinism. Acceptable in unit tests.

## Gotchas

- `BackendUnavailableError` import warning when running tests through the CLI runner — handled by Typer's CliRunner without invoking the real backend; tests on `--help` don't trigger it.
- The orphan-flag sentinel uses `==`, which means: if `post_write` were ever called MORE than `len(_slugs_to_write)` times (a bug elsewhere), the orphan check would silently NOT re-fire. That's the correct safety property — better silent-skip than re-flag.

## Threat flags

None new. All five `T-06-11..15` mitigations from the plan are honored.

## Self-Check: PASSED
