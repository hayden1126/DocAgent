---
phase: 08-multi-provider-backends
plan: 05
status: shipped
shipped_at: 2026-05-17
commit: eae604e
tests_delta: 437 -> 452 (+15)
---

# Phase 8 Plan 05: Close spike gaps + RateLimitError single-retry — Summary

All nine RESEARCH.md Pattern 1 spike-prototype gaps now explicit (most
covered by 08-01/08-03 code; this plan adds regression tests + one new
behavioral change: bounded retry on RateLimitError).

## What landed

- `docagent/backends/litellm_backend.py`:
  - `import time` added at module top.
  - Inside `LiteLLMBackend.run()`, new `except litellm.RateLimitError:`
    branch — `time.sleep(2)`, then retry ONCE. If the retry raises
    again, propagate. **No exponential backoff** (compounding retries
    on rate-limited providers worsen bills, not improve them).
  - `BadRequestError` is NOT caught here — bad input is not transient;
    it bubbles to the orchestrator's per-task exception handler.
  - No broad `except Exception:` introduced (`grep -c 'except
    Exception' docagent/backends/litellm_backend.py == 0`).
- `tests/unit/test_litellm_backend_tool_loop.py`:
  - 4 retry tests: success after one retry (sleep == [2]); failure
    after two RateLimitErrors propagates; BadRequestError no-retry
    (call_count == 1, sleeps == []); AuthenticationError wraps as
    BackendUnavailableError mentioning all three env var names.
  - 1 `tc.model_dump()` contract regression pinned against real
    `litellm.types.utils.ChatCompletionMessageToolCall` (Pitfall 4).
  - 3 usage-shape tests (Pitfall 3): attribute object works, None
    skipped without crash, missing `prompt_tokens` defaults to 0.
  - 3 sandbox-escape: dotdot chain, absolute root, symlink-to-/tmp.
  - 3 edge cases: empty `fn.arguments`, `response.choices=[]` skipped,
    `tool_calls=None` terminates loop.
  - 1 BackendUnavailableError distinction: ImportError flavor vs
    AuthenticationError flavor — both friendly messages, different
    content.

## Verification

- 15 / 15 new tests green.
- 452 / 452 across the full suite (437 + 15).
- `ruff check` clean; `mypy --strict` clean on
  `docagent/backends/litellm_backend.py`.
- Spike gaps closure status (RESEARCH.md Pattern 1):
  - #1 retry on transient → **NEW in this plan**.
  - #2 max-turns exhaust → covered in 08-01.
  - #3 empty assistant message + no tool → covered (loop breaks naturally).
  - #4 tool-call malformed JSON args → covered (json.loads fallback).
  - #5 tool_calls is None → covered (`or []` guard) + new test.
  - #6 missing response.usage → covered in 08-01 + new test.
  - #7 response.choices empty → covered in 08-01 + new test.
  - #8 `tc.model_dump()` future-breakage → **NEW regression test**.
  - #9 `fn.name` is None → ACCEPTABLE per RESEARCH.md (rare and
    would surface as an empty `unknown tool:` dispatch error string;
    not worth additional code).

## Deviations

None.

## Out-of-scope flagged

None.
