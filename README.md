# DocAgent

Repository documentation agent for humans and coding agents. <!-- ground: pyproject.toml:6-8 -->

## Why

Existing tooling either generates stale per-symbol Markdown without verification or is closed SaaS. DocAgent produces dual-track output — human-facing files (README, how-to guides) alongside agent-facing files (`AGENTS.md`, `CLAUDE.md`, `llms.txt`) — driven by an agentic generation loop. <!-- ground: docagent/artifacts/builtins.py:7-14 --> A deterministic-first verifier short-circuits cheap gates (markdownlint, links, citations, secrets) before the expensive LLM judge runs. <!-- ground: docagent/verify/pipeline.py:46-57 --> It targets multi-language repos via tree-sitter and offers incremental, git-diff-driven refreshes. <!-- ground: pyproject.toml:27-33 -->

## Install

```bash
pip install docagent
```

Requires Python ≥ 3.11. <!-- ground: pyproject.toml:11-11 --> The package is published as `docagent` and installs a `docagent` console script. <!-- ground: pyproject.toml:50-51 -->

For development:

```bash
pip install -e ".[dev]"
```

<!-- ground: pyproject.toml:42-48 -->

## Quickstart

```bash
docagent init      # full pass: scan repo, build index, generate all artifacts
docagent update    # incremental refresh based on git diff since last run
docagent verify    # run the deterministic-first verifier pipeline
```

<!-- ground: docagent/cli.py:79-90 --> <!-- ground: docagent/cli.py:140-144 --> <!-- ground: docagent/cli.py:161-166 -->

Useful flags on `init`: `--repo/-C` to set the repo root, `--only` to restrict to specific artifact ids, `--dry-run` to print diffs without writing, and `--skip-index` to reuse an existing `.docagent/index.db`. <!-- ground: docagent/cli.py:80-88 -->

`update` requires a prior `init`; it reads the previous `doc_version` from run state and lists files changed since then. Affected-artifact resolution is not yet wired. <!-- ground: docagent/cli.py:146-158 -->

## Architecture

- `docagent/cli.py` — Typer-based CLI exposing `init`, `update`, and `verify` subcommands. <!-- ground: docagent/cli.py:18-23 -->
- `docagent/core/scanner.py`, `state.py`, `diff.py` — repository scanner, persisted run state, and git-diff helpers used by the CLI. <!-- ground: docagent/cli.py:14-16 -->
- `docagent/adapters/` — per-language parser adapters that extract symbols (qualified name, kind, byte/line ranges, signature, existing doc) from scanned files. <!-- ground: docagent/cli.py:54-73 -->
- `docagent/parser/treesitter.py` — tree-sitter parsing layer shared across adapters. <!-- ground: pyproject.toml:27-33 -->
- `docagent/index/store.py` — SQLite-backed symbol store; `open_store` persists file hashes and symbol rows for incremental work. <!-- ground: docagent/cli.py:16-16 --> <!-- ground: docagent/cli.py:74-75 -->
- `docagent/artifacts/` — registry + v1 builtins (`readme`, `python_docstrings`, `api_reference`, `how_to_guides`, `agents_md`, `claude_md`, `llms_txt`) wired into a dependency DAG. <!-- ground: docagent/artifacts/builtins.py:7-14 --> <!-- ground: docagent/artifacts/builtins.py:70-101 -->
- `docagent/core/orchestrator.py` — drives `plan → generate → verify → write` across the artifact DAG, with a post-write hook that populates the mention index. <!-- ground: docagent/core/orchestrator.py:46-86 -->
- `docagent/backends/agent_sdk.py` — `AgentSDKBackend` drives the Claude Agent SDK loop invoked by the orchestrator. <!-- ground: docagent/cli.py:91-92 -->
- `docagent/verify/pipeline.py` — deterministic-first verifier pipeline composed of named gates (markdownlint, links, citations, docs_site, secrets, judge) with optional non-blocking gates. <!-- ground: docagent/verify/pipeline.py:46-57 -->

## Status

Pre-alpha. <!-- ground: pyproject.toml:15-15 --> CLI scaffolding, indexing, the orchestrator, and the verifier gate registry exist, but most v1 artifacts are still stubs that emit placeholder content, `update` does not yet resolve affected artifacts, and `verify` does not yet execute gates against on-disk artifacts. <!-- ground: docagent/artifacts/builtins.py:46-56 --> <!-- ground: docagent/cli.py:158-158 --> <!-- ground: docagent/cli.py:172-172 -->

## License

MIT. <!-- ground: LICENSE:1-3 -->
