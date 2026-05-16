"""Prompt template for the AGENTS.md artifact.

Targets the Linux Foundation `AGENTS.md` convention (agents.md): plain
Markdown, no rigid schema, but optimized for *coding agents* who need to
reason about the repo quickly. Distinct from CLAUDE.md (Anthropic-specific
project context) and from the README (human-facing marketing/overview).
"""

PROMPT_VERSION = "1"

AGENTS_MD_PROMPT = """\
You are generating the top-level AGENTS.md for the repository at the current
working directory. The file is read by coding agents (Cursor, Claude Code,
Codex, Continue, etc.) to orient themselves before making changes. Keep it
under 150 lines.

Procedure:
1. Use Glob and Read to inventory the build system, scripts, tests, code
   style configuration (ruff, eslint, gofmt, rustfmt, etc.), and any
   pre-commit / CI configuration.
2. Read the package manifest (pyproject.toml / package.json / Cargo.toml /
   go.mod) to identify the canonical install and run commands.
3. Read the test directory enough to give an accurate test command.
4. Note any AGENTS.md / CLAUDE.md / .cursorrules that already exist — do
   not contradict them; preserve their voice where it agrees with the code.

Produce a Markdown file with these sections, in order. Skip a section if it
truly does not apply, but do not invent one to fill space:

- Title (project name as H1)
- One-line orientation: what the project is and what it does. <!-- ground -->
- ## Setup
  Install commands an agent should run in a fresh clone. Copy-pasteable.
  <!-- ground -->
- ## Run
  How to invoke the project (CLI, server, library import). <!-- ground -->
- ## Test
  The single command that runs the test suite, plus how to run a focused
  test. <!-- ground -->
- ## Lint and format
  Commands for the project's actual linters/formatters. Mention any
  pre-commit configuration. <!-- ground -->
- ## Project structure
  3-8 bullets mapping top-level directories to their purpose. Each bullet
  cites the directory or a representative file. <!-- ground -->
- ## Conventions
  Code-style rules, naming patterns, error handling expectations, anything
  an agent would otherwise re-derive from reading samples. Cite the source
  of each convention (config file, existing code). <!-- ground -->
- ## Boundaries
  Files or directories an agent should NOT modify (generated code, vendored
  deps, large fixtures). Cite ignore files or comments that establish the
  boundary. <!-- ground -->
- ## Tasks to avoid
  Common tasks that look reasonable but are wrong here (e.g. "do not edit
  *_pb2.py by hand", "do not run alembic upgrade without --sql first").
  Only include if you have evidence in the repo.

Grounding rules — non-negotiable:
- Every command, path, or convention claim carries a
  `<!-- ground: <relative-path>:<start>-<end> -->` HTML comment immediately
  after the sentence.
- Paths are relative to the repo root and must exist.
- Do not invent commands, scripts, or conventions you have not verified by
  reading the source.

Style:
- Imperative, agent-readable. Bullet lists over prose where possible.
- Code blocks use triple backticks with language hints.
- ≤150 lines total.

Output: emit ONLY the AGENTS.md content. No preamble, no commentary, no
surrounding fences.
"""
