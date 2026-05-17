"""TypeScript / JavaScript adapter.

Handles ``.ts``, ``.tsx``, ``.js``, ``.jsx``, ``.mjs``, ``.cjs``, and
``.d.ts``. Per-file grammar dispatch: TSX/JSX files parse with the ``tsx``
grammar, everything else with ``typescript`` — the latter is a superset and
handles plain JS correctly.

Symbol extraction only. v1 does not splice in-place JSDoc — that's a separate
post-alpha artifact. ``splice_doc`` raises ``NotImplementedError`` so the
contract is loud, not silent.

Qualified names are built by walking ancestors of each definition node: a
method inside ``class Foo`` inside ``namespace Outer`` becomes
``Outer.Foo.method``. Leaf-name matching against the mention index continues
to work via :func:`docagent.index.store.Store.known_symbol_names`.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

from docagent.adapters.base import (
    BuildContext,
    DocStyle,
    LanguageAdapter,
    ParseResult,
    Ref,
    Symbol,
    SymbolKind,
)
from docagent.parser import treesitter as ts


@dataclass(frozen=True, slots=True)
class ExportEntry:
    """One row of a TS module's public surface.

    * ``name`` — the public surface name (post-alias for ``export { Foo as Bar }``,
      ``"*"`` for ``export * from``, ``"default"`` for default exports).
    * ``kind`` — ``"re_export"`` when the entry rebinds another module's symbol,
      ``"original"`` for declarations exported directly.
    * ``source_module`` — the bare-string module specifier on the ``from``
      clause (e.g. ``"./foo"``), or ``None`` for originals.
    * ``alias_of`` — the original (pre-alias) name when aliased, else ``None``.
    """

    name: str
    kind: Literal["re_export", "original"]
    source_module: str | None
    alias_of: str | None

_TSX_EXTS = frozenset({".tsx", ".jsx"})
_ALL_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".d.ts")

# Ancestor node types that contribute to a qualified name. Body-only constructs
# (`statement_block`, function bodies) are deliberately absent — we don't want
# locally-scoped symbols escaping into the index.
_SCOPE_NODE_TYPES: dict[str, None] = {
    "class_declaration": None,
    "abstract_class_declaration": None,
    "interface_declaration": None,
    "internal_module": None,  # `namespace Foo {}`
    "module": None,  # `module Foo {}` with identifier name
}

# Maps the @def.<kind> capture name to a SymbolKind in our index.
_CAPTURE_TO_KIND: dict[str, SymbolKind] = {
    "def.function": "function",
    "def.class": "class",
    "def.method": "method",
    "def.interface": "interface",
    "def.type_alias": "type_alias",
    "def.enum": "enum",
    "def.module": "module",
}

_JSDOC_STYLE = DocStyle(
    delim_open="/**",
    delim_close=" */",
    line_prefix=" * ",
    placement="above",
)

_JSDOC_OPEN = b"/**"


def _clean_jsdoc_body(raw: str) -> str:
    """Strip ``/**``/``*/`` delimiters and per-line ``* `` prefixes.

    Preserves blank lines between paragraphs (collapsing runs of 2+ blank
    lines down to 1). ``@param``/``@returns``/``@throws`` tag text survives
    verbatim; the cleaner does not parse or restructure tags.
    """
    text = raw
    if text.startswith("/**"):
        text = text[3:]
    if text.endswith("*/"):
        text = text[:-2]
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("* "):
            stripped = stripped[2:]
        elif stripped.startswith("*"):
            stripped = stripped[1:]
        cleaned.append(stripped.rstrip())
    # Collapse runs of 2+ blank lines to one.
    collapsed: list[str] = []
    blank_run = 0
    for line in cleaned:
        if line == "":
            blank_run += 1
            if blank_run <= 1:
                collapsed.append(line)
        else:
            blank_run = 0
            collapsed.append(line)
    return "\n".join(collapsed).strip()


def _load_query() -> str:
    return (
        resources.files("docagent.adapters.queries")
        .joinpath("typescript_tags.scm")
        .read_text(encoding="utf-8")
    )


def _load_export_query() -> str:
    return (
        resources.files("docagent.adapters.queries")
        .joinpath("typescript_exports.scm")
        .read_text(encoding="utf-8")
    )


_QUERY = _load_query()
_EXPORT_QUERY = _load_export_query()


def _strip_string_literal(text: str) -> str:
    """Strip surrounding ``"`` / ``'`` / backtick quotes from a string literal."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'", "`"):
        return text[1:-1]
    return text


