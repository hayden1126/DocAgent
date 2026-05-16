"""Smoke tests for the v1 skeleton.

These exercise the load-bearing wiring: registry topo sort, SQLite migration,
Python adapter parse + symbol extraction + docstring splice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docagent.adapters.python import PythonAdapter
from docagent.artifacts.builtins import register_v1_builtins
from docagent.artifacts.registry import Registry
from docagent.ignore import IgnoreMatcher
from docagent.index.store import open_store


def test_registry_topo_order_v1():
    reg = Registry()
    register_v1_builtins(reg)
    order = [a.id for a in reg.topo_order()]
    assert order.index("readme") < order.index("agents_md")
    assert order.index("readme") < order.index("claude_md")
    assert order.index("python_docstrings") < order.index("api_reference")
    assert order.index("api_reference") < order.index("how_to_guides")
    assert order.index("readme") < order.index("how_to_guides")
    assert order.index("api_reference") < order.index("llms_txt")


def test_registry_detects_cycle():
    from dataclasses import dataclass

    @dataclass
    class _A:
        id: str
        audience: str = "human"
        depends_on: tuple[str, ...] = ()

        def plan(self, ctx):
            return []

        def generate(self, task, ctx):
            ...

        def verify(self, patch, ctx):
            ...

    reg = Registry()
    reg.register(_A(id="a", depends_on=("b",)))
    reg.register(_A(id="b", depends_on=("a",)))
    with pytest.raises(ValueError, match="Cycle"):
        reg.topo_order()


def test_sqlite_store_migration(tmp_path: Path):
    store = open_store(tmp_path)
    # idempotent on reopen
    store.close()
    store2 = open_store(tmp_path)
    cur = store2.conn.execute("SELECT version FROM schema_version")
    assert cur.fetchone()[0] == 1
    store2.close()


def test_python_adapter_extracts_symbols(tmp_path: Path):
    src = b'''
def foo(x: int) -> int:
    """existing doc"""
    return x + 1


class Bar:
    def baz(self):
        return 7
'''
    path = tmp_path / "sample.py"
    path.write_bytes(src)
    adapter = PythonAdapter()
    parsed = adapter.parse(path, src)
    syms = adapter.extract_symbols(parsed)
    qns = {s.qualified_name for s in syms}
    assert "foo" in qns
    assert "Bar" in qns
    assert "Bar.baz" in qns
    foo = next(s for s in syms if s.qualified_name == "foo")
    assert foo.existing_doc == "existing doc"


def test_python_adapter_splice_inserts_docstring(tmp_path: Path):
    src = b"def foo():\n    return 1\n"
    path = tmp_path / "f.py"
    adapter = PythonAdapter()
    parsed = adapter.parse(path, src)
    sym = next(s for s in adapter.extract_symbols(parsed) if s.qualified_name == "foo")
    new_src = adapter.splice_doc(src, sym, "Increment by one.")
    assert b'"""Increment by one."""' in new_src


def test_ignore_matcher_filters_defaults(tmp_path: Path):
    matcher = IgnoreMatcher(tmp_path)
    assert matcher.is_ignored(tmp_path / "build" / "x.py")
    assert matcher.is_ignored(tmp_path / "vendor" / "lib.py")
    assert matcher.is_ignored(tmp_path / "node_modules" / "pkg" / "index.js")
    assert not matcher.is_ignored(tmp_path / "src" / "main.py")
