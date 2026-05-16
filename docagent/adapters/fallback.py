"""Fallback adapter — tree-sitter only.

Used for languages without a dedicated deepener. Symbol extraction only;
in-place doc splicing is supported via byte-range insertion above the symbol
(language-appropriate comment prefix), but cross-references are lexical.
"""

from __future__ import annotations

from pathlib import Path

from docagent.adapters.base import (
    BuildContext,
    DocStyle,
    LanguageAdapter,
    ParseResult,
    Ref,
    Symbol,
)
from docagent.parser import treesitter as ts


# Minimal queries that capture function/class/method definitions across grammars.
# Per-language tuning lives here; for v1 we ship coarse, broadly-applicable patterns.
GENERIC_QUERIES: dict[str, str] = {
    "rust": """
        (function_item name: (identifier) @name) @def
        (struct_item name: (type_identifier) @name) @def
        (enum_item name: (type_identifier) @name) @def
        (trait_item name: (type_identifier) @name) @def
        (impl_item) @def
    """,
    "go": """
        (function_declaration name: (identifier) @name) @def
        (method_declaration name: (field_identifier) @name) @def
        (type_declaration (type_spec name: (type_identifier) @name)) @def
    """,
    "typescript": """
        (function_declaration name: (identifier) @name) @def
        (class_declaration name: (type_identifier) @name) @def
        (interface_declaration name: (type_identifier) @name) @def
        (method_definition name: (property_identifier) @name) @def
    """,
    "java": """
        (class_declaration name: (identifier) @name) @def
        (method_declaration name: (identifier) @name) @def
        (interface_declaration name: (identifier) @name) @def
    """,
    "cpp": """
        (function_definition declarator: (function_declarator declarator: (identifier) @name)) @def
        (class_specifier name: (type_identifier) @name) @def
        (struct_specifier name: (type_identifier) @name) @def
    """,
}

EXTENSIONS: dict[str, tuple[str, ...]] = {
    "rust": (".rs",),
    "go": (".go",),
    "typescript": (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
    "java": (".java",),
    "cpp": (".cc", ".cpp", ".cxx", ".hpp", ".hh", ".h"),
}

DOC_STYLES: dict[str, DocStyle] = {
    "rust": DocStyle(delim_open="", delim_close="", line_prefix="/// ", placement="above"),
    "go": DocStyle(delim_open="", delim_close="", line_prefix="// ", placement="above"),
    "typescript": DocStyle(delim_open="/**", delim_close=" */", line_prefix=" * ", placement="above"),
    "java": DocStyle(delim_open="/**", delim_close=" */", line_prefix=" * ", placement="above"),
    "cpp": DocStyle(delim_open="/**", delim_close=" */", line_prefix=" * ", placement="above"),
}


KIND_MAP: dict[str, dict[str, str]] = {
    "rust": {
        "function_item": "function",
        "struct_item": "class",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "class",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type_alias",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_definition": "method",
    },
    "java": {
        "class_declaration": "class",
        "method_declaration": "method",
        "interface_declaration": "interface",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "class",
    },
}


class FallbackAdapter(LanguageAdapter):
    def __init__(self, language_id: str) -> None:
        if language_id not in GENERIC_QUERIES:
            raise KeyError(f"No fallback query registered for: {language_id}")
        self.language_id = language_id
        self.file_extensions = EXTENSIONS[language_id]
        self._query = GENERIC_QUERIES[language_id]
        self._kinds = KIND_MAP[language_id]

    def parse(self, path: Path, src: bytes) -> ParseResult:
        tree = ts.parse_source(self.language_id, src)
        has_errors = tree.root_node.has_error
        return ParseResult(file=path, tree=tree, source=src, has_errors=has_errors)

    def extract_symbols(self, tree: ParseResult) -> list[Symbol]:
        captures = ts.run_query(self.language_id, tree.tree, self._query)
        # Group: collect 'def' nodes and their nearest 'name'.
        defs: list[object] = []
        names: dict[int, str] = {}
        for node, cap in captures:
            if cap == "def":
                defs.append(node)
            elif cap == "name":
                names[node.start_byte] = node.text.decode("utf-8", errors="replace")

        out: list[Symbol] = []
        src = tree.source
        for d in defs:
            qn: str | None = None
            for off, text in names.items():
                if d.start_byte <= off <= d.end_byte:
                    qn = text
                    break
            if qn is None:
                continue
            kind = self._kinds.get(d.type, "function")
            out.append(
                Symbol(
                    qualified_name=qn,
                    kind=kind,  # type: ignore[arg-type]
                    file=tree.file,
                    byte_start=d.start_byte,
                    byte_end=d.end_byte,
                    line_start=d.start_point[0] + 1,
                    line_end=d.end_point[0] + 1,
                    signature=src[d.start_byte : min(d.end_byte, d.start_byte + 200)]
                    .decode("utf-8", errors="replace")
                    .split("\n")[0],
                )
            )
        return out

    def doc_comment_style(self, sym: Symbol) -> DocStyle:
        return DOC_STYLES[self.language_id]

    def splice_doc(self, src: bytes, sym: Symbol, doc: str) -> bytes:
        style = self.doc_comment_style(sym)
        line_start = src.rfind(b"\n", 0, sym.byte_start) + 1
        indent = src[line_start : sym.byte_start].decode("utf-8", errors="replace")
        if not indent.isspace() and indent != "":
            indent = ""

        if style.delim_open or style.delim_close:
            lines = [indent + style.delim_open]
            for line in doc.splitlines() or [""]:
                lines.append(indent + style.line_prefix + line)
            lines.append(indent + style.delim_close)
        else:
            lines = [indent + style.line_prefix + line for line in (doc.splitlines() or [""])]

        block = ("\n".join(lines) + "\n" + indent).encode("utf-8")
        return src[:line_start] + block + src[line_start:]

    def local_references(self, tree: ParseResult) -> list[Ref]:
        return []  # TODO: lexical identifier refs via tree-sitter query

    def semantic_references(self, repo_root: Path) -> list[Ref] | None:
        return None

    def build_context(self, repo_root: Path) -> BuildContext | None:
        return None
