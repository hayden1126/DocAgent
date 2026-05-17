"""Tests for the deterministic Markdown chunks of ``api_reference``.

The chunks are pure functions — they convert a list of ``ModuleSymbol`` rows
plus sibling/parent context into Markdown. Pinning their format here means
the LLM-written sections can change without dragging the deterministic
infrastructure with them.
"""

from __future__ import annotations

from pathlib import Path

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


# ---------------------------------------------------------------------------
# Phase 7 render extensions
# ---------------------------------------------------------------------------


def test_python_output_unchanged_when_kwargs_omitted() -> None:
    """Pre-Phase-7 callers (no export_edges, no existing_docs) must still
    produce byte-identical output."""
    out_a = public_surface_table(
        "pkg.mod", (_sym("pkg.mod.foo", "function", "def foo(x: int) -> int"),)
    )
    out_b = public_surface_table(
        "pkg.mod",
        (_sym("pkg.mod.foo", "function", "def foo(x: int) -> int"),),
        export_edges=None,
        existing_docs=None,
    )
    assert out_a == out_b
    # No "Exported as" column should appear in either rendering.
    assert "Exported as" not in out_a


def test_exported_as_column_aliased() -> None:
    """Aliased re-export renders as ``Bar (from other.Foo)`` (RESEARCH.md Q1)."""
    from docagent.adapters.typescript import ExportEntry

    edges = {
        "Bar": ExportEntry(
            name="Bar", kind="re_export", source_module="./other", alias_of="Foo"
        )
    }
    out = public_surface_table(
        "pkg",
        (_sym("pkg.Bar", "function", "function Bar()"),),
        export_edges=edges,
    )
    assert "Exported as" in out
    assert "Bar (from other.Foo)" in out


def test_exported_as_column_re_export_kind_when_module_symbol_kind_matches() -> None:
    """When the ModuleSymbol itself has kind='re_export' and the signature
    encodes the aliased-form (per RESEARCH.md Q1 locked row shape), the
    full row reads naturally."""
    from docagent.adapters.typescript import ExportEntry

    edges = {
        "Bar": ExportEntry(
            name="Bar", kind="re_export", source_module="./other", alias_of="Foo"
        )
    }
    out = public_surface_table(
        "pkg",
        (_sym("pkg.Bar", kind="re_export", sig="exported-as Bar (from other.Foo)"),),
        export_edges=edges,
    )
    assert "| `Bar` | re_export | `exported-as Bar (from other.Foo)` | Bar (from other.Foo) |" in out


def test_exported_as_named_re_export_no_alias() -> None:
    from docagent.adapters.typescript import ExportEntry

    edges = {
        "Bar": ExportEntry(
            name="Bar", kind="re_export", source_module="./other", alias_of=None
        )
    }
    out = public_surface_table(
        "pkg",
        (_sym("pkg.Bar", "function", "function Bar()"),),
        export_edges=edges,
    )
    assert "Bar (from other)" in out
    assert "Bar (from other.Foo)" not in out


def test_exported_as_export_star_renders() -> None:
    from docagent.adapters.typescript import ExportEntry

    edges = [
        ExportEntry(name="*", kind="re_export", source_module="./other", alias_of=None)
    ]
    out = public_surface_table(
        "pkg", (_sym("pkg.dummy", "function", "function dummy()"),), export_edges=edges
    )
    assert "Exported as" in out


def test_exported_as_originals_render_em_dash() -> None:
    from docagent.adapters.typescript import ExportEntry

    edges = [
        ExportEntry(name="foo", kind="original", source_module=None, alias_of=None)
    ]
    out = public_surface_table(
        "pkg", (_sym("pkg.foo", "function", "function foo()"),), export_edges=edges
    )
    assert "—" in out


def test_existing_doc_appended_to_signature() -> None:
    out = public_surface_table(
        "pkg.mod",
        (_sym("pkg.mod.foo", "function", "function foo()"),),
        existing_docs={"pkg.mod.foo": "Brief description here."},
    )
    assert "Brief description here." in out
    assert " — Brief description here." in out


def test_existing_doc_brief_with_at_returns_preserved() -> None:
    """The brief + @returns body is what Plan 07-01 stores in existing_doc;
    the renderer surfaces the brief (first line) into the Signature column."""
    multiline = (
        "Greet the user with their name.\n\n@returns A formatted greeting string."
    )
    out = public_surface_table(
        "pkg.mod",
        (_sym("pkg.mod.greet", "function", "function greet(name)"),),
        existing_docs={"pkg.mod.greet": multiline},
    )
    assert "Greet the user with their name." in out


