"""Discover TypeScript modules via a three-tier cascade.

Cascade order (RESEARCH.md Pattern 1, locked short-circuit reading):

1. ``package.json#exports`` — the author-declared public-API contract.
2. ``tsconfig.json#include`` (and ``compilerOptions.rootDir`` when present)
   parsed as JSONC via :mod:`docagent.artifacts._jsonc`.
3. Filesystem glob over the TypeScript adapter's extensions.

The first signal that yields a non-empty set wins; later signals are NOT
unioned in. A wildcard-only ``exports`` map (every key or every leaf path
contains ``*``) is treated as "no signal" and downgraded to the fallback
with a WARN.

Barrel files (modules whose only exports are ``export * from ...`` /
``export { ... } from ...`` and which therefore expose zero original
symbols) are dropped: their public-surface table would be empty. The
parent's see-also block can still mention them by name; that's a renderer
concern, not a discovery one.

Path-traversal in exports values (``"./bad": "../../etc/passwd"``) is
rejected: the resolved path must stay inside ``repo_root``.
"""

from __future__ import annotations

import json
import posixpath
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pathspec

from docagent._logging import get_logger
from docagent.adapters.typescript import ExportEntry, TypeScriptAdapter
from docagent.artifacts._jsonc import parse_jsonc
from docagent.artifacts._module_discovery import (
    _EXCLUDED_TOP_DIRS,
    DiscoveredModule,
    ModuleSymbol,
    _is_public_leaf,
    parent_module,
    sibling_modules,
)

_log = get_logger("artifacts.api_reference.ts_discovery")

_TS_EXTS: tuple[str, ...] = (".d.ts", ".ts", ".tsx", ".mjs", ".cjs", ".js", ".jsx")
_STRIPPABLE_TS_PREFIXES: frozenset[str] = frozenset({"src", "lib", "dist"})
# TS-specific excluded top-level dirs, layered on top of _EXCLUDED_TOP_DIRS.
# node_modules is the obvious one; `dist` is NOT here because it's a
# strippable prefix in TS conventions (a path under `dist/` decomposes to
# the source name, mirroring `src/`).
_TS_EXCLUDED_TOP_DIRS: frozenset[str] = _EXCLUDED_TOP_DIRS | frozenset({"node_modules"})
# Conditional-key order for resolving an exports-map entry: we want any
# concrete file path; ``default`` is the broadest, then runtime conditions.
_EXPORT_CONDITIONS: tuple[str, ...] = ("default", "import", "require", "types", "node")


# ---------------------------------------------------------------------------
# Dotted-name conversion
# ---------------------------------------------------------------------------


def _file_to_dotted_ts(file_rel: str) -> str | None:
    """Convert a repo-relative POSIX path to a dotted TS module name.

    Strips a leading ``src``/``lib``/``dist`` segment, then drops the longest
    matching extension from :data:`_TS_EXTS`. Returns ``None`` for paths in
    excluded top-level directories (``tests``, ``node_modules``, etc.) or
    paths whose extension is not a TS variant.
    """
    parts = file_rel.split("/")
    if not parts:
        return None
    # Strippable TS prefixes (src/lib/dist) win over the excluded-top-dir
    # rule because they are conventions ("the source lives here"); a plain
    # `tests/` or `node_modules/` directory drops via the excluded check
    # AFTER strippable prefixes have peeled.
    while parts and parts[0] in _STRIPPABLE_TS_PREFIXES:
        parts = parts[1:]
    if not parts or parts[0] in _TS_EXCLUDED_TOP_DIRS:
        return None
    last = parts[-1]
    matched_ext = next((e for e in _TS_EXTS if last.endswith(e)), None)
    if matched_ext is None:
        return None
    stripped = last[: -len(matched_ext)]
    if not stripped:
        return None
    parts[-1] = stripped
    return ".".join(parts)


# ---------------------------------------------------------------------------
# package.json#exports
# ---------------------------------------------------------------------------


