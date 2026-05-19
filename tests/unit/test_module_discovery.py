"""Tests for module discovery from the symbol index.

Pins the rules: dotted-name derivation (with ``src/`` peel and ``__init__``
collapse), exclusion of test/build dirs, public-symbol filter, and the
sibling/parent-module helpers used by the see-also renderer.
"""

from __future__ import annotations

from docagent.artifacts._module_discovery import (
    DiscoveredModule,
    discover_python_modules,
    parent_module,
    sibling_modules,
)


def _row(qn: str, file: str, line: int = 1) -> tuple:
    return (qn, "function", file, line, line, qn)


def test_simple_module_with_public_function() -> None:
    mods = discover_python_modules([_row("greet", "tinylib/cli.py")])
    assert len(mods) == 1
    assert mods[0].dotted_name == "tinylib.cli"
    assert mods[0].file_rel == "tinylib/cli.py"
    assert mods[0].public_symbols[0].qualified_name == "greet"


def test_private_function_skipped() -> None:
    mods = discover_python_modules(
        [_row("greet", "tinylib/cli.py"), _row("_helper", "tinylib/cli.py")]
    )
    qns = [s.qualified_name for s in mods[0].public_symbols]
    assert "greet" in qns
    assert "_helper" not in qns


def test_module_with_all_private_is_dropped() -> None:
    mods = discover_python_modules([_row("_only_helper", "tinylib/internal.py")])
    assert mods == []


def test_dunder_method_skipped() -> None:
    mods = discover_python_modules(
        [_row("Greeter.greet", "tinylib/cli.py"), _row("Greeter.__init__", "tinylib/cli.py")]
    )
    qns = [s.qualified_name for s in mods[0].public_symbols]
    assert "Greeter.greet" in qns
    assert "Greeter.__init__" not in qns


def test_methods_of_private_class_skipped() -> None:
    """A public-named method under a private parent class is still private.

    Regression for the ``_ByteOffsetTable.at`` case shipped in
    ``docs/reference/docagent.adapters.python.md`` — public leaf, private
    parent — which leaked into the public-surface table before v1.0.3.
    """
    mods = discover_python_modules(
        [
            _row("Public.method", "tinylib/cli.py"),
            _row("_Private.public_method", "tinylib/cli.py"),
        ]
    )
    qns = [s.qualified_name for s in mods[0].public_symbols]
    assert "Public.method" in qns
    assert "_Private.public_method" not in qns


def test_init_py_collapses_to_package_name() -> None:
    mods = discover_python_modules([_row("greet", "tinylib/__init__.py")])
    assert mods[0].dotted_name == "tinylib"


def test_src_layout_strips_prefix() -> None:
    mods = discover_python_modules([_row("greet", "src/mypkg/cli.py")])
    assert mods[0].dotted_name == "mypkg.cli"


def test_src_layout_root_init() -> None:
    mods = discover_python_modules([_row("VERSION", "src/mypkg/__init__.py")])
    assert mods[0].dotted_name == "mypkg"


def test_tests_directory_excluded() -> None:
    mods = discover_python_modules([_row("test_foo", "tests/unit/test_things.py")])
    assert mods == []


def test_build_dist_directories_excluded() -> None:
    rows = [
        _row("foo", "build/lib/x.py"),
        _row("bar", "dist/x.py"),
        _row("baz", "scripts/run.py"),
        _row("real", "mypkg/x.py"),
    ]
    mods = discover_python_modules(rows)
    assert [m.dotted_name for m in mods] == ["mypkg.x"]


def test_pyi_stubs_use_module_name() -> None:
    mods = discover_python_modules([_row("greet", "tinylib/cli.pyi")])
    assert mods[0].dotted_name == "tinylib.cli"


def test_multiple_modules_sorted() -> None:
    rows = [
        _row("z", "pkg/zeta.py"),
        _row("a", "pkg/alpha.py"),
        _row("m", "pkg/__init__.py"),
    ]
    mods = discover_python_modules(rows)
    assert [m.dotted_name for m in mods] == ["pkg", "pkg.alpha", "pkg.zeta"]


def test_symbols_sorted_by_line_within_module() -> None:
    rows = [
        ("baz", "function", "pkg/x.py", 50, 51, "baz"),
        ("foo", "function", "pkg/x.py", 10, 11, "foo"),
        ("bar", "function", "pkg/x.py", 30, 31, "bar"),
    ]
    mods = discover_python_modules(rows)
    qns = [s.qualified_name for s in mods[0].public_symbols]
    assert qns == ["foo", "bar", "baz"]


def test_sibling_modules_same_package() -> None:
    all_mods = ["pkg", "pkg.a", "pkg.b", "pkg.sub.c", "other"]
    assert sibling_modules("pkg.a", all_mods) == ["pkg.b"]


def test_sibling_modules_top_level() -> None:
    all_mods = ["pkg", "other", "pkg.a"]
    assert sibling_modules("pkg", all_mods) == ["other"]


def test_parent_module() -> None:
    assert parent_module("pkg.sub.mod") == "pkg.sub"
    assert parent_module("pkg") is None


def test_returns_discovered_module_instances() -> None:
    mods = discover_python_modules([_row("greet", "tinylib/cli.py")])
    assert isinstance(mods[0], DiscoveredModule)