def _declared_names(node, src: bytes) -> list[str]:
    """Walk a declaration node and return the declared identifier name(s)."""
    out: list[str] = []
    if node.type in ("function_declaration", "generator_function_declaration", "class_declaration", "abstract_class_declaration", "interface_declaration", "type_alias_declaration", "enum_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            out.append(src[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace"))
    elif node.type in ("lexical_declaration", "variable_declaration"):
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node is not None and name_node.type == "identifier":
                    out.append(src[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace"))
    return out


def _grammar_for(path: Path) -> str:
    """Pick the grammar key — TSX for JSX-bearing files, TS otherwise.

    ``.d.ts`` files are picked up by the ``.ts`` branch via the longest-suffix
    check in the scanner; here we just need to choose grammar.
    """
    if path.suffix in _TSX_EXTS:
        return "tsx"
    return "typescript"


def _node_name_text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _ancestor_scope_path(node, src: bytes) -> list[str]:
    """Walk parents of ``node`` and collect names of scope-contributing
    containers, root-to-leaf."""
    scope: list[str] = []
    parent = node.parent
    while parent is not None:
        if parent.type in _SCOPE_NODE_TYPES:
            name_node = parent.child_by_field_name("name")
            if name_node is not None:
                scope.append(_node_name_text(name_node, src))
        parent = parent.parent
    scope.reverse()
    return scope


def _lines_between_are_blank(src: bytes, first_line: int, last_line: int) -> bool:
    """Return True if every source line in [first_line, last_line] is blank.

    Line indices are 0-based (matching tree-sitter's ``start_point``).
    """
    if first_line > last_line:
        return True
    text = src.decode("utf-8", errors="replace")
    lines = text.splitlines()
    for i in range(first_line, last_line + 1):
        if i < 0 or i >= len(lines):
            continue
        if lines[i].strip() != "":
            return False
    return True


def _is_private_method_name(name: str) -> bool:
    """Skip constructors and ECMAScript-private (`#foo`) members.

    Constructors are never referenced by name in prose; treating them as
    symbols pollutes the mention index and the qualified-name fan-out.
    """
    return name == "constructor" or name.startswith("#")


class TypeScriptAdapter(LanguageAdapter):
    language_id = "typescript"
    file_extensions = _ALL_EXTS

    def parse(self, path: Path, src: bytes) -> ParseResult:
        grammar = _grammar_for(path)
        tree = ts.parse_source(grammar, src)
        return ParseResult(
            file=path,
            tree=tree,
            source=src,
            has_errors=tree.root_node.has_error,
        )

    def extract_symbols(self, parsed: ParseResult) -> list[Symbol]:
        grammar = _grammar_for(parsed.file)
        captures = ts.run_query(grammar, parsed.tree, _QUERY)
        src = parsed.source

        # The query interleaves @def.<kind> and @name captures, and names of
        # nested defs land inside the byte range of their outer def. Pair each
        # name with its TIGHTEST enclosing def — the smallest span that still
        # contains the name's bytes. Otherwise an outer ``class Foo`` def gets
        # paired with the first inner method's name and ``Foo`` is lost.
        defs: list[tuple[object, SymbolKind]] = []
        names: list[object] = []
        jsdoc_comments: list[object] = []
        for node, cap in captures:
            if cap == "name":
                names.append(node)
            elif cap in _CAPTURE_TO_KIND:
                defs.append((node, _CAPTURE_TO_KIND[cap]))
            elif cap == "jsdoc.candidate" and (
                src[node.start_byte : node.start_byte + 3] == _JSDOC_OPEN
            ):
                jsdoc_comments.append(node)
        jsdoc_comments.sort(key=lambda n: n.end_point[0])

        def_to_name: dict[int, object] = {}
        for name_node in names:
            best_span = None
            best_def_id = None
            for def_node, _ in defs:
                if (
                    def_node.start_byte <= name_node.start_byte
                    and name_node.end_byte <= def_node.end_byte
                ):
                    span = def_node.end_byte - def_node.start_byte
                    if best_span is None or span < best_span:
                        best_span = span
                        best_def_id = id(def_node)
            if best_def_id is not None and best_def_id not in def_to_name:
                def_to_name[best_def_id] = name_node

        seen: set[tuple[str, int]] = set()
        out: list[Symbol] = []

        for def_node, kind in defs:
            name_node = def_to_name.get(id(def_node))
            if name_node is None:
                continue

            leaf = _node_name_text(name_node, src)
            if kind == "method" and _is_private_method_name(leaf):
                continue

            scope = _ancestor_scope_path(def_node, src)
            qn = ".".join([*scope, leaf]) if scope else leaf

            # Dedupe overload signature + implementation pairs at the same name
            # and line. The TS grammar exposes both, and we want one row.
            key = (qn, def_node.start_point[0] + 1)
            if key in seen:
                continue
            seen.add(key)

            signature = (
                src[def_node.start_byte : min(def_node.end_byte, def_node.start_byte + 200)]
                .decode("utf-8", errors="replace")
                .split("\n")[0]
            )

            # Pair the latest /** comment whose end-line falls in
            # [def.start_line - 2, def.start_line - 1] — i.e. immediately
            # above, allowing exactly 0 or 1 blank line between. Intervening
            # non-blank content (e.g. `const x = 1;`) breaks the pairing.
            def_start_line = def_node.start_point[0]
            existing_doc: str | None = None
            existing_doc_byte_range: tuple[int, int] | None = None
            best_match = None
            for comment in jsdoc_comments:
                gap = def_start_line - (comment.end_point[0] + 1)
                if gap not in (0, 1):
                    continue
                if gap == 1 and not _lines_between_are_blank(
                    src, comment.end_point[0] + 1, def_start_line - 1
                ):
                    continue
                best_match = comment
            if best_match is not None:
                raw = src[best_match.start_byte : best_match.end_byte].decode(
                    "utf-8", errors="replace"
                )
                existing_doc = _clean_jsdoc_body(raw)
                existing_doc_byte_range = (best_match.start_byte, best_match.end_byte)

            out.append(
                Symbol(
                    qualified_name=qn,
                    kind=kind,
                    file=parsed.file,
                    byte_start=def_node.start_byte,
                    byte_end=def_node.end_byte,
                    line_start=def_node.start_point[0] + 1,
                    line_end=def_node.end_point[0] + 1,
                    signature=signature,
                    existing_doc=existing_doc,
                    existing_doc_byte_range=existing_doc_byte_range,
                )
            )
        return out

    def extract_exports(self, parsed: ParseResult) -> list[ExportEntry]:
        """Surface every ``export ...`` statement as a structured ``ExportEntry``.

        Used by the TS module-discovery cascade to distinguish barrel files
        (all-re-export, no original symbols) from empty modules.
        """
        grammar = _grammar_for(parsed.file)
        captures = ts.run_query(grammar, parsed.tree, _EXPORT_QUERY)
        src = parsed.source

        # Deduplicate export_statement nodes by start_byte (tree-sitter may
        # surface the same node under multiple matches).
        seen_stmts: dict[int, object] = {}
        for node, cap in captures:
            if cap == "export.stmt":
                seen_stmts.setdefault(node.start_byte, node)

        out: list[ExportEntry] = []
        for _, stmt in sorted(seen_stmts.items()):
            out.extend(self._exports_from_statement(stmt, src))
        return out

    @staticmethod
    def _exports_from_statement(stmt, src: bytes) -> list[ExportEntry]:
        """Parse a single ``export_statement`` node into one-or-more entries."""
        # Field-based lookups (tree-sitter-typescript reliably names these).
        source_node = stmt.child_by_field_name("source")
        decl_node = stmt.child_by_field_name("declaration")

        # Locate child structure: export_clause? + raw star token + default kw.
        export_clause = None
        has_star = False
        has_default = False
        for child in stmt.children:
            if child.type == "export_clause":
                export_clause = child
            elif child.type == "*":
                has_star = True
            elif child.type == "default":
                has_default = True

        source_module: str | None = None
        if source_node is not None:
            source_module = _strip_string_literal(
                src[source_node.start_byte : source_node.end_byte].decode(
                    "utf-8", errors="replace"
                )
            )

        out: list[ExportEntry] = []

        # `export * from "./foo"`
        if has_star and source_module is not None:
            out.append(
                ExportEntry(
                    name="*",
                    kind="re_export",
                    source_module=source_module,
                    alias_of=None,
                )
            )
            return out

        # `export { ... } [from "..."]` — named or aliased re-export.
        if export_clause is not None:
            for spec in export_clause.children:
                if spec.type != "export_specifier":
                    continue
                name_node = spec.child_by_field_name("name")
                alias_node = spec.child_by_field_name("alias")
                if name_node is None:
                    continue
                original = src[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                if alias_node is not None:
                    surface = src[alias_node.start_byte : alias_node.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    alias_of: str | None = original
                else:
                    surface = original
                    alias_of = None
                kind: Literal["re_export", "original"] = (
                    "re_export" if source_module is not None else "original"
                )
                out.append(
                    ExportEntry(
                        name=surface,
                        kind=kind,
                        source_module=source_module,
                        alias_of=alias_of,
                    )
                )
            return out

        # `export default <decl-or-expression>` — single "default" entry.
        if has_default:
            out.append(
                ExportEntry(
                    name="default",
                    kind="original",
                    source_module=None,
                    alias_of=None,
                )
            )
            return out

        # `export function foo() {}` / `export class Bar {}` / `export const x = ...`
        if decl_node is not None:
            for name in _declared_names(decl_node, src):
                out.append(
                    ExportEntry(
                        name=name,
                        kind="original",
                        source_module=None,
                        alias_of=None,
                    )
                )

        return out

    def doc_comment_style(self, sym: Symbol) -> DocStyle:
        return _JSDOC_STYLE

    def splice_doc(self, src: bytes, sym: Symbol, doc: str) -> bytes:
        raise NotImplementedError(
            "TypeScriptAdapter does not splice JSDoc in v1. The four "
            "single-file artifacts (README/AGENTS.md/CLAUDE.md/llms.txt) "
            "don't require in-place doc edits; a dedicated "
            "`typescript_docstrings` artifact is the right home for that."
        )

    def local_references(self, parsed: ParseResult) -> list[Ref]:
        return []  # lexical refs deferred; the citation gate catches most drift

    def semantic_references(self, repo_root: Path) -> list[Ref] | None:
        return None  # tsserver/LSP deepener is a v2 item

    def build_context(self, repo_root: Path) -> BuildContext | None:
        tsconfig = repo_root / "tsconfig.json"
        return BuildContext(tsconfig=tsconfig if tsconfig.is_file() else None)
