# docagent

Repository documentation agent for humans and coding agents. <!-- ground: pyproject.toml:8-8 -->

> **Not affiliated with [facebookresearch/DocAgent](https://github.com/facebookresearch/DocAgent)** (Meta AI, [arXiv 2504.08725](https://arxiv.org/abs/2504.08725), ACL 2025). That project is a multi-agent pipeline for generating Python docstrings. This project is a single-agent CLI that generates whole-repository documentation (README, AGENTS.md, CLAUDE.md, how-to guides, API reference, llms.txt) with a deterministic verifier and citation-grounded output. See [How we differ](#how-we-differ) below.

## Why

Repositories accumulate stale READMEs, missing how-to guides, and undocumented APIs faster than humans can maintain them, and AI coding assistants increasingly need their own orientation files (`AGENTS.md`, `CLAUDE.md`, `llms.txt`) alongside the human-facing docs. DocAgent treats documentation as a set of verifiable artifacts driven by a DAG, generates them with an LLM backend, and verifies every claim against the actual source via a deterministic-first pipeline. <!-- ground: docagent/artifacts/builtins.py:1-15 --> The verifier is built around ground-citation comments (`<!-- ground: path:start-end -->`) so generated docs stay anchored to real code. <!-- ground: docagent/cli.py:14-23 -->

## Install

DocAgent targets Python 3.11+ and is distributed as the `docagent` package. <!-- ground: pyproject.toml:11-11 --> <!-- ground: pyproject.toml:6-6 -->

```bash
pip install docagent
```

For the multi-provider backend (Gemini, OpenRouter, Anthropic-direct via LiteLLM), install the optional `multi` extra: <!-- ground: pyproject.toml:50-55 -->

```bash
pip install 'docagent[multi]'
```

## Provider setup

DocAgent ships two backends. The default is the **Claude Agent SDK** (`agent_sdk`), which delegates to your local `claude` CLI. <!-- ground: docagent/cli.py:25-26 --> <!-- ground: docagent/cli.py:57-59 -->

```bash
# Default backend — uses your existing `claude` CLI session.
docagent init
```

The opt-in **LiteLLM backend** routes to Gemini, OpenRouter, Anthropic-direct, or OpenAI based on the `--model` string and requires the corresponding provider API key: <!-- ground: docagent/cli.py:27-33 --> <!-- ground: docagent/cli.py:50-56 -->

| Provider | Model string example | Env var |
|---|---|---|
| Anthropic (direct) | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-pro` | `GEMINI_API_KEY` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4-6` | `OPENROUTER_API_KEY` |

```bash
export GEMINI_API_KEY=...
docagent init --backend litellm --model gemini/gemini-2.5-pro
```

`--backend litellm` without `--model` exits with a multi-line hint listing the supported routing strings. <!-- ground: docagent/cli.py:50-53 -->

## Quickstart

Installation registers a single `docagent` console entry point. <!-- ground: pyproject.toml:57-58 --> The Typer app exposes three commands: `init`, `update`, and `verify`. <!-- ground: docagent/cli.py:61-66 -->

```bash
# Full pass: scan repo, build symbol index, generate all artifacts.
docagent init

# Incremental refresh of artifacts affected by recent changes.
docagent update

# Re-run the deterministic-first verifier against artifacts on disk.
docagent verify
```

Useful flags on `init`/`update`: `--dry-run` previews diffs without writing, `--only <artifact_id>` restricts the run to specific artifacts, and `--backend litellm --model <provider/model>` swaps the default Claude Agent SDK backend for LiteLLM. <!-- ground: docagent/cli.py:44-59 -->

## Architecture

DocAgent is organized into orthogonal packages under `docagent/`:

- **`docagent.cli`** — Typer-based entry point for `init` / `update` / `verify`; selects a backend and constructs the orchestrator. <!-- ground: docagent/cli.py:61-66 --> <!-- ground: docagent/cli.py:44-59 -->
- **`docagent.artifacts`** — Each artifact (`readme`, `api_reference`, `how_to_guides`, `agents_md`, `claude_md`, `llms_txt`, `python_docstrings`) owns its own `plan → generate → verify` cycle and registers into the DAG via `register_v1_builtins`. <!-- ground: docagent/cli.py:16-17 -->
- **`docagent.core`** — Orchestrator, scanner, diff/state tracking, and the `BudgetTracker` drive the DAG; CLI imports these directly. <!-- ground: docagent/cli.py:18-22 -->
- **`docagent.adapters` + `docagent.parser`** — Language adapters using libcst/jedi for Python and tree-sitter for Rust/Go/TypeScript/Java/C++ extract symbols and signatures. <!-- ground: pyproject.toml:25-33 -->
- **`docagent.index`** — SQLite-backed symbol/mention store opened via `open_store`; populated by the scanner during `init`. <!-- ground: docagent/cli.py:22-22 -->
- **`docagent.backends`** — Pluggable LLM backends: `agent_sdk` (default, Claude Agent SDK) and `litellm` (multi-provider; `--model` required). <!-- ground: docagent/cli.py:25-59 -->
- **`docagent.verify`** — Deterministic-first verification pipeline backing the `verify` command and the per-artifact verify phase. <!-- ground: docagent/cli.py:61-66 -->

## Status

Beta. <!-- ground: pyproject.toml:14-15 --> The artifact pipeline runs end-to-end and self-verifies through the deterministic gates; the package version is `1.0.4` and APIs may still change between minor releases. <!-- ground: pyproject.toml:7-7 --> <!-- ground: docagent/__init__.py:3-3 -->

## How we differ

This project shares the name "DocAgent" with Meta AI's [facebookresearch/DocAgent](https://github.com/facebookresearch/DocAgent) ([arXiv 2504.08725](https://arxiv.org/abs/2504.08725), ACL 2025 demo) but is a separate, unaffiliated project with a different scope:

| Axis | Meta's DocAgent | This project |
|---|---|---|
| **Scope** | Python docstrings only, symbol-level | Whole-repo artifacts: README, AGENTS.md, CLAUDE.md, how-to guides, API reference, `llms.txt`, plus docstrings |
| **Topology** | 5-agent pipeline (Navigator → Reader / Searcher / Writer / Verifier / Orchestrator) | Single-agent orchestrator over the Claude Agent SDK |
| **Verification** | LLM "Verifier" agent | Deterministic-first gate pipeline (ground-citation validation, markdownlint, structure, secrets) |
| **Indexing** | In-process dependency graph | Persisted SQLite symbol index (libcst + tree-sitter) |
| **Grounding** | Hierarchical context build | `<!-- ground: path:line-start-line-end -->` citation enforcement on every non-trivial claim |
| **Distribution** | Research repo, clone-and-run | `pip install`-able CLI: `docagent init / update / verify` |

If you arrived here looking for the Meta paper's reference implementation, you want [facebookresearch/DocAgent](https://github.com/facebookresearch/DocAgent).

## License

MIT. <!-- ground: LICENSE:1-1 --> <!-- ground: pyproject.toml:10-10 -->
