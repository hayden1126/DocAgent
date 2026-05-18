# DocAgent

Repository documentation agent that generates and verifies grounded docs (README, AGENTS.md, CLAUDE.md, llms.txt, API reference, how-to guides) for humans and coding agents. <!-- ground: pyproject.toml:5-13 -->

## Setup

Python 3.11 or 3.12 required. <!-- ground: pyproject.toml:11-11 --> Install in editable mode with dev extras:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```
<!-- ground: .github/workflows/test.yml:24-26 -->

The optional multi-provider backend lives behind the `multi` extra (pulls in LiteLLM). <!-- ground: pyproject.toml:50-55 -->

```bash
pip install -e ".[dev,multi]"
```

## Run

DocAgent is a Typer CLI exposed as the `docagent` console script. <!-- ground: pyproject.toml:57-58 --> Top-level commands are `init`, `update`, and `verify`. <!-- ground: docagent/cli.py:195-518 -->

```bash
docagent init           # generate documentation artifacts
docagent update         # refresh affected artifacts after source changes
docagent verify         # check ground citations, links, secrets, markdownlint
```

The repo also ships a composite GitHub Action wrapping `docagent verify`. <!-- ground: action.yml:1-9 -->

Backend selection: default is the Claude Agent SDK; pass `--backend litellm --model <provider/model>` for Gemini / OpenRouter / Anthropic-direct. <!-- ground: docagent/cli.py:26-59 -->

## Test

Run the full suite with pytest:

```bash
pytest -q
```
<!-- ground: .github/workflows/test.yml:28-29 -->

Focused run by node id (file, class, or test function):

```bash
pytest tests/unit/test_citations_grammar.py -q
pytest tests/unit/test_orchestrator_budget.py -q
```

Tests live under `tests/unit/`, `tests/integration/`, and `tests/golden/` (snapshot fixtures in `tests/golden/fixtures/` and `tests/golden/snapshots/`). <!-- ground: tests/golden/fixtures/tinylib/pyproject.toml:1-1 -->

## Lint and format

Ruff is the linter/formatter, line length 100, target `py311`, rule set `E, F, I, B, UP, SIM, RUF` with `E501` ignored. <!-- ground: pyproject.toml:67-73 --> mypy runs in strict mode with `warn_return_any = false`. <!-- ground: pyproject.toml:75-78 --> Markdown is linted via `pymarkdownlnt` (also wired into the verifier). <!-- ground: pyproject.toml:48-48 -->

```bash
ruff check .
ruff format .
mypy docagent
```

No pre-commit config is checked in. CI runs `pytest` on push/PR <!-- ground: .github/workflows/test.yml:1-29 --> and `docagent verify` against its own docs via the local Action. <!-- ground: .github/workflows/verify.yml:1-27 -->

## Project structure

- `docagent/` — Python package; CLI entry at `docagent/cli.py`. <!-- ground: docagent/cli.py:1-3 -->
- `docagent/artifacts/` — one module per generated artifact (`readme.py`, `agents_md.py`, `claude_md.py`, `llms_txt.py`, `api_reference.py`, `how_to_guides.py`) plus the `Registry` and DAG plumbing. <!-- ground: docagent/artifacts/registry.py:1-1 -->
- `docagent/backends/` — LLM backends: `agent_sdk.py` (default) and `litellm_backend.py` (multi-provider). <!-- ground: docagent/backends/agent_sdk.py:1-1 -->
- `docagent/adapters/`, `docagent/parser/` — language adapters (`python.py`, `typescript.py`, `fallback.py`) and tree-sitter parser. <!-- ground: docagent/adapters/python.py:1-1 -->
- `docagent/verify/` — verification gates: `citations.py`, `links.py`, `secrets.py`, `markdownlint.py`, `judge.py`, `pipeline.py`. <!-- ground: docagent/verify/pipeline.py:1-1 -->
- `docagent/core/` — orchestrator, budget tracker, scanner, state, diff, paths. <!-- ground: docagent/core/orchestrator.py:1-1 -->
- `docagent/index/` — SQLite-backed code index (`store.py`, `mentions.py`). <!-- ground: docagent/index/store.py:1-1 -->
- `tests/` — `unit/`, `integration/`, `golden/` (snapshot-based). <!-- ground: tests/golden/test_readme_snapshot.py:1-1 -->
- `action.yml` — composite GitHub Action wrapping `docagent verify`. <!-- ground: action.yml:41-91 -->

## Conventions

- Line length 100; ruff target Python 3.11; rule set `E, F, I, B, UP, SIM, RUF` with `E501` ignored. <!-- ground: pyproject.toml:67-73 -->
- mypy strict, but `warn_return_any = false`; the `litellm` import override allows missing stubs and untyped defs only inside that override. <!-- ground: pyproject.toml:75-85 -->
- Use `from __future__ import annotations` at the top of modules. <!-- ground: docagent/cli.py:3-3 -->
- Logging: use `docagent._logging.get_logger` / `setup_logging` rather than the stdlib `logging` module directly. <!-- ground: docagent/cli.py:15-15 -->
- Every documentation claim carries an HTML ground comment of the form `<!-- ground: path:start-end -->`; this is enforced by the verifier. <!-- ground: action.yml:2-6 -->
- Artifacts declare DAG dependencies and are registered through `Registry` / `register_v1_builtins`. <!-- ground: docagent/cli.py:16-17 -->

## Boundaries

- `.venv/`, `__pycache__/`, `build/`, `dist/`, `*.egg-info/` — gitignored build/runtime artifacts; never commit. <!-- ground: .gitignore:1-9 -->
- `.docagent/` — runtime state (SQLite store, caches); gitignored except inside golden fixtures. <!-- ground: .gitignore:22-23 -->
- `tests/golden/snapshots/` — generated snapshot expectations; regenerate via the golden-test harness rather than hand-editing. <!-- ground: tests/golden/_harness.py:1-1 -->
- `.planning/` ADRs once merged — append a new ADR rather than rewriting an existing one. <!-- ground: pyproject.toml:52-52 -->

## Tasks to avoid

- Do not import `litellm` unconditionally — it is gated behind the `[multi]` extra and may be absent; route through `docagent/backends/litellm_backend.py` and respect the mypy override. <!-- ground: pyproject.toml:50-85 -->
- Do not edit docs without their `<!-- ground: ... -->` citations — `docagent verify` fails the build on broken grounding, dead links, or leaked secrets. <!-- ground: .github/workflows/verify.yml:1-13 -->
- Do not flip the CI Action to `strict: 'true'` casually — it deliberately runs non-strict to keep markdownlint nits and judge `skipped` non-blocking. <!-- ground: .github/workflows/verify.yml:24-27 -->
