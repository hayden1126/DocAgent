"""LanguageAdapter protocol and shared types.

Per-language adapters provide parsing, symbol extraction, doc-comment styling,
in-place doc splicing, and references (lexical always; semantic when a
deepener is configured).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

SymbolKind = Literal[
    "module", "class", "function", "method", "const", "type_alias", "enum", "trait", "interface"
]

Placement = Literal["inside", "above"]


@dataclass(frozen=True, slots=True)
class DocStyle:
    """How a per-language adapter wants doc comments rendered."""

    delim_open: str
    delim_close: str
    line_prefix: str = ""
    placement: Placement = "inside"
    indent: str = "    "


@dataclass(frozen=True, slots=True)
class Symbol:
    qualified_name: str
    kind: SymbolKind
    file: Path
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    signature: str = ""
    existing_doc: str | None = None
    existing_doc_byte_range: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class Ref:
    """A reference between symbols.

    `kind` is `semantic` when produced by a deepener (libcst+Jedi, LSP, native
    tool) and `lexical` when produced by tree-sitter alone.
    """

    src: str
    dst: str
    kind: Literal["semantic", "lexical"]


@dataclass(frozen=True, slots=True)
class ParseResult:
    file: Path
    tree: object
    source: bytes
    has_errors: bool = False
    error_ranges: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class BuildContext:
    """What deepeners need to do their work."""

    compile_commands: Path | None = None
    cargo_toml: Path | None = None
    go_mod: Path | None = None
    tsconfig: Path | None = None
    extras: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class LanguageAdapter(Protocol):
    language_id: str
    file_extensions: tuple[str, ...]

    def parse(self, path: Path, src: bytes) -> ParseResult: ...

    def extract_symbols(self, tree: ParseResult) -> list[Symbol]: ...

    def doc_comment_style(self, sym: Symbol) -> DocStyle: ...

    def splice_doc(self, src: bytes, sym: Symbol, doc: str) -> bytes:
        """Insert or replace the doc comment for `sym`. Format-preserving."""
        ...

    def local_references(self, tree: ParseResult) -> list[Ref]:
        """Lexical refs from tree-sitter. Always available."""
        ...

    def semantic_references(self, repo_root: Path) -> list[Ref] | None:
        """Semantic refs via a deepener. None when no deepener is configured."""
        ...

    def build_context(self, repo_root: Path) -> BuildContext | None: ...
