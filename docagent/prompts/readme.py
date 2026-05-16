"""Prompt template for the README artifact."""

README_PROMPT = """\
You are generating the top-level README.md for the repository at the current
working directory.

Procedure:
1. Use Glob to discover the layout. Read pyproject.toml or package.json or
   Cargo.toml or go.mod (whichever exists) to identify the project name,
   description, language, and install command.
2. Read the most important source entry points — CLI entry, package
   `__init__.py`, top-level lib files, the `tests/` directory — to understand
   what the project actually does.
3. Read any existing README.md, AGENTS.md, or docs/ contents to preserve voice
   and avoid contradicting prior documentation. Do not preserve outdated
   claims; verify them.

Produce a README with these sections, in order:
- Title (project name as H1)
- One-sentence elevator description (verified against pyproject/package
  metadata)
- ## Why — 2-4 sentences on the problem the project solves
- ## Install — copy-pasteable install command verified against the build
  metadata
- ## Quickstart — minimal end-to-end usage. Prefer commands that are
  actually wired (CLI entry points present in the source).
- ## Architecture — 4-8 bullet points or a short paragraph describing the
  major modules and how they fit together. Reference real files.
- ## Status — pre-alpha / alpha / stable as appropriate, with a one-line
  honest assessment.
- ## License — read LICENSE if present and state the SPDX identifier.

Grounding rules — non-negotiable:
- Every factual claim about install commands, CLI entry points, module
  responsibilities, or architectural relationships MUST carry a
  `<!-- ground: <relative-path>:<start>-<end> -->` HTML comment immediately
  after the sentence it grounds.
- Paths must be relative to the repo root and must exist.
- Line ranges must point to real, supportive code. Do not cite a range you
  have not Read.
- Do not invent CLI commands, modules, or behaviors. If you are unsure, omit
  the claim.

Style:
- Concise. ≤200 lines total.
- No emojis unless the existing README already uses them.
- Code blocks use triple backticks with language hints (```bash, ```python).

Output: emit ONLY the README.md content. No commentary, no surrounding
```markdown fences, no "Here is the README:" preamble.
"""
