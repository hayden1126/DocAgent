"""Python adapter — the v1 deepener.

Uses libcst for format-preserving docstring extraction and splicing.
Jedi-backed semantic references are scaffolded but defer the heavy wiring to
a follow-up patch; v1 returns None until enabled, so callers fall through to
lexical references.
"""

from __future__ import annotations

from pathlib import Path

import libcst as cst
from libcst.metadata import PositionProvider

from docagent.adapters.base import (
    BuildContext,
    DocStyle,
    LanguageAdapter,
    ParseResult,
    Ref,
    Symbol,
)


PYTHON_DOC_STYLE = DocStyle(
    delim_open='"""',
    delim_close='"""',
    line_prefix="",
    placement="inside",
    indent="    ",
)


class _ByteOffsetTable:
    """Map libcst's (1-based line, 0-based code-point column) to byte offsets.

    libcst's :class:`PositionProvider` reports columns in code points, not
    bytes. For ASCII sources that's a non-issue, but a single non-ASCII
    character in a docstring (or a UTF-8 BOM, or smart quotes) would slide
    every downstream byte range by some amount. Pre-compute a per-line table
    once and convert per lookup.
    """

    __slots__ = ("_line_byte_starts", "_line_texts", "_eof_byte")

    def __init__(self, source: bytes) -> None:
        text = source.decode("utf-8")
        line_texts = text.split("\n")
        starts = [0, 0]  # 1-based; element 0 unused
        cursor = 0
        for line in line_texts:
            cursor += len(line.encode("utf-8")) + 1  # +1 for the newline
            starts.append(cursor)
        self._line_byte_starts = starts
        self._line_texts = line_texts
        self._eof_byte = len(source)

    def at(self, line: int, col: int) -> int:
        if line < 1 or line > len(self._line_texts):
            return self._eof_byte
        line_start = self._line_byte_starts[line]
        line_text = self._line_texts[line - 1]
        clipped_col = max(0, min(col, len(line_text)))
        return line_start + len(line_text[:clipped_col].encode("utf-8"))


class _SymbolCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, file: Path, source: bytes) -> None:
        super().__init__()
        self.file = file
        self.source = source
        self._offsets = _ByteOffsetTable(source)
        self.symbols: list[Symbol] = []
        self._scope: list[str] = []
        self._scope_is_class: list[bool] = []

    def _record(
        self,
        node: cst.CSTNode,
        name: str,
        kind: str,
        signature: str,
    ) -> None:
        pos = self.get_metadata(PositionProvider, node)
        qn = ".".join(self._scope + [name])
        existing_doc = _extract_docstring(node)
        byte_start = self._offsets.at(pos.start.line, pos.start.column)
        byte_end = self._offsets.at(pos.end.line, pos.end.column)
        self.symbols.append(
            Symbol(
                qualified_name=qn,
                kind=kind,  # type: ignore[arg-type]
                file=self.file,
                byte_start=byte_start,
                byte_end=byte_end,
                line_start=pos.start.line,
                line_end=pos.end.line,
                signature=signature,
                existing_doc=existing_doc,
            )
        )

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        in_class = bool(self._scope_is_class) and self._scope_is_class[-1]
        kind = "method" if in_class else "function"
        self._record(node, node.name.value, kind, _function_signature(node))
        self._scope.append(node.name.value)
        self._scope_is_class.append(False)

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self._scope.pop()
        self._scope_is_class.pop()

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._record(node, node.name.value, "class", _class_signature(node))
        self._scope.append(node.name.value)
        self._scope_is_class.append(True)

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._scope.pop()
        self._scope_is_class.pop()


_RENDER_MODULE = cst.Module(body=[])


def _function_signature(node: cst.FunctionDef) -> str:
    """Render ``name(params) -> return_annotation``.

    Whitespace and trailing newlines from libcst are stripped. Async
    functions are prefixed with ``async ``. Functions without a return
    annotation render as ``name(params)``.
    """
    name = node.name.value
    params_src = _RENDER_MODULE.code_for_node(node.params).strip()
    sig = f"{name}({params_src})"
    if node.returns is not None:
        ann_src = _RENDER_MODULE.code_for_node(node.returns.annotation).strip()
        sig = f"{sig} -> {ann_src}"
    if getattr(node, "asynchronous", None) is not None:
        sig = "async " + sig
    return _collapse_ws(sig)


