"""Deterministic Markdown rendering for ``api_reference``.

The artifact's output per module is a sandwich: deterministic top
(frontmatter + H1) + LLM opener + deterministic middle (public-surface
table) + LLM workflows + deterministic bottom (see-also + footer). The
splice happens in the artifact; this module only owns the deterministic
chunks.

Why pure functions instead of a class: each chunk is independently testable
against a list of ``ModuleSymbol`` rows. No state, no I/O. The artifact
composes the chunks.
"""

from __future__ import annotations

from docagent.artifacts._module_discovery import ModuleSymbol

_SIGNATURE_MAX = 120
_FOOTER_HINT = (
    "<!-- For rendered per-symbol details, point mkdocstrings or pdoc at "
    "this module. -->"
)


def frontmatter(dotted_name: str) -> str:
    """Minimal YAML frontmatter so mkdocs/Hugo can route, and so the
    post-write hook can recognize the file as DocAgent-owned."""
    return (
        "---\n"
        "docagent_artifact: api_reference\n"
        f"module: {dotted_name}\n"
        "generated_by: docagent\n"
        "---\n"
    )


def h1(dotted_name: str) -> str:
    return f"# `{dotted_name}`\n"


def _truncate_signature(sig: str) -> str:
    sig = sig.replace("\n", " ").strip()
    if len(sig) <= _SIGNATURE_MAX:
        return sig
    return sig[: _SIGNATURE_MAX - 1].rstrip() + "…"


def _escape_pipe(text: str) -> str:
    return text.replace("|", "\\|")


def public_surface_table(
    dotted_name: str, symbols: tuple[ModuleSymbol, ...]
) -> str:
    """Render the public-surface section.

    Symbols are listed under their leaf name (the form most likely to appear
    in prose) with their kind and a truncated signature. No anchor links —
    we don't render per-symbol pages, so promising navigation that doesn't
    work is worse than a plain table (the plan agent's call).
    """
    if not symbols:
        return "## Public surface\n\n*(none)*\n"

    lines = [
        "## Public surface",
        "",
        "| Name | Kind | Signature |",
        "|------|------|-----------|",
    ]
    seen: set[str] = set()
    for sym in symbols:
        leaf = sym.qualified_name[len(dotted_name) + 1 :] if sym.qualified_name.startswith(
            dotted_name + "."
        ) else sym.qualified_name
        if leaf in seen:
            continue
        seen.add(leaf)
        sig = _truncate_signature(sym.signature or leaf)
        lines.append(
            f"| `{_escape_pipe(leaf)}` | {sym.kind} | `{_escape_pipe(sig)}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _relative_link(target_dotted: str) -> str:
    return f"{target_dotted}.md"


def see_also_section(
    dotted_name: str,
    siblings: list[str],
    parent: str | None,
) -> str:
    """Render the see-also section. Links are relative ``.md`` paths to
    sibling/parent pages — all of which the same ``api_reference`` run will
    produce, so the verifier's intra-artifact link carve-out is sufficient
    to keep CI green during init."""
    items: list[str] = []
    if parent is not None:
        items.append(f"- [`{parent}`]({_relative_link(parent)}) — parent package")
    for s in siblings:
        items.append(f"- [`{s}`]({_relative_link(s)})")
    if not items:
        return ""
    return "## See also\n\n" + "\n".join(items) + "\n"


def footer() -> str:
    return _FOOTER_HINT + "\n"


def assemble_page(
    dotted_name: str,
    symbols: tuple[ModuleSymbol, ...],
    siblings: list[str],
    parent: str | None,
    opener_md: str,
    workflows_md: str,
) -> str:
    """Compose the full module page. ``opener_md`` and ``workflows_md`` are
    the LLM-generated chunks (already cleaned). Empty values get a
    placeholder so a flaky model response doesn't sink the whole file."""
    opener = opener_md.strip() or "*See public surface below.*"
    workflows = workflows_md.strip() or "*No worked examples emitted for this module.*"
    parts = [
        frontmatter(dotted_name),
        h1(dotted_name),
        "",
        opener,
        "",
        public_surface_table(dotted_name, symbols),
        "## Common workflows",
        "",
        workflows,
        "",
    ]
    see_also = see_also_section(dotted_name, siblings, parent)
    if see_also:
        parts.append(see_also)
    parts.append(footer())
    return "\n".join(parts)
