# DocAgent

Repository documentation agent for humans and coding agents. Generates and verifies READMEs, AGENTS.md, CLAUDE.md, and llms.txt — and breaks CI when a documentation citation no longer matches the source. <!-- ground: pyproject.toml:6-8 -->

## What it does

Most AI documentation tools generate plausible prose and stop there. DocAgent makes documentation *checkable*: every non-trivial claim carries a `<!-- ground: path:line-start-line-end -->` HTML comment, and a deterministic-first verifier confirms that the cited file and line range still match what the prose says. <!-- ground: docagent/verify/citations.py:1-6 -->

The gate order is cheap-first: structural lint (non-blocking) → links → citations → docs-site dry-run (non-blocking) → secrets → LLM judge (non-blocking, tiebreaker only). Truth-checking gates block writes; stylistic gates do not. <!-- ground: docagent/verify/pipeline.py:46-64 -->

Output is dual-track. Human files (`README.md`) and agent files (`AGENTS.md` per the Linux Foundation spec, `CLAUDE.md` per Anthropic, `llms.txt` per llmstxt.org) share an artifact DAG so dependents (e.g. AGENTS.md citing README) regenerate in the right order. <!-- ground: docagent/artifacts/builtins.py:71-92 -->

## Install

```bash
pip install docagent
```

Requires Python ≥ 3.11. <!-- ground: pyproject.toml:11-11 --> Installs a `docagent` console script. <!-- ground: pyproject.toml:51-52 -->

For development:

```bash
pip install -e ".[dev]"
```

<!-- ground: pyproject.toml:42-49 -->

## Quickstart

```bash
docagent init      # full pass: scan repo, build index, generate all artifacts
docagent update    # incremental refresh based on git diff since last init
docagent verify    # run the deterministic-first verifier pipeline
```

<!-- ground: docagent/cli.py:84-95 --> <!-- ground: docagent/cli.py:153-161 --> <!-- ground: docagent/cli.py:300-315 -->

Global flags: `--debug` emits DEBUG-level logs to stderr (also: `DOCAGENT_DEBUG=1`); `--version` prints the version and exits. <!-- ground: docagent/cli.py:41-50 -->

`init` accepts `--only <id>` (repeatable), `--dry-run`, and `--skip-index` to reuse an existing `.docagent/index.db`. <!-- ground: docagent/cli.py:85-93 -->

`update` resolves affected artifacts via two signals — the identifier-mention index and on-disk citation paths — so renaming a function only refreshes the artifacts that actually mention it. <!-- ground: docagent/core/affected.py:1-18 -->

`verify` works against on-disk artifacts. It reads the registry, picks up any artifact recorded in `.docagent/index.db` or discovered on disk by its conventional target path, and runs the pipeline. Use `--strict` to fail on any finding, including non-blocking warnings. <!-- ground: docagent/cli.py:300-315 -->

## GitHub Action

Wire the verifier into CI so a PR that breaks a citation goes red:

```yaml
# .github/workflows/docs.yml
name: docs
on: [pull_request]
permissions:
  contents: read
  pull-requests: write
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hayden1126/DocAgent@main
        with:
          strict: false       # or 'true' to fail on non-blocking findings
          # only: 'readme,agents_md'  # restrict to specific artifacts
```

The Action runs `docagent verify` — pure-deterministic, no Claude API key required. On PR failure it posts a sticky comment with the verifier output. <!-- ground: action.yml:1-7 --> <!-- ground: action.yml:85-105 -->

## Grounding citations

The convention is a single HTML comment placed immediately after the sentence it grounds:

```markdown
The scanner skips `.docagent/` by default. <!-- ground: docagent/ignore.py:9-31 -->
```

Paths are repo-relative POSIX (`/`-separated). The line range is inclusive; a single line can be written as `path:42` instead of `path:42-42`. <!-- ground: docagent/citations.py:1-12 --> The grammar reserves `:` as the delimiter — paths may not contain `:` or whitespace. <!-- ground: docagent/citations.py:21-23 -->