def test_existing_doc_truncates_long_brief() -> None:
    long_brief = "x" * 200
    out = public_surface_table(
        "pkg.mod",
        (_sym("pkg.mod.foo", "function", "function foo()"),),
        existing_docs={"pkg.mod.foo": long_brief},
    )
    assert "…" in out


def test_existing_doc_falls_back_to_module_symbol_field() -> None:
    """When the existing_docs map doesn't have a key for a symbol, the
    renderer falls back to ``ModuleSymbol.existing_doc`` for the brief."""
    from docagent.artifacts._module_discovery import ModuleSymbol

    sym = ModuleSymbol(
        qualified_name="pkg.mod.foo",
        kind="function",
        signature="function foo()",
        line_start=1,
        line_end=1,
        existing_doc="Inline brief.",
    )
    # Non-empty existing_docs map flips has_docs on, but its keys don't match
    # the symbol; the renderer must read existing_doc from the field instead.
    out = public_surface_table(
        "pkg.mod", (sym,), existing_docs={"unrelated_key": "noise"}
    )
    assert "Inline brief." in out


def test_prompt_version_bumped_to_two() -> None:
    from docagent.prompts.api_reference import PROMPT_VERSION

    assert PROMPT_VERSION == "2"


def test_prompt_version_comment_present() -> None:
    """The grep guard locks the comment on the line immediately above the
    constant assignment. Keep both in lock-step or the verify command
    fails."""
    from pathlib import Path

    text = Path("docagent/prompts/api_reference.py").read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith('PROMPT_VERSION = "2"'):
            assert i > 0, "PROMPT_VERSION at file start; missing comment"
            assert "Phase 7: bumped 1" in lines[i - 1], (
                "line above PROMPT_VERSION should contain 'Phase 7: bumped 1', "
                f"got {lines[i - 1]!r}"
            )
            return
    raise AssertionError('PROMPT_VERSION = "2" not found in file')


# ---------------------------------------------------------------------------
# Combined-cap merge correctness (RESEARCH.md Pitfall 5)
# ---------------------------------------------------------------------------


def test_max_modules_caps_combined(tmp_path: Path) -> None:
    """Per RESEARCH.md Pitfall 5: when both languages contribute modules,
    the cap MUST apply to the merged, sorted-by-dotted-name list, not each
    language independently. This test seeds Python rows and exercises the
    merge → sort → cap path inside ``plan()``."""
    from docagent.artifacts.api_reference import ApiReferenceArtifact
    from docagent.artifacts.registry import GenerationContext
    from docagent.index.store import open_store

    store = open_store(tmp_path)
    try:
        py_files = {
            "alpha.py": ["a_func"],
            "gamma.py": ["g_func"],
            "mu.py": ["m_func"],
            "zeta.py": ["z_func"],
        }
        for file, names in py_files.items():
            rows = [
                (
                    name,
                    "function",
                    file,
                    0,
                    0,
                    1,
                    1,
                    f"def {name}()",
                    None,
                    "python",
                    "h",
                )
                for name in names
            ]
            store.replace_symbols_for_file(file, rows)
            store.upsert_file_hash(file, "h", "python", "2026-01-01T00:00:00Z")

        class _StubBackend:
            model = None

        art = ApiReferenceArtifact()
        ctx = GenerationContext(
            repo_root=tmp_path,
            store=store,
            backend=_StubBackend(),
            config={"max_modules": 2},
        )
        tasks = art.plan(ctx)
        assert len(tasks) == 2
        # Alphabetically first two: alpha, gamma.
        dotted = sorted(str(t.payload["dotted_name"]) for t in tasks)
        assert dotted == ["alpha", "gamma"]
        # Every task carries a language field (Phase 7).
        assert all(
            t.payload.get("language") in ("python", "typescript") for t in tasks
        )
    finally:
        store.close()


def test_module_symbol_accepts_existing_doc_kwarg() -> None:
    """``ModuleSymbol.existing_doc`` is optional and defaults to None — the
    addition is non-breaking for pre-Phase-7 callers."""
    from docagent.artifacts._module_discovery import ModuleSymbol

    legacy = ModuleSymbol(
        qualified_name="x", kind="function", signature="", line_start=1, line_end=1
    )
    assert legacy.existing_doc is None

    enriched = ModuleSymbol(
        qualified_name="x",
        kind="function",
        signature="",
        line_start=1,
        line_end=1,
        existing_doc="Brief.",
    )
    assert enriched.existing_doc == "Brief."
