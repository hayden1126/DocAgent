"""Discover Python modules in the repo from the symbol index.

For each unique Python source file in ``symbols``, this module derives a
dotted module name and groups the file's *public* symbols under it. The list
is what ``ApiReferenceArtifact.plan`` walks — one task per dotted module.

What we deliberately don't do here:

- We don't parse ``__all__`` or resolve re-exports. A "public" symbol is one
  whose qualified-name has NO segment starting with ``_`` — so private
  classes and the methods nested under them are both filtered.
- We don't probe ``pyproject.toml`` for package metadata. ``src/`` layout is
  detected by path-prefix only; if a project has ``src/`` somewhere else, it
  won't be peeled.
- We don't follow `import` graphs. See-also entries are derived from sibling
  modules in the same package, not from actual imports.

These shortcuts are why this file is small. Add complexity later only when a
real repo demonstrates a failure.
"""

from __future__ import annotations

from dataclasses import dataclass

# Top-level directory names whose modules are not documented. Belt-and-braces
# over ``.docagentignore``; the scanner already excludes most of these but the
# symbol index can still hold rows for them on older runs.
_EXCLUDED_TOP_DIRS: frozenset[str] = frozenset(
    {"tests", "test", "docs", "scripts", "examples", "build", "dist", ".docagent"}
)


@dataclass(frozen=True, slots=True)
class ModuleSymbol:
    qualified_name: str
    kind: str
    signature: str
    line_start: int
    line_end: int
    existing_doc: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredModule:
    dotted_name: str
    file_rel: str  # repo-relative POSIX path
    public_symbols: tuple[ModuleSymbol, ...]


def _is_public_leaf(qualified_name: str) -> bool:
    segments = qualified_name.split(".")
    return bool(segments) and all(seg and not seg.startswith("_") for seg in segments)


def _file_to_dotted(file_rel: str) -> str | None:
    """Convert a repo-relative POSIX path to a dotted module name.

    Returns ``None`` if the path doesn't represent a documentable module
    (e.g. it's in an excluded directory or has a non-.py suffix).
    """
    parts = file_rel.split("/")
    if not parts or parts[0] in _EXCLUDED_TOP_DIRS:
        return None
    # src/ layout: strip a leading "src" segment.
    if parts and parts[0] == "src":
        parts = parts[1:]
        if not parts or parts[0] in _EXCLUDED_TOP_DIRS:
            return None
    if not parts:
        return None
    last = parts[-1]
    if last == "__init__.py":
        parts = parts[:-1]
    elif last.endswith(".py"):
        parts[-1] = last[:-3]
    elif last.endswith(".pyi"):
        # Stub files document the same module name as their .py sibling;
        # the dotted path is identical.
        parts[-1] = last[:-4]
    else:
        return None
    if not parts:
        # A bare ``__init__.py`` at the repo root has no dotted name.
        return None
    return ".".join(parts)


def discover_python_modules(
    symbol_rows: list[tuple],
) -> list[DiscoveredModule]:
    """Build the ordered list of documentable modules from raw symbol rows.

    ``symbol_rows`` is whatever a caller pulled from ``Store.symbols``; we
    keep the type loose so the store query and this function can evolve
    independently. The expected tuple shape is either:

    * 6-field: ``(qualified_name, kind, file, line_start, line_end, signature)``
    * 7-field: ``(qualified_name, kind, file, line_start, line_end, signature,
      existing_doc)`` — Phase 7 extension so TS rows can ferry JSDoc into the
      renderer.

    Either form is accepted; a 6-field row gets ``existing_doc=None`` on the
    ``ModuleSymbol``.
    """
    grouped: dict[str, list[ModuleSymbol]] = {}
    file_for_module: dict[str, str] = {}

    for row in symbol_rows:
        qn = row[0]
        kind = row[1]
        file_rel = row[2]
        line_start = row[3]
        line_end = row[4]
        signature = row[5] if len(row) > 5 else ""
        existing_doc = row[6] if len(row) > 6 else None
        if not _is_public_leaf(qn):
            continue
        dotted = _file_to_dotted(file_rel)
        if dotted is None:
            continue
        grouped.setdefault(dotted, []).append(
            ModuleSymbol(
                qualified_name=qn,
                kind=kind,
                signature=signature or "",
                line_start=int(line_start),
                line_end=int(line_end),
                existing_doc=existing_doc,
            )
        )
        file_for_module.setdefault(dotted, file_rel)

    out: list[DiscoveredModule] = []
    for dotted in sorted(grouped):
        symbols = sorted(grouped[dotted], key=lambda s: s.line_start)
        out.append(
            DiscoveredModule(
                dotted_name=dotted,
                file_rel=file_for_module[dotted],
                public_symbols=tuple(symbols),
            )
        )
    return out


def sibling_modules(target: str, all_modules: list[str]) -> list[str]:
    """Modules in the same package as ``target`` (excluding ``target`` itself).

    "Same package" = same dotted-prefix up to the last segment. Useful for
    the see-also section.
    """
    if "." not in target:
        # Top-level module — siblings are other top-level modules.
        prefix = ""
    else:
        prefix = target.rsplit(".", 1)[0] + "."
    out: list[str] = []
    for m in all_modules:
        if m == target:
            continue
        if prefix:
            if m.startswith(prefix) and "." not in m[len(prefix) :]:
                out.append(m)
        else:
            if "." not in m:
                out.append(m)
    return out


def parent_module(target: str) -> str | None:
    """Dotted parent package for ``target``, or ``None`` if top-level."""
    if "." not in target:
        return None
    return target.rsplit(".", 1)[0]