## Where to look

- `docagent/cli.py` — Typer app with `init`, `update`, `verify` commands. <!-- ground: docagent/cli.py:19-24 -->
- `docagent/core/orchestrator.py` — drives `plan → generate → verify → write`, plus the post-write hook that populates the mention index. <!-- ground: docagent/core/orchestrator.py:49-91 -->
- `docagent/core/affected.py` — two-signal incremental resolver used by `update`. <!-- ground: docagent/core/affected.py:71-92 -->
- `docagent/verify/pipeline.py` — gate ordering and blocking semantics. <!-- ground: docagent/verify/pipeline.py:46-64 -->
- `docagent/citations.py` — single source of truth for the citation grammar. <!-- ground: docagent/citations.py:11-21 -->
- `docagent/backends/agent_sdk.py` — Claude Agent SDK backend; restricted to `Read/Glob/Grep`. <!-- ground: docagent/backends/agent_sdk.py:34-39 -->
- `docagent/artifacts/builtins.py` — v1 artifact registry. <!-- ground: docagent/artifacts/builtins.py:71-92 -->
- `tests/integration/test_verify_flow.py` and `test_update_flow.py` — end-to-end coverage of the two CI-visible flows.

## Languages

Python and TypeScript / JavaScript are first-class: a dedicated adapter extracts symbols with byte- and line-precise ranges suitable for grounded citations. The TS adapter handles `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, and `.d.ts`, covering functions, classes, methods, interfaces, type aliases, enums, namespaces, module-scope arrow-fn consts, and the common CommonJS `module.exports.foo = () => …` pattern. <!-- ground: docagent/adapters/typescript.py:34-39 --> <!-- ground: docagent/adapters/queries/typescript_tags.scm:14-83 --> Constructors and ECMAScript-private (`#foo`) members are deliberately excluded; in-place JSDoc generation is a v2 item. <!-- ground: docagent/adapters/typescript.py:91-96 -->

Rust, Go, Java, and C++ are covered by a tree-sitter-only fallback adapter — symbol extraction works but cross-references are lexical, not semantic. <!-- ground: docagent/adapters/fallback.py:25-50 -->

## `api_reference`

For each public Python module the scanner indexed, `api_reference` writes one curated landing page at `docs/reference/<dotted.name>.md`. <!-- ground: docagent/artifacts/api_reference.py:204-209 --> Each page combines a deterministic public-surface table (read directly from the symbol index — no LLM) with an LLM-written opener paragraph and 1-3 grounded worked examples, plus a see-also section linking to sibling and parent modules. <!-- ground: docagent/artifacts/_api_reference_render.py:107-138 --> Per-module fingerprinting via the new `artifact_unit_fingerprints` table makes re-runs idempotent — unchanged source skips the LLM call entirely. <!-- ground: docagent/artifacts/api_reference.py:60-76 -->

Use `--max-modules N` on `init` to cap the per-run cost (default 25, set to `0` for unlimited). <!-- ground: docagent/cli.py:93-97 --> The artifact deliberately does NOT generate per-symbol pages — point [`mkdocstrings`](https://mkdocstrings.github.io/) or [`pdoc`](https://pdoc.dev/) at the same source for that.

## Status

v1 alpha. Five artifacts ship end-to-end (`readme`, `agents_md`, `claude_md`, `llms_txt`, `api_reference`); `how_to_guides` and `python_docstrings` remain stubs (the latter cut from v1 — in-place source mutation is too high-risk for an experimental flag). <!-- ground: docagent/artifacts/builtins.py:71-92 --> The verifier is fully wired against on-disk artifacts; the `judge` gate is non-blocking and reports `skipped: judge not yet implemented` until its single-turn LLM call lands. <!-- ground: docagent/verify/judge.py:1-9 -->

## License

MIT. <!-- ground: LICENSE:1-3 -->
