---
phase: 06-how-to-guides-artifact
plan: 01
status: complete
commit: 3dbeab7
date: 2026-05-17
tests_added: 3
tests_passing: 235 (full unit suite, ignore=tests/golden)
files_modified:
  - docagent/core/orchestrator.py
  - tests/unit/test_orchestrator_token_attribution.py
---

# Phase 6 Plan 01: P0 token-attribution fix Summary

One-liner: Drain `last_responses` between `artifact.plan()` and the per-task loop so discovery-call tokens are attributed to `run.*` and `BudgetTracker`, restoring the `--max-cost` contract.

## What landed

- **Drain block** in `Orchestrator.run()` between `tasks = artifact.plan(ctx)` and `multi_task = ...`. Iterates ALL entries in `last_responses` (future-proofing for plan() with multiple calls), pushes each into `self.tracker.add(...)`, accumulates into `run.input_tokens / output_tokens / tool_calls / cost_usd`, then clears the sink. Skipped under `dry_run=True` to match per-task drain semantics.
- **Regression test** (`tests/unit/test_orchestrator_token_attribution.py`): three tests covering plan+generate, plan-only, and the noisy-prior-then-raise sink-leak guard.

## Verification

- `pytest tests/unit/test_orchestrator_token_attribution.py -x` → 3 passed.
- `pytest tests/ -x --ignore=tests/golden` → 235 passed.
- `ruff check` clean on both touched files.
- `mypy docagent/core/orchestrator.py` clean.

## Deviations from plan

- Test file used `dataclass` only (not `dataclass, field`) — minor import cleanup to satisfy ruff. No behavioral deviation.
- Drain block respects `dry_run` (skips `tracker.add` mirroring the per-task drain). Plan didn't explicitly call this out but consistency with the existing per-task drain implies it; otherwise `--dry-run` would over-attribute.

## Gotchas

- The noisy-prior-then-raise test exercises BOTH the new drain block AND the pre-existing W7 top-of-loop clear; together they guarantee a plan-call leak from a prior artifact's error path cannot contaminate the next artifact's accounting.

## Threat flags

None.

## Self-Check: PASSED
