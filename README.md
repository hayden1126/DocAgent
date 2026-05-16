# DocAgent

A repository documentation agent that reads existing repositories, writes new
documentation, and improves existing documentation. Output is dual-track:
human-readable Markdown plus agent-facing files (`AGENTS.md`, `llms.txt`,
`CLAUDE.md`).

> Status: pre-alpha. v1 is under active development. See
> [`docs/specs/`](docs/specs) and the architecture plan for scope.

## Why

Existing tools either ship stale per-symbol Markdown without verification
(RepoAgent) or are closed SaaS (DocuWriter). DocAgent combines:

- **Agentic loops** (Claude Agent SDK) for generation
- **Deterministic-first verification** (markdownlint → links → AST citation
  resolver → docs-site dry-run → secret scan → LLM judge)
- **Dual audience output** shaped by [Diátaxis](https://diataxis.fr) and the
  [AGENTS.md](https://agents.md) / [llms.txt](https://llmstxt.org) conventions
- **Git-diff-driven incremental updates** with an identifier-mention index
  that catches prose drift when symbols are renamed
- **Multi-language** via tree-sitter, with optional per-language deepeners
  (libcst+Jedi, LSPs, native tools)

## Install (planned)

```bash
pip install docagent
```

## Quickstart (planned)

```bash
docagent init     # full pass over the repo
docagent update   # incremental refresh based on git diff
docagent verify   # CI gate
```

## License

MIT.
