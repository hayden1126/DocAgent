"""Tests for ``PythonAdapter``'s real-signature extraction (item 12).

Before v1.0.3 the adapter stored ``signature=name``, which made the
``api_reference`` ``Signature`` column useless (`| parse | function | parse |`).
The adapter now renders real ``name(params) -> returns`` and ``class
Name(Bases)`` forms via libcst.
"""

from __future__ import annotations

from pathlib import Path

from docagent.adapters.python import PythonAdapter


def _signatures(src: str) -> dict[str, str]:
    adapter = PythonAdapter()
    parsed = adapter.parse(Path("x.py"), src.encode("utf-8"))
    return {s.qualified_name: s.signature for s in adapter.extract_symbols(parsed)}


def test_function_signature_includes_params_and_return() -> None:
    sigs = _signatures("def greet(name: str) -> str:\n    return name\n")
    assert sigs["greet"] == "greet(name: str) -> str"


def test_function_without_return_annotation_renders_bare_params() -> None:
    sigs = _signatures("def greet(name):\n    return name\n")
    assert sigs["greet"] == "greet(name)"


def test_method_signature_qualifies_with_class_scope() -> None:
    src = (
        "class Greeter:\n"
        "    def greet(self, name: str) -> str:\n"
        "        return name\n"
    )
    sigs = _signatures(src)
    assert sigs["Greeter"] == "Greeter"
    assert sigs["Greeter.greet"] == "greet(self, name: str) -> str"


def test_class_with_bases_renders_parenthesised() -> None:
    sigs = _signatures("class Child(Base, Mixin):\n    pass\n")
    assert sigs["Child"] == "Child(Base, Mixin)"


def test_async_function_prefixed() -> None:
    sigs = _signatures("async def fetch(url: str) -> bytes:\n    return b''\n")
    assert sigs["fetch"] == "async fetch(url: str) -> bytes"


def test_multiline_params_collapse_to_single_line() -> None:
    src = (
        "def many(\n"
        "    a: int,\n"
        "    b: int,\n"
        ") -> int:\n"
        "    return a + b\n"
    )
    sigs = _signatures(src)
    assert sigs["many"] == "many(a: int, b: int,) -> int"