def _class_signature(node: cst.ClassDef) -> str:
    """Render ``Name(Base1, Base2, ...)`` or bare ``Name``."""
    name = node.name.value
    if not node.bases:
        return name
    base_parts = [
        _RENDER_MODULE.code_for_node(arg.value).strip() for arg in node.bases
    ]
    return _collapse_ws(f"{name}({', '.join(base_parts)})")


def _collapse_ws(text: str) -> str:
    """Collapse internal whitespace to single spaces; libcst preserves
    source newlines inside multi-line parameter lists, but a table cell
    needs a single line."""
    return " ".join(text.split())


def _extract_docstring(node: cst.CSTNode) -> str | None:
    body = getattr(node, "body", None)
    if body is None:
        return None
    inner = getattr(body, "body", None)
    if not inner:
        return None
    first = inner[0]
    if isinstance(first, cst.SimpleStatementLine) and first.body:
        stmt = first.body[0]
        if isinstance(stmt, cst.Expr) and isinstance(stmt.value, cst.SimpleString):
            return stmt.value.evaluated_value
    return None


class _DocstringSplicer(cst.CSTTransformer):
    def __init__(self, target_qn: str, doc: str) -> None:
        super().__init__()
        self.target_qn = target_qn
        self.doc = doc
        self._scope: list[str] = []
        self.applied = False

    def _matches(self, name: str) -> bool:
        return ".".join(self._scope + [name]) == self.target_qn

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self._scope.append(node.name.value)
        return True

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        name = self._scope.pop()
        if ".".join(self._scope + [name]) == self.target_qn:
            return updated_node.with_changes(body=_inject_docstring(updated_node.body, self.doc))
        return updated_node

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        self._scope.append(node.name.value)
        return True

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        name = self._scope.pop()
        if ".".join(self._scope + [name]) == self.target_qn:
            return updated_node.with_changes(body=_inject_docstring(updated_node.body, self.doc))
        return updated_node


def _inject_docstring(body: cst.IndentedBlock, doc: str) -> cst.IndentedBlock:
    doc_node = cst.SimpleStatementLine(
        body=[cst.Expr(value=cst.SimpleString(value=f'"""{doc}"""'))]
    )
    existing = list(body.body)
    if existing:
        first = existing[0]
        if (
            isinstance(first, cst.SimpleStatementLine)
            and first.body
            and isinstance(first.body[0], cst.Expr)
            and isinstance(first.body[0].value, cst.SimpleString)
        ):
            existing[0] = doc_node
            return body.with_changes(body=existing)
    return body.with_changes(body=[doc_node, *existing])


class PythonAdapter(LanguageAdapter):
    language_id = "python"
    file_extensions = (".py", ".pyi")

    def parse(self, path: Path, src: bytes) -> ParseResult:
        module = cst.parse_module(src.decode("utf-8"))
        return ParseResult(file=path, tree=module, source=src, has_errors=False)

    def extract_symbols(self, tree: ParseResult) -> list[Symbol]:
        wrapper = cst.MetadataWrapper(tree.tree)  # type: ignore[arg-type]
        collector = _SymbolCollector(tree.file, tree.source)
        wrapper.visit(collector)
        return collector.symbols

    def doc_comment_style(self, sym: Symbol) -> DocStyle:
        return PYTHON_DOC_STYLE

    def splice_doc(self, src: bytes, sym: Symbol, doc: str) -> bytes:
        module = cst.parse_module(src.decode("utf-8"))
        transformer = _DocstringSplicer(sym.qualified_name, doc)
        new_module = module.visit(transformer)
        return new_module.code.encode("utf-8")

    def local_references(self, tree: ParseResult) -> list[Ref]:
        return []  # TODO: walk imports/names via libcst

    def semantic_references(self, repo_root: Path) -> list[Ref] | None:
        return None  # TODO: wire Jedi Project resolution

    def build_context(self, repo_root: Path) -> BuildContext | None:
        return None
