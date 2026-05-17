---
phase: 08-multi-provider-backends
plan: 01
status: shipped
shipped_at: 2026-05-17
commit: b0fe3ae
tests_delta: 385 -> 385 (no new tests; port + polish only)
---

# Phase 8 Plan 01: Port LiteLLMBackend prototype to main — Summary

Brought `docagent/backends/litellm_backend.py` from `spike/phase-8-litellm`
onto `main` with five polish deltas folded in. No CLI wiring, no
pricing shim, no allowlist gate — those land in 08-02 through 08-06.

## What landed

- `docagent/backends/litellm_backend.py` — promoted from spike with:
  - Module-load logger silencer: `logging.getLogger("LiteLLM").setLevel(logging.ERROR)` hides Bedrock/SageMaker pre-load WARNs (Pitfall 6).
  - `litellm.AuthenticationError` wrapped as `BackendUnavailableError` with the multi-provider env-var hint (GEMINI / OPENROUTER / ANTHROPIC API keys).
  - `if not response.choices: continue` defensive guard before reading `response.choices[0]` (Pattern 1 gap #7).
  - `else:` clause on the `for _turn in range(self.max_turns)` loop emits a `max_turns=N exhausted` WARN (Pattern 1 gap #2).
  - Docstring rewritten to drop the "spike" framing; Ollama dropped from the example list (deferred to v1.1).
- `pyproject.toml`:
  - `pydantic>=2.7` → `pydantic>=2.10` (LiteLLM 1.85 floor; Pitfall 5).
  - New `[project.optional-dependencies]` `multi = ["litellm>=1.50"]`.
  - `[[tool.mypy.overrides]]` for `litellm.*` with `ignore_missing_imports = true`, `disallow_untyped_defs = false`.
- `scripts/measure_citation_rate.py` — renamed from `scripts/spike_phase8_citation_rate.py` (via `git mv`); docstring updated to "permanent measurement tool" framing; Ollama example dropped from the Usage block.

## Verification

- `pip install -e ".[multi]"` resolves cleanly; `litellm 1.85.0` + `pydantic 2.13.x` co-install with `claude-agent-sdk 0.2.x`.
- `python -c "from docagent.backends.litellm_backend import LiteLLMBackend; b = LiteLLMBackend(model='anthropic/claude-sonnet-4-6'); print(b.name, b.model, b.max_turns)"` prints `litellm anthropic/claude-sonnet-4-6 24`.
- Module top-level import succeeds without `litellm` installed (lazy import inside `run()` only).
- `ruff check docagent/backends/litellm_backend.py` clean; `mypy --strict docagent/backends/litellm_backend.py` clean.
- 385 baseline tests still green.

## Deviations

None beyond the locked five polish deltas. Spike file ported verbatim
otherwise.

## Out-of-scope flagged

`docagent/backends/litellm_backend.py` carries one `# type: ignore[attr-defined]`
on the `except litellm.AuthenticationError as exc:` line. Reason: mypy's
override allows missing imports for `litellm.*` but still flags
`Module "litellm" does not explicitly export attribute "AuthenticationError"`.
The override is for missing stubs, not for explicit-export tracking. The
inline `type: ignore` is the minimal fix and stays local to that line.
