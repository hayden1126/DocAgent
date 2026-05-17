"""Deterministic Markdown chunks for `how_to_guides` pages.

The artifact composes its final page as:
  `assemble_page(frontmatter, llm_body, see_also)`
where frontmatter and see-also are byte-stable across runs given the same
inputs, and llm_body is whatever the per-page LLM call produced.

Pure functions only. No I/O, no LLM, no orchestrator deps.
"""

from __future__ import annotations


def render_frontmatter(*, title: str, slug: str) -> str:
    """Minimal YAML frontmatter. Title is quoted to handle colons.

    Slug is unquoted (`topic_slug` already restricts it to `[a-z0-9-]+`).
    """
    safe_title = title.replace('"', '\\"')
    return (
        "---\n"
        f'title: "{safe_title}"\n'
        f"slug: {slug}\n"
        "docagent_artifact: how_to_guides\n"
        "---\n"
    )


def render_see_also(
    *, related_modules: list[str], related_slugs: list[str]
) -> str:
    """Render the '## See also' block.

    Modules are listed first (sorted), then sibling how-to slugs (sorted).
    Module links use `../reference/<dotted>.md`; sibling links use
    `./<slug>.md`. Returns '' if both lists are empty.
    """
    if not related_modules and not related_slugs:
        return ""
    lines: list[str] = ["## See also", ""]
    for mod in sorted(related_modules):
        lines.append(f"- [{mod}](../reference/{mod}.md)")
    for slug in sorted(related_slugs):
        lines.append(f"- [{slug}](./{slug}.md)")
    lines.append("")
    return "\n".join(lines)


def assemble_page(*, frontmatter: str, body: str, see_also: str) -> str:
    """Glue the three sections together.

    Skips empty sections. Inserts exactly one blank line between non-empty
    sections. Guarantees exactly one trailing newline.
    """
    parts: list[str] = []
    for chunk in (frontmatter, body, see_also):
        if chunk:
            parts.append(chunk.rstrip("\n"))
    out = "\n\n".join(parts)
    return out + "\n" if out else ""
