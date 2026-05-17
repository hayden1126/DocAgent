"""Tests for the deterministic Markdown chunks of ``api_reference``.

The chunks are pure functions — they convert a list of ``ModuleSymbol`` rows
plus sibling/parent context into Markdown. Pinning their format here means
the LLM-written sections can change without dragging the deterministic
infrastructure with them.
"""

from __future__ import annotations

from docagent.artifacts._api_reference_render import (
    assemble_page,
    frontmatter,
    h1,
    public_surface_table,
    see_also_section,
)
from docagent.artifacts._module_discovery import ModuleSymbol


def _sym(qn: str, kind: str = "function", sig: str = "") -> ModuleSymbol:
    return ModuleSymbol(
        qualified_name=qn,
        kind=kind,
        signature=sig or qn,
        line_start=1,
        line_end=1,
    )


def test_frontmatter_has_required_keys() -> None:
    fm = frontmatter("pkg.mod")
    assert "docagent_artifact: api_reference" in fm
    assert "module: pkg.mod" in fm
    assert fm.startswith("---\n")
    assert fm.rstrip().endswith("---")


def test_h1_uses_backticks() -> None:
    assert h1("pkg.mod") == "# `pkg.mod`\n"


def test_public_surface_table_strips_module_prefix() -> None:
    """Leaf names should appear bare — ``pkg.mod.foo`` shows as ``foo``."""
    out = public_surface_table(
        "pkg.mod", (_sym("pkg.mod.foo", "function", "def foo(x: int) -> int"),)
    )
    assert "| `foo` | function | `def foo(x: int) -> int` |" in out


def test_public_surface_table_with_methods_keeps_class_prefix() -> None:
    out = public_surface_table(
        "pkg.mod",
        (
            _sym("pkg.mod.Greeter", "class", "class Greeter"),
            _sym("pkg.mod.Greeter.greet", "method", "def greet(self, name)"),
        ),
    )
    assert "`Greeter`" in out
    assert "`Greeter.greet`" in out


def test_public_surface_table_truncates_long_signatures() -> None:
    long_sig = "def foo(" + "x: int, " * 30 + ") -> int"
    out = public_surface_table("m", (_sym("m.foo", "function", long_sig),))
    assert "…" in out
    # The truncated line must still be valid Markdown (no unescaped pipes).
    assert all(line.count("|") == 4 for line in out.splitlines() if line.startswith("|"))


def test_public_surface_table_escapes_pipes_in_signatures() -> None:
    out = public_surface_table(
        "m", (_sym("m.foo", "function", "def foo(x: int | str)"),)
    )
    assert "int \\| str" in out


def test_public_surface_table_empty_module() -> None:
    out = public_surface_table("pkg.empty", ())
    assert "Public surface" in out
    assert "*(none)*" in out


def test_public_surface_dedupes_repeated_leaves() -> None:
    """Tree-sitter overload duplicates shouldn't multiply table rows."""
    out = public_surface_table(
        "m",
        (
            _sym("m.foo", "function", "def foo(a: int)"),
            _sym("m.foo", "function", "def foo(a: str)"),
        ),
    )
    assert out.count("| `foo` |") == 1


def test_see_also_includes_parent_and_siblings() -> None:
    out = see_also_section("pkg.a", ["pkg.b", "pkg.c"], "pkg")
    assert "[`pkg`](pkg.md)" in out
    assert "[`pkg.b`](pkg.b.md)" in out
    assert "[`pkg.c`](pkg.c.md)" in out
    assert "parent package" in out


def test_see_also_empty_returns_empty_string() -> None:
    """Top-level module with no siblings produces nothing."""
    assert see_also_section("solo", [], None) == ""


def test_see_also_siblings_only_no_parent() -> None:
    out = see_also_section("a", ["b"], None)
    assert "parent package" not in out
    assert "[`b`](b.md)" in out


def test_assemble_page_includes_all_sections() -> None:
    page = assemble_page(
        dotted_name="pkg.mod",
        symbols=(_sym("pkg.mod.foo", "function", "def foo()"),),
        siblings=["pkg.other"],
        parent="pkg",
        opener_md="The mod module does things. <!-- ground: pkg/mod.py:1-5 -->",
        workflows_md="```python\nfoo()\n```\n<!-- ground: pkg/mod.py:1-5 -->",
    )
    assert "docagent_artifact: api_reference" in page
    assert "# `pkg.mod`" in page
    assert "The mod module does things." in page
    assert "## Public surface" in page
    assert "## Common workflows" in page
    assert "```python" in page
    assert "## See also" in page
    assert "mkdocstrings" in page  # footer hint


def test_assemble_page_handles_empty_llm_sections() -> None:
    """If the model returns nothing useful, the page must still be valid
    Markdown rather than silently dropping a section."""
    page = assemble_page(
        dotted_name="pkg.mod",
        symbols=(_sym("pkg.mod.foo"),),
        siblings=[],
        parent=None,
        opener_md="   ",
        workflows_md="",
    )
    assert "See public surface below" in page
    assert "No worked examples" in page


def test_assemble_page_omits_see_also_when_no_neighbors() -> None:
    page = assemble_page(
        dotted_name="solo",
        symbols=(_sym("solo.x"),),
        siblings=[],
        parent=None,
        opener_md="x",
        workflows_md="y",
    )
    assert "## See also" not in page
