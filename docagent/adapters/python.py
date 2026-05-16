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


class _SymbolCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, file: Path, source: bytes) -> None:
        super().__init__()
        self.file = file
        self.source = source
        self.symbols: list[Symbol] = []
        self._scope: list[str] = []
        self._scope_is_class: list[bool] = []

    def _record(
        self,
        node: cst.CSTNode,
        name: str,
        kind: str,
    ) -> None:
        pos = self.get_metadata(PositionProvider, node)
        qn = ".".join(self._scope + [name])
        existing_doc = _extract_docstring(node)
        self.symbols.append(
            Symbol(
                qualified_name=qn,
                kind=kind,  # type: ignore[arg-type]
                file=self.file,
                byte_start=0,
                byte_end=0,
                line_start=pos.start.line,
                line_end=pos.end.line,
                signature=name,
                existing_doc=existing_doc,
            )
        )

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        in_class = bool(self._scope_is_class) and self._scope_is_class[-1]
        kind = "method" if in_class else "function"
        self._record(node, node.name.value, kind)
        self._scope.append(node.name.value)
        self._scope_is_class.append(False)

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self._scope.pop()
        self._scope_is_class.pop()

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._record(node, node.name.value, "class")
        self._scope.append(node.name.value)
        self._scope_is_class.append(True)

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._scope.pop()
        self._scope_is_class.pop()


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
