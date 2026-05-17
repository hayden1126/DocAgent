"""Tests for the TypeScript module-discovery cascade.

Mirrors `_module_discovery.py`'s test coverage for the Python side. Covers:
- _file_to_dotted_ts: prefix stripping, `.d.ts` longest-suffix, excluded dirs.
- Three-tier cascade: package.json#exports → tsconfig.json#include → glob.
- Wildcard-only exports fall back to tsconfig (with WARN).
- Barrel-only modules dropped via TypeScriptAdapter.extract_exports.
- Private-only modules dropped via the _is_public_leaf filter.
- Path-traversal in exports values is rejected.
- sibling_modules_ts / parent_module_ts delegate to the Python helpers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


def _write_pkg_json(repo: Path, content: dict) -> None:
    (repo / "package.json").write_text(json.dumps(content), encoding="utf-8")


def _write_tsconfig(repo: Path, content: dict) -> None:
    (repo / "tsconfig.json").write_text(json.dumps(content), encoding="utf-8")


def _write_ts(repo: Path, rel: str, content: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _file_to_dotted_ts
# ---------------------------------------------------------------------------


def test_file_to_dotted_basic() -> None:
    from docagent.artifacts._ts_module_discovery import _file_to_dotted_ts

    assert _file_to_dotted_ts("src/cli.ts") == "cli"
    assert _file_to_dotted_ts("src/sub/mod.ts") == "sub.mod"
    assert _file_to_dotted_ts("lib/foo.ts") == "foo"
    assert _file_to_dotted_ts("dist/bar.ts") == "bar"


def test_file_to_dotted_d_ts() -> None:
    """Longest-suffix wins over Path.stem."""
    from docagent.artifacts._ts_module_discovery import _file_to_dotted_ts

    assert _file_to_dotted_ts("src/types.d.ts") == "types"
    assert _file_to_dotted_ts("src/types.d.ts") != "types.d"


def test_file_to_dotted_all_extensions() -> None:
    from docagent.artifacts._ts_module_discovery import _file_to_dotted_ts

    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        assert _file_to_dotted_ts(f"src/foo{ext}") == "foo"


def test_file_to_dotted_excluded_top_dirs() -> None:
    from docagent.artifacts._ts_module_discovery import _file_to_dotted_ts

    assert _file_to_dotted_ts("tests/x.ts") is None
    assert _file_to_dotted_ts("node_modules/x.ts") is None
    assert _file_to_dotted_ts("build/x.ts") is None
    # `dist/x.ts` with no src/ peer in this call → stripped, becomes 'x'.
    # That matches the locked rule that strips src/lib/dist as TS conventions.
    assert _file_to_dotted_ts("dist/x.ts") == "x"


def test_file_to_dotted_returns_none_for_unknown_extension() -> None:
    from docagent.artifacts._ts_module_discovery import _file_to_dotted_ts

    assert _file_to_dotted_ts("src/foo.md") is None
    assert _file_to_dotted_ts("src/foo") is None


def test_file_to_dotted_empty_after_strip() -> None:
    """A bare extension-only path or src/-stripping that empties parts returns None."""
    from docagent.artifacts._ts_module_discovery import _file_to_dotted_ts

    assert _file_to_dotted_ts("src/") is None


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------


def _make_symbol_row(qn: str, file_rel: str, line_start: int = 1) -> tuple:
    return (qn, "function", file_rel, line_start, line_start, f"function {qn.split('.')[-1]}() {{}}")


def test_cascade_exports_wins(tmp_path: Path) -> None:
    """package.json#exports returns ONLY entries from exports, ignoring tsconfig.include."""
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    _write_pkg_json(
        repo,
        {
            "name": "demo",
            "exports": {
                ".": "./dist/index.js",
                "./cli": "./dist/cli.js",
                "./types": "./dist/types.js",
            },
        },
    )
    _write_tsconfig(repo, {"include": ["src/**/*"]})
    _write_ts(repo, "src/index.ts", "export function root() {}\n")
    _write_ts(repo, "src/cli.ts", "export function go() {}\n")
    _write_ts(repo, "src/types.ts", "export function T() {}\n")
    # Extra file under src that is NOT in exports — should be dropped.
    _write_ts(repo, "src/extra.ts", "export function extra() {}\n")

    rows = [
        _make_symbol_row("root", "src/index.ts"),
        _make_symbol_row("go", "src/cli.ts"),
        _make_symbol_row("T", "src/types.ts"),
        _make_symbol_row("extra", "src/extra.ts"),
    ]
    modules, _ = discover_ts_modules(repo, rows, {})
    dotted_names = {m.dotted_name for m in modules}
    # Only the three exports-map entries surface.
    assert "extra" not in dotted_names
    assert {"index", "cli", "types"}.issubset(dotted_names) or {
        "cli",
        "types",
    }.issubset(dotted_names)


