---
phase: 06-how-to-guides-artifact
plan: 04
status: complete
date: 2026-05-17
tests_added: 10
files_modified:
  - docagent/prompts/how_to_guides.py
  - tests/unit/test_how_to_guides_prompts.py
---

# Phase 6 Plan 04: how_to_guides prompt module Summary

One-liner: One `PROMPT_VERSION = "1"` covers BOTH discovery and per-page prompts (intentional coupling); discovery emits JSON, per-page produces Diátaxis H1+Goal+Steps+Verify(+Troubleshoot) with grounding directives.

## What landed

- `docagent/prompts/how_to_guides.py`: `PROMPT_VERSION`, `HEADER_MARKER`/`FOOTER_MARKER`, `build_discovery_prompt`, `build_page_prompt`.
- Discovery prompt: cites README + reference paths, returns JSON `[{title, sources}]`, mentions `max_topics` cap, instructs imperative verb-noun titles (rejects noun-phrase "Introduction to" drift).
- Per-page prompt: marker-split body (matches RESEARCH.md Pattern 2). Required sections H1+`## Goal`+`## Steps`+`## Verify`+optional `## Troubleshoot`. Explicit forbid on `## See also` and frontmatter.
- Defense against title-injection: `_sanitize_title` collapses newlines/tabs/runs of whitespace to single spaces. Tested.
- `tests/unit/test_how_to_guides_prompts.py`: 10 tests covering version, source citation, max-topics, no-markdown-instruction (discovery), required sections, See-also-forbid, title+source embedding, conditional Troubleshoot, determinism, title-injection guard.

## Verification

- `pytest tests/unit/test_how_to_guides_prompts.py` → 10 passed.
- `mypy --strict` clean.
- `ruff check` clean.
- `grep -c "PROMPT_VERSION" docagent/prompts/how_to_guides.py` → 1 declaration.
- `grep "See also" docagent/prompts/how_to_guides.py` → only in forbid-context lines.

## Deviations from plan

- The TDD "See also forbid" test initially caught a real ambiguity: the prompt body said "the '## See also' block" in instructions. Reworded to "a related-links block" so the literal `## See also` only appears in the explicit forbid line. **This is a useful catch — the test was right, the prompt was leaking the section name into a non-forbid sentence.**

## Threat flags

None — title sanitization mitigates T-06-09 (prompt injection via LLM-discovered titles).

## Self-Check: PASSED
