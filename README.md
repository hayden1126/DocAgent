# DocAgent

Repository documentation agent for humans and coding agents. <!-- ground: pyproject.toml:6-8 -->

## Why

Existing tooling either generates stale per-symbol Markdown without verification or is closed SaaS. DocAgent produces dual-track output — human-readable Markdown plus agent-facing files — driven by an agentic generation loop and a deterministic-first verification pipeline. <!-- ground: docagent/__init__.py:1-1 --> It targets multi-language repos via tree-sitter and offers incremental, git-diff-driven refreshes. <!-- ground: pyproject.toml:22-40 -->

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

<!-- ground: docagent/cli.py:79-90 --> <!-- ground: docagent/cli.py:136-141 --> <!-- ground: docagent/cli.py:157-162 -->

Useful flags on `init`: `--repo/-C` to set the repo root, `--only` to restrict to specific artifact ids, `--dry-run` to print diffs without writing, and `--skip-index` to reuse an existing `.docagent/index.db`. <!-- ground: docagent/cli.py:80-88 -->

`update` requires a prior `init`; it reads the previous `doc_version` from run state and lists files changed since then (affected-artifact resolution is not yet wired). <!-- ground: docagent/cli.py:142-154 -->

## Architecture

- `docagent/cli.py` — Typer-based CLI exposing `init`, `update`, and `verify` subcommands. <!-- ground: docagent/cli.py:18-23 -->
- `docagent/core/` — repository scanner, run state, and git-diff helpers used by the CLI. <!-- ground: docagent/cli.py:14-15 -->
- `docagent/adapters/` — per-language parser adapters that extract symbols (qualified name, kind, byte/line ranges, signature, existing doc) from scanned files. <!-- ground: docagent/cli.py:54-73 -->
- `docagent/parser/treesitter.py` — tree-sitter parsing layer shared across adapters. <!-- ground: docagent/parser/treesitter.py:1-1 -->
- `docagent/index/` — SQLite-backed symbol store; `open_store` persists file hashes and symbol rows for incremental work. <!-- ground: docagent/cli.py:74-75 -->
- `docagent/artifacts/registry.py` — registry of generated artifacts; `register_v1_builtins` populates the v1 set. <!-- ground: docagent/cli.py:12-13 -->
- `docagent/backends/` — generation backends; `AgentSDKBackend` drives the Claude Agent SDK loop invoked by the orchestrator. <!-- ground: docagent/cli.py:91-92 -->
- `docagent/verify/pipeline.py` — deterministic-first verifier pipeline composed of named gates (markdownlint, links, citations, docs-site, secrets, judge). <!-- ground: docagent/cli.py:163-167 -->

## Status

Pre-alpha. <!-- ground: pyproject.toml:15-15 --> CLI scaffolding, indexing, and the verifier gate registry exist, but `update` does not yet resolve affected artifacts and `verify` does not yet execute gates against on-disk artifacts. <!-- ground: docagent/cli.py:154-154 --> <!-- ground: docagent/cli.py:168-168 -->

## License

MIT. <!-- ground: LICENSE:1-3 -->
