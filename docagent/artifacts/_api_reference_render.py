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

from collections.abc import Mapping
from typing import Any

from docagent.artifacts._module_discovery import ModuleSymbol

_SIGNATURE_MAX = 120
_JSDOC_BRIEF_MAX = 80
_FOOTER_HINT = (
    "<!-- For rendered per-symbol details, point mkdocstrings or pdoc at "
    "this module. -->"
)


def _entry_attr(entry: Any, name: str, default: Any = None) -> Any:
    """Read a field on either an ``ExportEntry`` or a plain mapping."""
    if isinstance(entry, Mapping):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _render_exported_as(entry: Any) -> str:
    """Render the cell content for the ``Exported as`` column.

    * ``export * from "./other"`` → ``(re-export *)``
    * ``export { Foo as Bar } from "./other"`` → ``Bar (from other.Foo)``
    * ``export { Bar } from "./other"`` → ``Bar (from other)``
    * Originals → ``—``
    """
    kind = _entry_attr(entry, "kind")
    if kind != "re_export":
        return "—"
    name = str(_entry_attr(entry, "name", ""))
    source_module = _entry_attr(entry, "source_module")
    alias_of = _entry_attr(entry, "alias_of")
    if name == "*":
        return "(re-export *)"
    source_dotted = _source_to_dotted(source_module)
    if alias_of:
        return f"{name} (from {source_dotted}.{alias_of})"
    if source_dotted:
        return f"{name} (from {source_dotted})"
    return name


def _source_to_dotted(source_module: Any) -> str:
    """Strip surrounding quotes, leading ``./`` and trailing extension."""
    if not isinstance(source_module, str) or not source_module:
        return ""
    text = source_module.strip()
    if text.startswith("./"):
        text = text[2:]
    # Strip a trailing JS/TS extension (we want the dotted form, not the file).
    for ext in (".d.ts", ".ts", ".tsx", ".mjs", ".cjs", ".js", ".jsx"):
        if text.endswith(ext):
            text = text[: -len(ext)]
            break
    # Reject path-traversal noise as a defense-in-depth move; the discovery
    # module guards too, but we don't want bad strings leaking through.
    while text.startswith("../"):
        text = text[3:]
    return text.replace("/", ".")


def _truncate_jsdoc_brief(brief: str) -> str:
    """Pull the first line, strip whitespace, cap at the brief-column limit."""
    if not brief:
        return ""
    first_line = brief.strip().splitlines()[0].strip() if brief.strip() else ""
    if len(first_line) <= _JSDOC_BRIEF_MAX:
        return first_line
    return first_line[: _JSDOC_BRIEF_MAX - 1].rstrip() + "…"


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
    dotted_name: str,
    symbols: tuple[ModuleSymbol, ...],
    export_edges: Mapping[str, Any] | list[Any] | None = None,
    existing_docs: Mapping[str, str] | None = None,
) -> str:
    """Render the public-surface section.

    Symbols are listed under their leaf name (the form most likely to appear
    in prose) with their kind and a truncated signature. No anchor links —
    we don't render per-symbol pages, so promising navigation that doesn't
    work is worse than a plain table (the plan agent's call).

    Optional Phase-7 extensions:

    * ``export_edges`` — when non-empty, an extra ``Exported as`` column is
      appended. Aliased re-exports render as ``Bar (from other.Foo)``;
      ``export *`` shows ``(re-export *)``; originals show ``—``.
    * ``existing_docs`` — when non-empty, the Signature column is suffixed
      with ``` — <brief>``` for any symbol whose qualified_name has a
      JSDoc brief.
    """
    if not symbols:
        return "## Public surface\n\n*(none)*\n"

    # Normalize export_edges into a name → entry lookup. We accept either a
    # mapping keyed by leaf name OR a list of ExportEntry-like objects.
    edge_by_name: dict[str, Any] = {}
    has_edges = False
    if export_edges:
        if isinstance(export_edges, Mapping):
            edge_by_name = dict(export_edges)
            has_edges = True
        else:
            for entry in export_edges:
                name = _entry_attr(entry, "name")
                if isinstance(name, str):
                    edge_by_name[name] = entry
            has_edges = bool(edge_by_name)

    has_docs = bool(existing_docs)

    header_cols = ["Name", "Kind", "Signature"]
    divider_cols = ["------", "------", "-----------"]
    if has_edges:
        header_cols.append("Exported as")
        divider_cols.append("-----------")

    lines = [
        "## Public surface",
        "",
        "| " + " | ".join(header_cols) + " |",
        "|" + "|".join(divider_cols) + "|",
    ]
    seen: set[str] = set()
    for sym in symbols:
        leaf = (
            sym.qualified_name[len(dotted_name) + 1 :]
            if sym.qualified_name.startswith(dotted_name + ".")
            else sym.qualified_name
        )
        if leaf in seen:
            continue
        seen.add(leaf)
        sig = _truncate_signature(sym.signature or leaf)
        sig_rendered = sig
        if has_docs:
            brief = ""
            if existing_docs is not None:
                brief = existing_docs.get(sym.qualified_name, "") or existing_docs.get(leaf, "")
            if not brief and sym.existing_doc:
                brief = sym.existing_doc
            brief_short = _truncate_jsdoc_brief(brief)
            if brief_short:
                sig_rendered = f"{sig} — {brief_short}"
        cells = [
            f"`{_escape_pipe(leaf)}`",
            sym.kind,
            f"`{_escape_pipe(sig_rendered)}`",
        ]
        if has_edges:
            cells.append(_escape_pipe(_render_exported_as(edge_by_name.get(leaf))))
        lines.append("| " + " | ".join(cells) + " |")
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
    export_edges: Mapping[str, Any] | list[Any] | None = None,
    existing_docs: Mapping[str, str] | None = None,
) -> str:
    """Compose the full module page. ``opener_md`` and ``workflows_md`` are
    the LLM-generated chunks (already cleaned). Empty values get a
    placeholder so a flaky model response doesn't sink the whole file.

    ``export_edges`` / ``existing_docs`` are forwarded to
    :func:`public_surface_table`; both default to ``None`` so the Python
    call path renders identically to pre-Phase-7 output."""
    opener = opener_md.strip() or "*See public surface below.*"
    workflows = workflows_md.strip() or "*No worked examples emitted for this module.*"
    parts = [
        frontmatter(dotted_name),
        h1(dotted_name),
        "",
        opener,
        "",
        public_surface_table(
            dotted_name,
            symbols,
            export_edges=export_edges,
            existing_docs=existing_docs,
        ),
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
