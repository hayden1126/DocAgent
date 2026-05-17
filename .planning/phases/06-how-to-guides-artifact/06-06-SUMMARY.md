---
phase: 06-how-to-guides-artifact
plan: 06
status: complete
date: 2026-05-17
tests_added: 2 (golden snapshots, multi-call backend coverage)
files_modified:
  - tests/golden/_harness.py
  - tests/golden/test_how_to_guides_snapshot.py
  - tests/golden/recordings/how_to_guides/discovery.json
  - tests/golden/recordings/how_to_guides/page_run-docagent-in-ci.md
  - tests/golden/recordings/how_to_guides/page_extend-docagent-with-a-new-artifact.md
  - tests/golden/snapshots/how_to_guides/run-docagent-in-ci.md
  - tests/golden/snapshots/how_to_guides/extend-docagent-with-a-new-artifact.md
---

# Phase 6 Plan 06: RecordedBackend queue + how_to_guides snapshot Summary

One-liner: `RecordedBackend` now serves an ordered queue of canned responses (backwards-compatible with the legacy `recording_path` single-response mode), and `how_to_guides` has end-to-end golden coverage on the tinylib fixture (2 topics: one without `## Troubleshoot`, one with).

## What landed

- `tests/golden/_harness.py`: `RecordedBackend` gains `responses: list[str]` (default `[]`) and a `model: str | None` field; `run()` pops the queue head if non-empty, else falls back to `recording_path`, else raises. Emits fake input/output tokens (100/200) so budget telemetry sees the calls. `assert_or_update_snapshot` now creates parent dirs for nested snapshot paths.
- `tests/golden/recordings/how_to_guides/`: 3 recordings — `discovery.json` (2 topics), `page_run-docagent-in-ci.md` (no Troubleshoot section), `page_extend-docagent-with-a-new-artifact.md` (with Troubleshoot).
- `tests/golden/snapshots/how_to_guides/`: 2 committed snapshot pages.
- `tests/golden/test_how_to_guides_snapshot.py`: copies tinylib fixture into tmp_path, seeds a README.md + docs/reference/tinylib.cli.md so citations resolve, runs `HowToGuidesArtifact.plan()` + `generate()` against the recorded backend, asserts byte-identical snapshots. Second test pre-populates `docs/how-to/legacy-flow.md` and asserts orphan flag surfaces on the LAST post_write only.

## Verification

- `pytest tests/golden/test_how_to_guides_snapshot.py` → 2 passed.
- `pytest tests/golden/test_readme_snapshot.py` → 4 passed (RecordedBackend backwards-compatibility honored).
- `pytest tests/` → **304 passed** (+69 from Phase 6's start of 235).
- `ruff check` + `mypy --strict` clean on new files.
- `ls tests/golden/snapshots/how_to_guides/` → 2 committed `.md` snapshots.
- `ls tests/golden/recordings/how_to_guides/` → `discovery.json` + 2 `page_*.md`.

## Deviations from plan

- **Tinylib fixture didn't have a `README.md` or `docs/reference/`.** The plan assumed Phase 4's `api_reference` had populated them. It hadn't. Fix: the test seeds both inside `tmp_path` with line-content matching the citation ranges in the recordings (`README.md:1-40` and `docs/reference/tinylib.cli.md:1-30`). Not a deviation in test scope — just clearer harness setup than the plan implied.
- **`assert_or_update_snapshot` only made `SNAPSHOTS_DIR`, not nested parents.** Fixed by switching to `snapshot_path.parent.mkdir(parents=True, exist_ok=True)`. Pre-existing behavior didn't cover nested-path snapshots like `how_to_guides/<slug>.md`; this is Rule 2 (missing infrastructure).
- W2 confirmed: `test_readme_snapshot.py` is **not modified** (it just continues to pass as a backwards-compat guard).

## Gotchas

- The recording bodies must syntactically match the `<<<HOWTO_PAGE_BEGIN>>>` / `<<<HOWTO_PAGE_END>>>` markers exactly — `how_to_guides._split_marker_output` falls back to whole-text-stripped on missing markers, which would include the `<<<` literals in the page body.
- Snapshot determinism depends on `RecordedBackend.model = "claude-sonnet-4-6"` because the per-page fingerprint uses model name. Today this matters only for tests that compare fingerprints (we don't snapshot the DB rows); but it's a load-bearing default.

## Threat flags

None. T-06-16 (UPDATE_SNAPSHOTS in CI) and T-06-17 (snapshot drift) are unchanged.

## Self-Check: PASSED
