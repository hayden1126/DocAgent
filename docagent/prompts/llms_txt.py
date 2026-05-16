"""Prompt template for the llms.txt artifact.

Targets the llmstxt.org convention: a Markdown file at the repo root that
curates essential project context for LLM agents. Required: H1 + blockquote
summary. Optional: H2-delimited sections of `[name](url)` link lists with
one-line descriptions. The special `## Optional` section flags lower-priority
links.
"""

PROMPT_VERSION = "1"

LLMS_TXT_PROMPT = """\
You are generating /llms.txt for the repository at the current working
directory, per the llmstxt.org convention. Coding agents and LLM-driven
tools read this file at the start of a task to load curated project context
without crawling the whole repo.

Procedure:
1. Read pyproject.toml / package.json / Cargo.toml / go.mod and any
   top-level README to learn the project name and a one-sentence summary.
2. Inventory the docs/ tree (or equivalent), the README, and any high-value
   reference files an agent should know about.
3. Identify which files are "essential" (every agent should load them)
   versus "optional" (relevant for some tasks).

Produce a Markdown file with EXACTLY this structure:

1. An H1 line: `# <project name>` — taken from the package manifest.
2. A blockquote (`> ...`) one-paragraph summary of what the project is, what
   it does, and who/what it is for. 2-4 sentences. Ground the claim that
   describes what the project does.
3. (Optional but recommended) A short prose paragraph of additional context,
   if the blockquote leaves something important unsaid. Plain prose, no
   bullets.
4. One or more H2 sections (`## Section name`), each containing a
   bullet list of links: `- [Title](relative/path): one-line description.`
   Suggested sections: `## Docs`, `## Code`, `## Tests`.
5. A final `## Optional` section listing links the agent can skip in
   bandwidth-constrained settings.

Grounding rules — non-negotiable:
- Every link points to a file or directory that exists in the repo.
- The blockquote-summary's main verb (what the project does) carries a
  `<!-- ground: <relative-path>:<start>-<end> -->` HTML comment.
- Other prose claims also carry ground citations when they make factual
  statements about the code.

Style:
- Concise. The file should be skim-readable in ten seconds.
- Use relative paths.
- Use lowercase section names where natural (`## Docs`, not `## DOCS`).
- No emojis.

Output: emit ONLY the llms.txt content. No preamble, no surrounding fences.
"""
