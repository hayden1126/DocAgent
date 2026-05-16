# DocAgent
<!-- ground: pyproject.toml:6-6 -->

Repository documentation agent for humans and coding agents; Python ≥ 3.11, Typer CLI, Claude Agent SDK backend. <!-- ground: pyproject.toml:8-11 --> <!-- ground: docagent/backends/agent_sdk.py:1-11 -->

No `AGENTS.md` exists at the repo root yet — `agents_md` is itself one of the artifacts this repo generates. <!-- ground: docagent/artifacts/builtins.py:96-96 -->

## Quick commands

```bash
pip install -e ".[dev]"             # dev install (ruff, mypy, pytest)
docagent init                        # full pass: scan + index + generate
docagent init --dry-run --only readme  # preview a single artifact
docagent update                      # incremental (requires prior init)
docagent verify                      # run deterministic-first gate pipeline
pytest                               # full test suite (unit + golden)
```
<!-- ground: pyproject.toml:42-48 --> <!-- ground: docagent/cli.py:79-90 --> <!-- ground: docagent/cli.py:140-144 --> <!-- ground: docagent/cli.py:161-166 -->

## Where to look

- `docagent/cli.py` — Typer app; commands `init`, `update`, `verify`. <!-- ground: docagent/cli.py:18-23 -->
- `docagent/artifacts/builtins.py` — DAG and registration of v1 artifacts (`readme`, `python_docstrings`, `api_reference`, `how_to_guides`, `agents_md`, `claude_md`, `llms_txt`). <!-- ground: docagent/artifacts/builtins.py:7-14 --> <!-- ground: docagent/artifacts/builtins.py:70-101 -->
- `docagent/core/orchestrator.py` — drives `plan → generate → verify → write`, plus the post-write mention-index hook. <!-- ground: docagent/core/orchestrator.py:46-86 -->
- `docagent/verify/pipeline.py` — gate order (markdownlint → links → citations → docs_site → secrets → judge). <!-- ground: docagent/verify/pipeline.py:46-57 -->
- `docagent/backends/agent_sdk.py` — `AgentSDKBackend`; tools restricted to `Read/Glob/Grep`, `permission_mode="bypassPermissions"`. <!-- ground: docagent/backends/agent_sdk.py:21-37 -->
- `tests/golden/` — recorded-backend snapshot tests; fixtures under `tests/golden/fixtures/tinylib/`. <!-- ground: tests/golden/_harness.py:7-13 -->

## Conventions Claude should follow

- Every non-trivial factual claim in generated Markdown must carry `<!-- ground: path:line-start-line-end -->` directly after the sentence. The `citations` gate validates file existence and line ranges. <!-- ground: docagent/backends/agent_sdk.py:29-34 --> <!-- ground: docagent/verify/citations.py:15-39 -->
- Do not wrap generated artifacts in an outer ```markdown fence and do not include preamble like "I'll use the Skill tool…"; if you do, `clean_markdown_output` strips it, but prompts forbid it. <!-- ground: docagent/artifacts/_cleaners.py:4-9 --> <!-- ground: docagent/artifacts/_cleaners.py:24-40 -->
- Top-level artifacts (README, AGENTS.md, CLAUDE.md) must start with a `# ` H1 — the cleaner uses it as the anchor and drops anything before. <!-- ground: docagent/artifacts/_cleaners.py:34-39 -->
- Bump `PROMPT_VERSION` in `docagent/prompts/<artifact>.py` when changing a prompt; it gets stamped into `DocPatch.prompt_version` and folded into the patch digest. <!-- ground: docagent/artifacts/registry.py:25-31 --> <!-- ground: docagent/core/orchestrator.py:16-21 -->
- Snapshot updates are deliberate: run with `UPDATE_SNAPSHOTS=1`, inspect the diff, then commit. <!-- ground: tests/golden/_harness.py:44-50 -->
- Ruff style: `line-length=100`, target `py311`, rules `E,F,I,B,UP,SIM,RUF` (E501 ignored); mypy is `strict`. <!-- ground: pyproject.toml:60-71 -->

## Gotchas

- `docagent update` requires a previous `docagent init` to have written `doc_version` into run state; otherwise it exits with code 2. Affected-artifact resolution is **not yet wired** — `update` only lists changed files. <!-- ground: docagent/cli.py:146-158 -->
- `docagent verify` currently prints the gate list and notes that gate execution against on-disk artifacts is not yet wired — do not assume it failed because no findings appeared. <!-- ground: docagent/cli.py:166-172 -->
- Most v1 artifacts other than `readme`, `agents_md`, `claude_md`, `llms_txt` still emit a placeholder stub (`<!-- docagent: <id> stub. Real generator not yet implemented. -->`). Treat their outputs as scaffolding, not regressions. <!-- ground: docagent/artifacts/builtins.py:46-56 -->
- `PythonDocstringsArtifact.plan` returns `[]` until the symbol-index query is implemented — wiring it requires reading from `ctx.store`, not from disk. <!-- ground: docagent/artifacts/builtins.py:62-67 -->
- The scanner skips `.docagent/`, `.venv/`, `vendor/`, `node_modules/`, `build/`, `dist/`, and friends by default; add a `.docagentignore` to extend. <!-- ground: docagent/ignore.py:9-31 --> <!-- ground: docagent/ignore.py:36-40 -->
- `.docagent/` is gitignored at the repo root but **un-ignored under `tests/golden/`** — fixture state directories are intentionally committed. <!-- ground: .gitignore:22-23 -->
- The orchestrator's `_post_write` hook swallows exceptions into `run.findings` rather than raising; a missing mention row degrades incremental mode silently. <!-- ground: docagent/core/orchestrator.py:88-124 -->
- The Agent SDK backend wraps an async call synchronously and depends on the local `claude` CLI being on PATH. <!-- ground: docagent/backends/agent_sdk.py:1-11 -->

## Test invocation

```bash
pytest                                                        # all tests
pytest tests/unit                                              # unit only
pytest tests/golden/test_readme_snapshot.py                    # one snapshot
UPDATE_SNAPSHOTS=1 pytest tests/golden/test_readme_snapshot.py # re-record
```
<!-- ground: tests/golden/test_readme_snapshot.py:7-11 --> <!-- ground: tests/golden/_harness.py:44-50 -->
