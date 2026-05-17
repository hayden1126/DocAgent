---
phase: 06-how-to-guides-artifact
plan: 02
status: complete
commit: 5cab74d
date: 2026-05-17
tests_added: 13
files_modified:
  - docagent/artifacts/_topic_discovery.py
  - tests/unit/test_topic_discovery.py
---

# Phase 6 Plan 02: _topic_discovery.py Summary

One-liner: Pure-Python `Topic` + `topic_slug()` + `dedupe_topics()` helper module — kebab-case slugger with 60-char cap and `howto-<sha1[:8]>` hash fallback; first-write-wins collision handling with one warn per pair.

## What landed

- `docagent/artifacts/_topic_discovery.py`: frozen `Topic(slug, title, sources)` dataclass; `topic_slug(title)` with the 5 ordered transforms from CONTEXT.md; `dedupe_topics(topics, *, warn)` with FIFO-walk first-write-wins.
- `tests/unit/test_topic_discovery.py`: 13 tests covering all slug rules + 4 dedupe scenarios + frozen-dataclass guard.

## Verification

- `pytest tests/unit/test_topic_discovery.py` → 13 passed.
- `mypy docagent/artifacts/_topic_discovery.py` strict-clean.
- `ruff check` clean on both files.
- `grep "from docagent.verify.links"` on the new module returns nothing — confirms we did not reuse the anchor slugger.

## Deviations from plan

- Test name changed from `test_topic_is_frozen_and_hashable` to `test_topic_is_frozen` and the assertion narrowed to `pytest.raises(AttributeError)` (was `Exception`) to satisfy ruff B017. No behavioral change; frozen dataclasses raise `FrozenInstanceError` which is an `AttributeError` subclass.

## Gotchas

- `Topic.sources` is `list[str]` (mutable), so `Topic` is **frozen but not hashable** despite the `@dataclass(frozen=True)` decorator. Per Plan 05, dedup keys by slug (via dict), not by Topic-hash — this is fine. If a future caller needs hashing, switch `sources` to `tuple[str, ...]`.

## Threat flags

None.

## Self-Check: PASSED
