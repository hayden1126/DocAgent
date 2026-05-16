"""Shared tree-sitter grammar loader.

Grammars are lazy-loaded on first use; each language ships as its own pip
package (e.g. `tree-sitter-python`). We exec a small import per language so
unused grammars don't pay startup cost.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

try:
    from tree_sitter import Language, Parser
except ImportError as exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "tree-sitter is required. Install with `pip install tree-sitter`."
    ) from exc


GRAMMAR_PACKAGES: dict[str, str] = {
    "python": "tree_sitter_python",
    "rust": "tree_sitter_rust",
    "go": "tree_sitter_go",
    "typescript": "tree_sitter_typescript",
    "tsx": "tree_sitter_typescript",
    "javascript": "tree_sitter_typescript",  # ts grammar handles JS adequately
    "java": "tree_sitter_java",
    "cpp": "tree_sitter_cpp",
}


@dataclass(frozen=True, slots=True)
class LoadedGrammar:
    language_id: str
    language: Any  # tree_sitter.Language
    parser: Any  # tree_sitter.Parser


@lru_cache(maxsize=None)
def load(language_id: str) -> LoadedGrammar:
    pkg_name = GRAMMAR_PACKAGES.get(language_id)
    if pkg_name is None:
        raise KeyError(f"No tree-sitter grammar registered for language: {language_id}")

    module = importlib.import_module(pkg_name)

    if language_id in ("typescript", "tsx", "javascript"):
        accessor = "language_tsx" if language_id == "tsx" else "language_typescript"
        if hasattr(module, accessor):
            lang_capsule = getattr(module, accessor)()
        else:
            lang_capsule = module.language()
    else:
        lang_capsule = module.language()

    language = Language(lang_capsule)
    parser = Parser(language)
    return LoadedGrammar(language_id=language_id, language=language, parser=parser)


def parse_source(language_id: str, src: bytes) -> Any:
    grammar = load(language_id)
    return grammar.parser.parse(src)


def run_query(language_id: str, tree: Any, query_source: str) -> list[tuple[Any, str]]:
    grammar = load(language_id)
    query = grammar.language.query(query_source)
    captures = query.captures(tree.root_node)
    out: list[tuple[Any, str]] = []
    if isinstance(captures, dict):
        for name, nodes in captures.items():
            for node in nodes:
                out.append((node, name))
    else:
        for node, name in captures:
            out.append((node, name))
    return out
