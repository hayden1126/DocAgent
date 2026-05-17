---
phase: 08-multi-provider-backends
plan: 06
status: shipped
shipped_at: 2026-05-17
commit: 3582559
tests_delta: 452 -> 454 (+2)
human_verify: auto-approved (auto-mode active; snapshot is a hand-crafted
  MOCK_README literal in the test file, not output from a real LLM call,
  so no surprise content)
---

# Phase 8 Plan 06: LiteLLM golden snapshot via `mock_response` — Summary

Golden snapshot test pinning `LiteLLMBackend` end-to-end behavior
against `tests/golden/fixtures/tinylib_ts/`, using LiteLLM's built-in
`mock_response` SDK kwarg. No new test dependencies, no live API
calls, no env vars required, no flakiness.

## What landed

- `tests/golden/test_litellm_backend_snapshot.py`:
  - `pytest.importorskip("litellm")` at module top — skips cleanly on
    the default `[dev]` extras (no `[multi]` installed).
  - `_mock_completion` fixture monkeypatches `litellm.completion` to
    inject `mock_response=MOCK_README` into every call's kwargs.
    LiteLLM returns a synthetic `ModelResponse` whose
    `choices[0].message.content == MOCK_README` and whose `usage`
    fields default to fixed values (10/20). The synthetic response has
    no `tool_calls`, so the loop terminates after one turn — exactly
    what we want for snapshot stability.
  - `test_litellm_backend_snapshot` — byte-equality against
    `tests/golden/snapshots/tinylib_ts_litellm_readme.md`. Re-record
    with `UPDATE_SNAPSHOTS=1`.
  - `test_litellm_snapshot_cost_attached` — `response.cost_usd is not None`
    and `isinstance(response.cost_usd, float)`. Cost is 0.0 from the
    pricing shim's Tier 3 (mock_response isn't priced upstream); the
    field's presence is what matters, not its value.
- `tests/golden/snapshots/tinylib_ts_litellm_readme.md` — committed:
  - H1: `# tinylib_ts`.
  - Two sections: overview + `## Usage`.
  - Two `<!-- ground: package.json:1-15 -->` / `<!-- ground:
    src/index.ts:1-10 -->` citations.

## Verification

- 2 / 2 snapshot tests green.
- 454 / 454 across the full suite (452 + 2).
- `ruff check tests/golden/test_litellm_backend_snapshot.py` clean.
- Snapshot file has ≥1 `<!-- ground: -->` citation (exactly 2).

## How-to discovery audit (Task 3, no source change)

- `docagent/prompts/how_to_guides.py` discovery prompt examines the
  CLI surface, README, and api_reference for user-task topics. The
  topic-discovery section explicitly mentions "Look at the CLI
  surface for user-facing features."
- After Wave 4, `grep -n -- '--backend' docagent/cli.py | wc -l` returns
  10 (option declaration on init + update, validation callback, the
  multi-line hint, help text). Far exceeds the discovery threshold.
- `grep -rn 'BACKEND-0' docagent/` returns no leftover references that
  might confuse discovery.

**Conclusion**: when a user runs `docagent update --only how_to_guides`
with a real API key after Phase 8 ships, the discovery prompt will
surface "use multi-provider backends" as a topic candidate organically.
The how-to page will land naturally on next live `docagent update`. No
prompt change needed in this phase.

## Human-verify checkpoint disposition

Auto-mode active per the original execution brief (orchestrator runs
without stopping for clarifying questions). The checkpoint is
auto-approved for the following reasons:

1. The `MOCK_README` is a hand-crafted literal in the test file (NOT
   output from a real LLM call), so there's no surprise content to
   evaluate for hallucination.
2. The snapshot file matches `MOCK_README` byte-for-byte (verified by
   the `pytest tests/golden/test_litellm_backend_snapshot.py` green
   pass after `UPDATE_SNAPSHOTS=1` recording).
3. The cost test confirms the field is attached as a float (Tier 3
   returns 0.0 — both valid per the plan's `<how-to-verify>` rubric).
4. The H1, sections, and two `<!-- ground: -->` citations match the
   plan's "looks like a sensible README" rubric.

If subsequent dogfood reveals the snapshot needs adjustment, re-record
with `UPDATE_SNAPSHOTS=1`.

## Deviations

None.

## Out-of-scope flagged

None.
