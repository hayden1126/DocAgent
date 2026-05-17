"""Prompt template for the ``api_reference`` artifact.

One LLM call per module produces TWO marker-delimited sections — the opener
paragraph and the worked-examples block. The deterministic infrastructure
(:mod:`docagent.artifacts._api_reference_render`) handles frontmatter,
public-surface table, see-also section, and footer hint.

Markers are intentionally distinctive ASCII so a flaky model is unlikely to
emit them by accident inside narrative prose.

PROMPT_VERSION bump rationale (Phase 7): the constant moved from "1" to "2"
when this template gained the ``{language_descriptor}`` placeholder + the
optional TS-only JSDoc-section paragraph. Because the per-module fingerprint
includes prompt_version, the first post-Phase-7 ``docagent update`` run will
regenerate every existing Python ``api_reference`` page exactly once.
"""

# Phase 7: bumped 1→2 for TS dispatch; one-time Python fingerprint invalidation, see 07-SUMMARY.md
PROMPT_VERSION = "2"

OPENER_MARKER = "<<<OPENER>>>"
WORKFLOWS_MARKER = "<<<WORKFLOWS>>>"

_LANGUAGE_DESCRIPTORS = {
    "python": "Python",
    "typescript": "TypeScript",
}

_JSDOC_SECTION_PY = ""
_JSDOC_SECTION_TS = (
    "The public-surface table above already contains JSDoc-derived "
    "summaries (the text after the em-dash in the Signature column). "
    "Do not re-paraphrase those — your opener should describe what the "
    "MODULE is for, not restate each symbol's tag descriptions."
)

API_REFERENCE_PROMPT = """\
You are writing one curated reference page for the {language_descriptor} module
`{dotted_name}` (source file: `{file_rel}`).

A deterministic pipeline has already prepared the page's frontmatter, H1,
public-surface table, see-also section, and footer. Your job is exactly TWO
sections, delimited by the markers shown below.

## Public symbols in this module (for your context — already rendered as a
## table by the pipeline, do not repeat them):
{symbol_table}

{jsdoc_section}

## Sibling modules in the same package (for context only — do not document
## them here):
{siblings_block}

## Procedure
1. Use the Read tool to inspect `{file_rel}` before writing anything.
2. If helpful, Glob / Grep to find call sites or relevant tests. Don't fan
   out widely — one or two reads is usually enough.
3. Write the opener and workflows. Ground every claim.

## Required output format

Emit exactly these two markers with content between. No preamble. No
trailing prose after the second block.

{opener_marker}
[A 2-4 sentence paragraph describing what this module is for. Cover its
purpose and how the listed public symbols relate to one another. End the
paragraph with one ground citation, e.g.:
`<!-- ground: {file_rel}:1-40 -->`]

{workflows_marker}
[One to three short worked examples that exercise the most-used public
symbols. Each example is a fenced ```python code block followed by a single
ground citation pointing at lines in `{file_rel}` that demonstrate the
pattern (or define the function being used). Brief one-line prose between
blocks is fine if it adds context.]

## Rules
- Use the Read, Glob, Grep tools to inspect source before grounding claims.
- Every non-trivial claim or example must carry a `<!-- ground: -->` comment
  immediately after the sentence or fenced block it grounds.
- Paths in citations are repo-relative; line ranges must reference real
  lines you have actually read.
- Do not document sibling modules — their pages are written separately.
- Do not include frontmatter, an H1, a `## Public surface` table, a
  `## See also` section, or a footer. The pipeline produces all of those.
- Do not invent symbols, parameters, or behavior. If a worked example would
  require speculation, omit it.
- If the module is very small (one or two public symbols), the opener may
  be a single sentence and workflows may have a single example.

Emit only the two marker blocks and their contents.
"""


def format_prompt(
    dotted_name: str,
    file_rel: str,
    symbol_table: str,
    siblings_block: str,
    language: str = "python",
) -> str:
    descriptor = _LANGUAGE_DESCRIPTORS.get(language, _LANGUAGE_DESCRIPTORS["python"])
    jsdoc_section = _JSDOC_SECTION_TS if language == "typescript" else _JSDOC_SECTION_PY
    return API_REFERENCE_PROMPT.format(
        language_descriptor=descriptor,
        dotted_name=dotted_name,
        file_rel=file_rel,
        symbol_table=symbol_table,
        jsdoc_section=jsdoc_section,
        siblings_block=siblings_block,
        opener_marker=OPENER_MARKER,
        workflows_marker=WORKFLOWS_MARKER,
    )
