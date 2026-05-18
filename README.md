# docagent

Repository documentation agent for humans and coding agents. <!-- ground: pyproject.toml:8-8 -->

## Why

Repositories accumulate stale READMEs, missing how-to guides, and undocumented APIs faster than humans can maintain them, and AI coding assistants increasingly need their own orientation files (`AGENTS.md`, `CLAUDE.md`, `llms.txt`) alongside the human-facing docs. DocAgent treats documentation as a set of verifiable artifacts driven by a DAG, generates them with an LLM backend, and verifies every claim against the actual source via a deterministic-first pipeline. <!-- ground: docagent/artifacts/builtins.py:1-15 --> The verifier is built around ground-citation comments (`<!-- ground: path:start-end -->`) so generated docs stay anchored to real code. <!-- ground: docagent/cli.py:524-532 -->

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

DocAgent has two backends. The default is the **Claude Agent SDK**, which delegates to your local `claude` CLI; a missing CLI surfaces an actionable hint and exits cleanly. <!-- ground: docagent/backends/agent_sdk.py:68-70 -->

```bash
# Default backend — uses your existing `claude` CLI session.
docagent init
```

The opt-in **LiteLLM backend** (`pip install 'docagent[multi]'`) routes to Gemini, OpenRouter, or Anthropic-direct based on the model string. Set the appropriate provider env var: <!-- ground: docagent/backends/litellm_backend.py:211-217 -->

| Provider | Model string example | Env var |
|---|---|---|
| Anthropic (direct) | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-pro` | `GEMINI_API_KEY` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4-6` | `OPENROUTER_API_KEY` |
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |

```bash
export GEMINI_API_KEY=...
docagent init --backend litellm --model gemini/gemini-2.5-pro
```

`--backend litellm` without `--model` exits with a clean hint listing the supported routing strings. <!-- ground: docagent/backends/litellm_backend.py:211-217 --> Unsupported models still run but emit a one-time `[unsupported-model]` warning per model name. **Ollama is deliberately out of v1**: the citation-emission rate measured 0% on `llama3.1:8b` during the spike, breaking the verifier moat; re-spike on Llama 3.3 70B+ / Qwen 2.5 Coder 32B+ is the v1.1 trigger. <!-- ground: .planning/decisions/0001-spike-results.md:1-15 -->

## Quickstart

Installation registers a single `docagent` CLI entry point. <!-- ground: pyproject.toml:57-58 --> It exposes three commands — `init`, `update`, and `verify`. <!-- ground: docagent/cli.py:195-196 --> <!-- ground: docagent/cli.py:320-321 --> <!-- ground: docagent/cli.py:517-518 -->

```bash
# Full pass: scan repo, build symbol index, generate all artifacts.
docagent init

# Incremental refresh: regenerate only artifacts affected by recent changes.
docagent update

# Re-run the deterministic-first verifier against artifacts already on disk.
docagent verify
```
<!-- ground: docagent/cli.py:240-240 --> <!-- ground: docagent/cli.py:357-357 --> <!-- ground: docagent/cli.py:525-532 -->

Useful flags on `init` / `update`: `--dry-run` prints diffs without writing, `--only <artifact_id>` restricts the run to specific artifacts, and `--max-cost USD` caps total LLM spend. <!-- ground: docagent/cli.py:201-223 --> Switch to the LiteLLM multi-provider backend with `--backend litellm --model <provider/model>` (default is the Claude Agent SDK). <!-- ground: docagent/cli.py:26-59 -->

## Architecture

DocAgent is organized into orthogonal packages under `docagent/`:

- **`docagent.cli`** — Typer-based entry point for `init` / `update` / `verify`; selects a backend and constructs the orchestrator. <!-- ground: docagent/cli.py:61-66 --> <!-- ground: docagent/cli.py:44-59 -->
- **`docagent.artifacts`** — Each artifact (`readme`, `api_reference`, `how_to_guides`, `agents_md`, `claude_md`, `llms_txt`, `python_docstrings`) owns its own `plan → generate → verify` cycle and declares dependencies in a DAG. <!-- ground: docagent/artifacts/builtins.py:7-15 -->
- **`docagent.core`** — Orchestrator, scanner, diff/state tracking, budget enforcement, and affected-artifact resolution drive the DAG. <!-- ground: docagent/core/orchestrator.py:1-21 --> <!-- ground: docagent/cli.py:266-277 -->
- **`docagent.adapters` + `docagent.parser`** — Language adapters using libcst/jedi for Python and tree-sitter for Rust/Go/TypeScript/Java/C++ extract symbols and signatures. <!-- ground: pyproject.toml:25-33 -->
- **`docagent.index`** — SQLite-backed symbol/mention store at `.docagent/index.db`; populated by the scanner during `init`. <!-- ground: docagent/cli.py:164-192 --> <!-- ground: docagent/cli.py:203-204 -->
- **`docagent.backends`** — Pluggable LLM backends: `agent_sdk` (default, Claude Agent SDK) and `litellm` (multi-provider; `--model` required). <!-- ground: docagent/cli.py:44-59 -->
- **`docagent.verify`** — Deterministic-first verification pipeline: ground-citation resolution, link checks, secrets scan, and per-artifact gates. <!-- ground: docagent/cli.py:533-540 -->

## Status

Pre-Alpha. <!-- ground: pyproject.toml:14-15 --> The artifact pipeline runs end-to-end and self-verifies through the deterministic gates, but versioning is still `0.1.0-dev` and APIs may change. <!-- ground: pyproject.toml:7-7 --> <!-- ground: docagent/__init__.py:3-3 -->

## License

MIT. <!-- ground: LICENSE:1-1 --> <!-- ground: pyproject.toml:10-10 -->