def _resolve_conditional(node: Any) -> str | None:
    """Pick *some* concrete file string from a conditional-export subtree."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        for cond in _EXPORT_CONDITIONS:
            if cond in node:
                resolved = _resolve_conditional(node[cond])
                if resolved is not None:
                    return resolved
        for v in node.values():
            resolved = _resolve_conditional(v)
            if resolved is not None:
                return resolved
    return None


def _is_inside(repo_root: Path, candidate: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return False


def _normalize_to_source(repo_root: Path, exports_path: str) -> str | None:
    """Map an exports-map path to a repo-relative POSIX source path.

    Rejects path-traversal (``../``) and absolute paths. If the path points
    at a compiled artifact under ``dist/`` (the conventional ``./dist/x.js``
    pattern), try the ``src/x.<ts-ext>`` peer.
    """
    if exports_path.startswith("/"):
        _log.warning(
            "package.json#exports entry is an absolute path; skipping: %s", exports_path
        )
        return None
    # Strip a leading "./" for cleaner posix joining.
    rel = exports_path[2:] if exports_path.startswith("./") else exports_path
    if rel.startswith("../") or "/../" in rel or rel == "..":
        _log.warning(
            "package.json#exports entry uses path-traversal; skipping: %s", exports_path
        )
        return None
    candidate = (repo_root / rel).resolve()
    if not _is_inside(repo_root, candidate):
        _log.warning(
            "package.json#exports entry escapes repo_root; skipping: %s", exports_path
        )
        return None
    # If the entry points at a compiled JS path under dist/, look for the
    # source peer under src/.
    parts = rel.split("/")
    if parts and parts[0] == "dist":
        rest = parts[1:]
        if rest:
            last = rest[-1]
            for js_ext in (".js", ".mjs", ".cjs", ".jsx"):
                if last.endswith(js_ext):
                    base = last[: -len(js_ext)]
                    for src_ext in _TS_EXTS:
                        candidate_src = repo_root / "src" / "/".join(rest[:-1]) / (base + src_ext)
                        if candidate_src.is_file():
                            return posixpath.normpath(
                                "/".join(["src", *rest[:-1], base + src_ext])
                            )
                    break
    # Otherwise return the path as-is (already POSIX since we never path-joined).
    return posixpath.normpath(rel)


def _files_from_exports_map(repo_root: Path) -> set[str] | None:
    """Return the set of source files declared by ``package.json#exports``.

    Returns ``None`` when there is no exports map (caller falls through).
    Returns ``set()`` when the exports map is wildcard-only — the caller
    treats this identically to "absent" but the WARN is emitted here.
    """
    pkg_path = repo_root / "package.json"
    if not pkg_path.is_file():
        return None
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _log.warning("package.json failed to parse as JSON: %s", exc)
        return None
    exports = data.get("exports")
    if exports is None:
        return None

    # String form: `"exports": "./index.js"`
    candidate_paths: list[str] = []
    all_wildcard = True
    if isinstance(exports, str):
        candidate_paths.append(exports)
        all_wildcard = "*" in exports
    elif isinstance(exports, dict):
        for subpath_key, value in exports.items():
            if "*" in subpath_key:
                continue
            resolved = _resolve_conditional(value)
            if resolved is None:
                continue
            if "*" in resolved:
                continue
            candidate_paths.append(resolved)
            all_wildcard = False
        if not candidate_paths and exports:
            all_wildcard = True
    else:
        _log.warning("package.json#exports has unexpected type: %s", type(exports).__name__)
        return None

    if not candidate_paths:
        if all_wildcard:
            _log.warning(
                "package.json#exports is wildcard-only; falling back to tsconfig.include"
            )
        return set()

    out: set[str] = set()
    for path in candidate_paths:
        normalized = _normalize_to_source(repo_root, path)
        if normalized is not None:
            out.add(normalized)
    return out


# ---------------------------------------------------------------------------
# tsconfig.json#include
# ---------------------------------------------------------------------------


def _glob_to_pathspec_pattern(pattern: str) -> str:
    """tsconfig.include patterns are git-style globs. pathspec handles them."""
    return pattern


def _files_from_tsconfig_include(repo_root: Path) -> set[str]:
    """Enumerate TS source files matched by ``tsconfig.json#include``."""
    tsconfig_path = repo_root / "tsconfig.json"
    if not tsconfig_path.is_file():
        return set()
    try:
        data = parse_jsonc(tsconfig_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _log.warning("tsconfig.json failed to parse as JSONC: %s", exc)
        return set()
    include = data.get("include")
    if not isinstance(include, list):
        return set()
    patterns: list[str] = [p for p in include if isinstance(p, str)]
    if not patterns:
        return set()
    spec = pathspec.GitIgnoreSpec.from_lines(patterns)

    out: set[str] = set()
    for ext in _TS_EXTS:
        for path in repo_root.rglob(f"*{ext}"):
            rel = path.relative_to(repo_root).as_posix()
            if any(seg in _EXCLUDED_TOP_DIRS for seg in rel.split("/")):
                continue
            if spec.match_file(rel):
                out.add(rel)
    return out


# ---------------------------------------------------------------------------
# Filesystem glob (final fallback)
# ---------------------------------------------------------------------------


def _files_from_glob(repo_root: Path) -> set[str]:
    out: set[str] = set()
    for ext in _TS_EXTS:
        for path in repo_root.rglob(f"*{ext}"):
            rel = path.relative_to(repo_root).as_posix()
            if any(seg in _EXCLUDED_TOP_DIRS for seg in rel.split("/")):
                continue
            out.add(rel)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_ts_modules(
    repo_root: Path,
    symbol_rows: list[tuple],
    file_hashes: dict[str, str],
) -> tuple[list[DiscoveredModule], dict[str, list[ExportEntry]]]:
    """Discover documentable TS modules + their export edges.

    ``symbol_rows`` is the same tuple shape ``discover_python_modules`` accepts,
    optionally including a trailing ``existing_doc`` field for the JSDoc text
    captured by the adapter (Plan 07-05 extends ``ModuleSymbol`` to carry it).

    Returns a tuple:
      * sorted ``list[DiscoveredModule]``
      * ``dict[str, list[ExportEntry]]`` keyed by ``dotted_name`` — the raw
        export edges per surviving module (used by the renderer's
        "Exported as" column).
    """
    # ---- cascade: stop at the first non-empty signal ----
    files_from_exports = _files_from_exports_map(repo_root)
    candidate_files = (
        files_from_exports
        or _files_from_tsconfig_include(repo_root)
        or _files_from_glob(repo_root)
    )

    # ---- index symbol rows by file ----
    rows_by_file: dict[str, list[tuple]] = {}
    for row in symbol_rows:
        file_rel = row[2]
        rows_by_file.setdefault(file_rel, []).append(row)

    # ---- group by dotted-name + filter private leaves ----
    grouped: dict[str, list[ModuleSymbol]] = {}
    file_for_module: dict[str, str] = {}
    for file_rel in sorted(candidate_files):
        dotted = _file_to_dotted_ts(file_rel)
        if dotted is None:
            continue
        for row in rows_by_file.get(file_rel, []):
            qn = row[0]
            if not _is_public_leaf(qn):
                continue
            kind = row[1]
            line_start = int(row[3])
            line_end = int(row[4])
            signature = row[5] if len(row) > 5 else ""
            existing_doc = row[6] if len(row) > 6 else None
            grouped.setdefault(dotted, []).append(
                _build_module_symbol(qn, kind, signature or "", line_start, line_end, existing_doc)
            )
            file_for_module.setdefault(dotted, file_rel)
        # Even files with no public symbols still need a placeholder so the
        # barrel-detection pass can look at them. We only register file_for_module
        # if at least one row was found; otherwise the module won't survive.

    # ---- barrel-file drop ----
    adapter = TypeScriptAdapter()
    export_edges: dict[str, list[ExportEntry]] = {}
    out: list[DiscoveredModule] = []
    for dotted in sorted(grouped):
        file_rel = file_for_module[dotted]
        symbols = sorted(grouped[dotted], key=lambda s: s.line_start)
        # Parse the file and inspect its export edges for the renderer.
        edges = _safe_extract_exports(adapter, repo_root, file_rel)
        if not symbols and edges and all(e.kind == "re_export" for e in edges):
            # Barrel file with no original symbols — skip.
            continue
        if not symbols:
            continue
        export_edges[dotted] = edges
        out.append(
            DiscoveredModule(
                dotted_name=dotted,
                file_rel=file_rel,
                public_symbols=tuple(symbols),
            )
        )

    # Also evaluate candidate files with no symbols but having exports —
    # these are the pure barrel files. We've already filtered them above,
    # but we explicitly drop their dotted names here in case a caller passed
    # synthetic rows.
    for file_rel in candidate_files:
        dotted = _file_to_dotted_ts(file_rel)
        if dotted is None or dotted in {m.dotted_name for m in out}:
            continue
        edges = _safe_extract_exports(adapter, repo_root, file_rel)
        if edges and all(e.kind == "re_export" for e in edges):
            # Barrel file — explicitly do NOT add. Kept loop for symmetry.
            continue

    return out, export_edges


def _build_module_symbol(
    qualified_name: str,
    kind: str,
    signature: str,
    line_start: int,
    line_end: int,
    existing_doc: str | None,
) -> ModuleSymbol:
    """Construct a ModuleSymbol, tolerating either the legacy 5-field shape
    or the 7-field shape introduced in Plan 07-05.

    Falls back to positional construction if ``existing_doc`` is not a
    supported kwarg yet.
    """
    try:
        return ModuleSymbol(  # type: ignore[call-arg]
            qualified_name=qualified_name,
            kind=kind,
            signature=signature,
            line_start=line_start,
            line_end=line_end,
            existing_doc=existing_doc,
        )
    except TypeError:
        return ModuleSymbol(
            qualified_name=qualified_name,
            kind=kind,
            signature=signature,
            line_start=line_start,
            line_end=line_end,
        )


def _safe_extract_exports(
    adapter: TypeScriptAdapter, repo_root: Path, file_rel: str
) -> list[ExportEntry]:
    full = repo_root / file_rel
    if not full.is_file():
        return []
    try:
        src = full.read_bytes()
        parsed = adapter.parse(full, src)
        return list(adapter.extract_exports(parsed))
    except Exception as exc:  # pragma: no cover — defensive guard
        _log.warning("extract_exports failed for %s: %s", file_rel, exc)
        return []


def sibling_modules_ts(target: str, all_modules: Iterable[str]) -> list[str]:
    """Delegate to the language-agnostic dotted-prefix helper."""
    return sibling_modules(target, list(all_modules))


def parent_module_ts(target: str) -> str | None:
    return parent_module(target)
