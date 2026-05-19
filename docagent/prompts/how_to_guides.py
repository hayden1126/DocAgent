"""Prompt templates for the ``how_to_guides`` artifact.

Two LLM calls per run for this artifact:

1. **Discovery** — one call total. Enumerate user-task topics from the
   README + ``docs/reference/*.md`` set.
2. **Per-page** — one call per planned topic. Produce the Diátaxis how-to
   layout: H1 imperative title + ``## Goal`` + ``## Steps`` (grounded) +
   ``## Verify`` + optional ``## Troubleshoot``. The deterministic
   pipeline (:mod:`docagent.artifacts._how_to_render`) prepends
   frontmatter and appends the ``## See also`` block — DO NOT instruct
   the LLM to write either.

`PROMPT_VERSION` is intentionally ONE constant covering BOTH prompts:
bumping it invalidates every how-to fingerprint at once. Coupling is
intentional — any prompt change requires the user to regenerate all
pages so style stays consistent.
"""

from __future__ import annotations

PROMPT_VERSION = "2"

HEADER_MARKER = "<<<HOWTO_PAGE_BEGIN>>>"
FOOTER_MARKER = "<<<HOWTO_PAGE_END>>>"


_DISCOVERY_TEMPLATE = """\
You are extracting user-task topics for a Diátaxis-style "how-to guides"
section of a software project's documentation.

A how-to is goal-oriented: it answers "how do I accomplish X?" with a
short sequence of imperative steps. It is NOT a tutorial (learning-
oriented), NOT a reference (information-oriented), and NOT an explanation
(understanding-oriented). Pick topics that a real user of this repo
would search for after they already know the project exists.

You may Read the following files and ONLY these files (Glob/Grep are
fine for navigating within them; do not range further):

README excerpt paths:
{readme_paths_block}

Reference page paths:
{reference_paths_block}

Repo root for citation paths: `{repo_root}`

Return AT MOST {max_topics} topics. Cap is hard — if you find more,
prioritize the most cross-cutting / user-visible ones.

## Required output format

Return a single JSON array. No preamble, no markdown fence, no trailing
prose. Each element is an object of the shape:

  {{"title": "Run docagent in CI", "sources": ["README.md:42-68", "docs/reference/docagent.cli.md:120-145"]}}

Rules:
- `title` is the user task in imperative verb-noun form ("Run X in Y",
  "Configure Z", "Extend W"). Do NOT use noun phrases like
  "Introduction to X" or "Overview of Y" — those belong in explanation
  pages, not how-to.
- `sources` lists 1-4 repo-relative `path:start-end` line ranges drawn
  ONLY from the paths above. Line ranges must be real (you have read
  them) and ground the task.
- Skip topics for which you cannot cite at least one source.
- Do not propose API-reference topics (one-symbol-per-page reference is
  a separate artifact).
- Output JSON only. Nothing else.
"""


_PAGE_TEMPLATE = """\
You are writing one Diátaxis how-to page for a software project.

Topic title (the page H1, imperative form): {topic_title}

Cite ONLY against these sources (Read/Glob/Grep restricted to them):
{sources_block}

A deterministic pipeline will prepend the frontmatter and append a
related-links block. You produce everything else, between the markers
below.

## Required output format

Emit exactly these two markers with content between. No preamble. No
trailing prose after the second marker.

{header_marker}
# {topic_title}

## Goal
[One paragraph naming the user's outcome. End with one
`<!-- ground: path:start-end -->` citation.]

## Steps
1. [Imperative step. End with `<!-- ground: path:start-end -->`.]
2. [Next imperative step. Ground it too.]
3. [...as many as needed; typically 3-7 steps.]

## Verify
[One short paragraph or a single command the user runs to confirm the
goal is met. The check MUST exercise a behavioral assertion — import a
symbol, call a CLI subcommand, query an API, observe a file/exit-code
side effect — that proves the goal was achieved. Do NOT re-run the same
command from Steps and rely on it reporting "already done" (e.g.
"re-run `pip install`; pip will say already-installed" is circular and
forbidden). Ground it.]

## Troubleshoot
[Optional. Include this section ONLY if you have grounded
failure-mode citations from the sources above. If you do not, OMIT
this section entirely — do not write a "## Troubleshoot" heading
with empty content.]
{footer_marker}

## Rules
- Use Read / Glob / Grep on the listed sources to verify every claim.
- Every imperative sentence in `## Steps` MUST carry a
  `<!-- ground: path:start-end -->` comment immediately after.
- Citation paths are repo-relative; line ranges must reference real
  lines you have read. Before emitting any
  `<!-- ground: PATH:A-B -->`, confirm B is ≤ the file's line count
  (Read the file and verify). When unsure, cite a narrower range that
  you have actually seen — the citations gate will reject ranges that
  exceed file bounds and the artifact will not land on disk.
- The H1 must be the imperative verb-noun title given above. Do NOT
  rewrite it as a noun phrase like "Introduction to X" or
  "Overview of Y".
- Do NOT write a `## See also` section. The pipeline appends one.
- Do NOT include YAML frontmatter. The pipeline prepends it.
- Do NOT invent commands, flags, or behavior. If a step would require
  speculation, omit the step.
- Keep prose tight. A user reading this is trying to finish a task,
  not learn the project.

Emit only the marker-delimited block.
"""


def _format_path_list(paths: list[str]) -> str:
    """Sort + format as a bulleted block. Deterministic across runs."""
    if not paths:
        return "(none)"
    return "\n".join(f"- {p}" for p in sorted(paths))


def _sanitize_title(title: str) -> str:
    """Collapse newlines/tabs to spaces so an LLM-supplied title cannot
    inject prompt-level instructions on a new line."""
    return " ".join(title.split())


def build_discovery_prompt(
    *,
    repo_root: str,
    readme_excerpt_paths: list[str],
    reference_paths: list[str],
    max_topics: int,
) -> str:
    """Build the one-shot topic-discovery prompt."""
    return _DISCOVERY_TEMPLATE.format(
        readme_paths_block=_format_path_list(readme_excerpt_paths),
        reference_paths_block=_format_path_list(reference_paths),
        repo_root=repo_root,
        max_topics=max_topics,
    )


def build_page_prompt(
    *,
    topic_title: str,
    topic_sources: list[str],
    related_modules: list[str],
) -> str:
    """Build the per-page prompt. `related_modules` is currently context-only
    (the LLM may consult them via Read); the deterministic ``## See also``
    block uses the same list."""
    safe_title = _sanitize_title(topic_title)
    sources_block = _format_path_list(topic_sources)
    return _PAGE_TEMPLATE.format(
        topic_title=safe_title,
        sources_block=sources_block,
        header_marker=HEADER_MARKER,
        footer_marker=FOOTER_MARKER,
    )
