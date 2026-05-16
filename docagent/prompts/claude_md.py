"""Prompt template for the CLAUDE.md artifact.

Targets Anthropic's CLAUDE.md convention: project-specific context Claude
loads automatically at session start. Complements AGENTS.md (a public,
agent-agnostic file) with rules that are Claude-specific or that the
project author wants to keep local to Claude sessions. Lives at the repo
root; for multi-repo monorepos, a `.claude/CLAUDE.md` is preferred.
"""

PROMPT_VERSION = "1"

CLAUDE_MD_PROMPT = """\
You are generating CLAUDE.md for the repository at the current working
directory. The file is read automatically by Claude Code at session start
and supplies project-specific context that complements AGENTS.md.

Distinguish CLAUDE.md from AGENTS.md:
- AGENTS.md is the public, agent-agnostic file with broad setup/test/lint
  conventions.
- CLAUDE.md is Claude-specific: code-review heuristics for this repo,
  Claude-only tool preferences, common-task recipes, the kind of mistake
  Claude has made here that is worth pinning.

Procedure:
1. If AGENTS.md exists, read it first. Do not duplicate its content —
   CLAUDE.md should reference it ("see AGENTS.md for setup") and then add
   what's Claude-specific.
2. Read CLI entry points, key library modules, and any existing CLAUDE.md.
3. Look for repository-specific conventions a coding agent would
   plausibly get wrong on first contact (custom test runners, project
   layout that diverges from convention, code-gen steps, vendored deps).

Produce a Markdown file with these sections, in order. Skip a section if
it does not apply:

- Title (project name as H1) <!-- ground -->
- One-line orientation. <!-- ground -->
- ## Quick commands
  A short reference card of the 3-6 commands you'll actually invoke during
  a typical session. <!-- ground -->
- ## Where to look
  3-6 bullets pointing to the canonical file/directory for common changes
  (CLI entry, public API, test fixtures, configuration loading). Each
  bullet cites the file. <!-- ground -->
- ## Conventions Claude should follow
  Rules that are not enforced by linters but matter (commit message style,
  PR shape, when to add tests, when to update CHANGELOG). Only include
  rules you can ground in CONTRIBUTING.md, prior commits, or explicit
  comments. <!-- ground -->
- ## Gotchas
  Things that have bitten an agent before, or that look reasonable but are
  wrong (e.g. "imports of `foo.legacy` are deprecated; use `foo.core`"
  with a ground citation to the deprecation marker).
- ## Test invocation
  The exact command to run tests, with any required flags / environment
  variables. <!-- ground -->

Grounding rules — non-negotiable:
- Every factual claim about commands, files, or conventions carries a
  `<!-- ground: <relative-path>:<start>-<end> -->` HTML comment.
- Paths are relative to the repo root and must exist.
- Do not invent gotchas or conventions you cannot ground in code or docs.

Style:
- Terse. ≤120 lines total.
- Imperative voice ("Run X", "Edit Y", "Do not Z").
- Code blocks with language hints.

Output: emit ONLY the CLAUDE.md content. No preamble, no surrounding
fences.
"""
