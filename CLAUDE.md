# DocAgent
<!-- ground: pyproject.toml:5-5 -->

Claude-specific notes for working on the DocAgent repository documentation agent; see `AGENTS.md` for setup, lint, and project-structure basics. <!-- ground: AGENTS.md:1-12 -->

> Note: this project shares the name "DocAgent" with Meta's [facebookresearch/DocAgent](https://github.com/facebookresearch/DocAgent) ([arXiv 2504.08725](https://arxiv.org/abs/2504.08725)) but is a separate, unaffiliated project (whole-repo doc generation vs. docstring-only). See README's "How we differ" section.

## Quick commands

```bash
pip install -e ".[dev]"                                       # dev install
docagent init                                                 # full pass: scan + index + generate
docagent init --dry-run --only readme                         # preview a single artifact (no write)
docagent update                                               # incremental (needs prior init state)
docagent verify                                               # deterministic-first gate pipeline
pytest -q                                                     # full test suite
```
<!-- ground: pyproject.toml:42-58 --> <!-- ground: docagent/cli.py:195-239 -->

## Where to look

- `docagent/cli.py` — Typer app; commands `init`, `update`, `verify`, plus `--backend agent_sdk|litellm` selection. <!-- ground: docagent/cli.py:224-238 -->
- `docagent/artifacts/builtins.py` — registers v1 artifacts (`readme`, `python_docstrings`, `api_reference`, `how_to_guides`, `agents_md`, `claude_md`, `llms_txt`) via `register_v1_builtins`. <!-- ground: docagent/artifacts/builtins.py:72-86 -->
- `docagent/core/orchestrator.py` — drives `plan → generate → verify → write`; wraps the backend with `_InstrumentedBackend` for budget telemetry. <!-- ground: docagent/core/orchestrator.py:97-127 -->
- `docagent/backends/agent_sdk.py` — `AgentSDKBackend`; read-only tools (Read/Glob/Grep) with `permission_mode="bypassPermissions"`. <!-- ground: docagent/backends/agent_sdk.py:5-11 -->
- `docagent/artifacts/_cleaners.py` — `clean_markdown_output`, `OutputTooSmallError`, `MIN_CLEAN_BYTES` floor. <!-- ground: docagent/artifacts/_cleaners.py:12-75 -->
- `tests/golden/` — recorded-backend snapshot tests; fixtures under `tests/golden/fixtures/tinylib/`. <!-- ground: tests/golden/fixtures/tinylib/pyproject.toml:1-1 -->

## Conventions Claude should follow

- Every non-trivial factual claim in generated Markdown must carry `<!-- ground: path:line-start-line-end -->` immediately after the sentence it grounds; the `citations` gate validates path existence and line ranges. <!-- ground: docagent/backends/agent_sdk.py:43-52 -->
- Do not wrap artifacts in an outer ```markdown fence and do not include preambles like "I'll use the Skill tool…"; `clean_markdown_output` will strip them but the prompts forbid them. <!-- ground: docagent/artifacts/_cleaners.py:1-9 --> <!-- ground: docagent/artifacts/_cleaners.py:38-65 -->
- Top-level artifacts (README, AGENTS.md, CLAUDE.md) must start with a `# ` H1 — the cleaner drops every line before it. <!-- ground: docagent/artifacts/_cleaners.py:59-64 -->
- Bump `PROMPT_VERSION` in `docagent/prompts/<artifact>.py` when changing a prompt; it is folded into the patch digest. <!-- ground: docagent/artifacts/registry.py:25-31 -->
- Snapshot updates are deliberate: run with `UPDATE_SNAPSHOTS=1`, inspect the diff, then commit. <!-- ground: tests/golden/_harness.py:44-50 -->
- Use `from __future__ import annotations` at the top of modules. <!-- ground: docagent/cli.py:3-3 -->
- Use `docagent._logging.get_logger` / `setup_logging` rather than stdlib `logging` directly. <!-- ground: docagent/cli.py:15-15 -->

## Gotchas

- `docagent update` requires a prior `init` to have written `doc_version` into run state; affected-artifact resolution is **not yet wired** — `update` only lists changed files. <!-- ground: docagent/cli.py:146-158 -->
- `docagent verify` currently prints the gate list and notes that gate execution against on-disk artifacts is not yet wired — do not assume failure just because findings are absent. <!-- ground: docagent/cli.py:166-172 -->
- Most v1 artifacts other than `readme`, `agents_md`, `claude_md`, `llms_txt` still emit a placeholder stub (`<!-- docagent: <id> stub. Real generator not yet implemented. -->`). Treat their outputs as scaffolding. <!-- ground: docagent/artifacts/builtins.py:48-58 -->
- `PythonDocstringsArtifact.plan` returns `[]` until the symbol-index query is implemented — wire it via `ctx.store`, not the filesystem. <!-- ground: docagent/artifacts/builtins.py:64-69 -->
- Cleaner has a `MIN_CLEAN_BYTES = 64` floor; outputs below it raise `OutputTooSmallError` so the cache never locks in an over-stripped artifact. <!-- ground: docagent/artifacts/_cleaners.py:12-26 --> <!-- ground: docagent/artifacts/_cleaners.py:66-71 -->
- `.docagent/` is gitignored at the repo root but **un-ignored under `tests/golden/`** — fixture state directories are intentionally committed. <!-- ground: .gitignore:22-23 -->
- The Agent SDK backend wraps an async call synchronously and depends on the local `claude` CLI being on PATH; missing CLI raises `BackendUnavailableError` with an install hint. <!-- ground: docagent/backends/agent_sdk.py:1-11 --> <!-- ground: docagent/backends/agent_sdk.py:25-36 -->
- The soft cost cap (`--max-cost` / `DOCAGENT_MAX_COST`) is a POST-FACT check between artifacts; one artifact may push past the cap before the next iteration's check fires. <!-- ground: docagent/core/orchestrator.py:104-110 -->

## Test invocation

```bash
pytest -q                                                       # all tests
pytest tests/unit -q                                            # unit only
pytest tests/golden/test_readme_snapshot.py -q                  # one snapshot
UPDATE_SNAPSHOTS=1 pytest tests/golden/test_readme_snapshot.py  # re-record
```
<!-- ground: .github/workflows/test.yml:28-29 --> <!-- ground: tests/golden/_harness.py:44-50 -->
