---
phase: 06-how-to-guides-artifact
plan: 03
status: complete
commit: HEAD~0
date: 2026-05-17
tests_added: 12
files_modified:
  - docagent/artifacts/_how_to_render.py
  - tests/unit/test_how_to_render.py
---

# Phase 6 Plan 03: _how_to_render.py Summary

One-liner: Pure deterministic rendering helpers — frontmatter + see-also block + page assembler — with module/sibling sorting and exactly-one-trailing-newline guarantee.

## What landed

- `docagent/artifacts/_how_to_render.py` exports `render_frontmatter`, `render_see_also`, `assemble_page`. Modeled on `_api_reference_render.py`'s pure-function style; no I/O, no LLM, stdlib-only.
- Frontmatter shape: `title` quoted, `slug` unquoted, plus `docagent_artifact: how_to_guides` so the writer can recognize DocAgent-owned files later.
- See-also: modules first (sorted) using `../reference/<dotted>.md`, then sibling how-to slugs (sorted) using `./<slug>.md`. Empty inputs → empty string.
- assemble_page: filters empty chunks, joins with `\n\n`, guarantees exactly one trailing newline.
- 12 tests covering link form, sorting, determinism, and trailing-newline invariants.

## Verification

- `pytest tests/unit/test_how_to_render.py` → 12 passed.
- `mypy --strict` clean.
- `ruff check` clean.
- `grep -c 'os.sep\|os.path.join' docagent/artifacts/_how_to_render.py` → 0 (POSIX-only output).

## Deviations from plan

- Frontmatter is non-empty (returns the YAML block) — plan said `render_frontmatter` "may return '' for v1". I chose to emit the block; it's harmless and `assemble_page` handles empty correctly anyway, so callers can override.

## Threat flags

None.

## Self-Check: PASSED