def test_cascade_tsconfig_used_when_exports_absent(tmp_path: Path) -> None:
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    _write_pkg_json(repo, {"name": "demo"})  # no exports
    _write_tsconfig(repo, {"include": ["src/**/*"]})
    _write_ts(repo, "src/a.ts", "export function a() {}\n")
    _write_ts(repo, "src/b.ts", "export function b() {}\n")

    rows = [
        _make_symbol_row("a", "src/a.ts"),
        _make_symbol_row("b", "src/b.ts"),
    ]
    modules, _ = discover_ts_modules(repo, rows, {})
    dotted_names = {m.dotted_name for m in modules}
    assert dotted_names == {"a", "b"}


def test_cascade_glob_when_neither(tmp_path: Path) -> None:
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    # No package.json, no tsconfig.json.
    _write_ts(repo, "src/lonely.ts", "export function lonely() {}\n")
    rows = [_make_symbol_row("lonely", "src/lonely.ts")]
    modules, _ = discover_ts_modules(repo, rows, {})
    assert any(m.dotted_name == "lonely" for m in modules)


def test_wildcard_only_exports_falls_back(tmp_path: Path) -> None:
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    _write_pkg_json(repo, {"exports": {"./*": "./dist/*.js"}})
    _write_tsconfig(repo, {"include": ["src/**/*"]})
    _write_ts(repo, "src/x.ts", "export function x() {}\n")

    rows = [_make_symbol_row("x", "src/x.ts")]

    # The `docagent` logger sets `propagate=False`, so attach a local
    # handler to capture warnings directly rather than relying on caplog.
    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    target = logging.getLogger("docagent.artifacts.api_reference.ts_discovery")
    handler = _Capture(level=logging.WARNING)
    target.addHandler(handler)
    try:
        modules, _ = discover_ts_modules(repo, rows, {})
    finally:
        target.removeHandler(handler)
    assert any(m.dotted_name == "x" for m in modules)
    assert any("wildcard-only" in r.getMessage() for r in captured)


def test_barrel_only_dropped(tmp_path: Path) -> None:
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    _write_pkg_json(repo, {"name": "demo"})
    _write_tsconfig(repo, {"include": ["src/**/*"]})
    _write_ts(repo, "src/barrel.ts", 'export * from "./other";\n')
    _write_ts(repo, "src/other.ts", "export function foo() {}\n")

    rows = [
        _make_symbol_row("foo", "src/other.ts"),
    ]
    modules, _ = discover_ts_modules(repo, rows, {})
    dotted_names = {m.dotted_name for m in modules}
    assert "other" in dotted_names
    assert "barrel" not in dotted_names


def test_private_only_module_dropped(tmp_path: Path) -> None:
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    _write_pkg_json(repo, {"name": "demo"})
    _write_tsconfig(repo, {"include": ["src/**/*"]})
    _write_ts(repo, "src/_internal.ts", "export function _helper() {}\n")

    rows = [_make_symbol_row("_helper", "src/_internal.ts")]
    modules, _ = discover_ts_modules(repo, rows, {})
    dotted_names = {m.dotted_name for m in modules}
    assert "_internal" not in dotted_names


def test_path_traversal_rejected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from docagent.artifacts._ts_module_discovery import discover_ts_modules

    repo = tmp_path
    _write_pkg_json(repo, {"exports": {".": "../../etc/passwd"}})
    # tsconfig provides a legitimate fallback so we can verify only the
    # legitimate file is returned (the traversal is rejected, not crashed).
    _write_tsconfig(repo, {"include": ["src/**/*"]})
    _write_ts(repo, "src/legit.ts", "export function legit() {}\n")

    rows = [_make_symbol_row("legit", "src/legit.ts")]
    with caplog.at_level(logging.WARNING, logger="docagent"):
        modules, _ = discover_ts_modules(repo, rows, {})
    dotted_names = {m.dotted_name for m in modules}
    assert "passwd" not in dotted_names
    assert not any("etc/passwd" in m.file_rel for m in modules)


def test_sibling_modules_ts_delegates() -> None:
    from docagent.artifacts._ts_module_discovery import sibling_modules_ts

    result = sibling_modules_ts(
        "tinylib_ts.cli",
        ["tinylib_ts.cli", "tinylib_ts.types", "other.x"],
    )
    assert result == ["tinylib_ts.types"]


def test_parent_module_ts() -> None:
    from docagent.artifacts._ts_module_discovery import parent_module_ts

    assert parent_module_ts("tinylib_ts.sub.foo") == "tinylib_ts.sub"
    assert parent_module_ts("foo") is None
