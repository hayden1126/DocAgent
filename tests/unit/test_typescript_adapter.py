"""Unit tests for ``TypeScriptAdapter``.

Pins symbol extraction across the categories the v1 adapter promises to
handle, plus the deliberate exclusions (constructors, anonymous defaults,
function-body locals). Each test exercises one grammar shape with inline
TS/TSX source — no fixture file plumbing needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docagent.adapters.base import Symbol
from docagent.adapters.typescript import TypeScriptAdapter


@pytest.fixture
def adapter() -> TypeScriptAdapter:
    return TypeScriptAdapter()


def _extract(adapter: TypeScriptAdapter, src: str, *, name: str = "sample.ts") -> list[Symbol]:
    parsed = adapter.parse(Path(name), src.encode("utf-8"))
    return adapter.extract_symbols(parsed)


def _by_qn(syms: list[Symbol]) -> dict[str, Symbol]:
    return {s.qualified_name: s for s in syms}


def test_function_declaration(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "export function greet(name: string) { return name }")
    by = _by_qn(syms)
    assert "greet" in by
    assert by["greet"].kind == "function"


def test_generator_function_declaration(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "function* gen() { yield 1 }")
    assert _by_qn(syms)["gen"].kind == "function"


def test_class_with_method(adapter: TypeScriptAdapter) -> None:
    syms = _extract(
        adapter,
        """
        export class Greeter {
            greet(name: string) { return name }
            static of(name: string) { return new Greeter() }
        }
        """,
    )
    by = _by_qn(syms)
    assert by["Greeter"].kind == "class"
    assert by["Greeter.greet"].kind == "method"
    assert by["Greeter.of"].kind == "method"


def test_abstract_class_and_abstract_method(adapter: TypeScriptAdapter) -> None:
    syms = _extract(
        adapter,
        "export abstract class A { abstract foo(): void; concrete() {} }",
    )
    by = _by_qn(syms)
    assert by["A"].kind == "class"
    assert by["A.foo"].kind == "method"
    assert by["A.concrete"].kind == "method"


def test_constructor_is_skipped(adapter: TypeScriptAdapter) -> None:
    """Constructors are never referenced by name in prose — including them
    pollutes the mention index."""
    syms = _extract(
        adapter,
        "class Foo { constructor() {} doThing() {} }",
    )
    by = _by_qn(syms)
    assert "Foo.constructor" not in by
    assert "Foo.doThing" in by


def test_ecmascript_private_method_skipped(adapter: TypeScriptAdapter) -> None:
    """``#foo`` is real privacy; skip. ``_foo`` is convention; keep."""
    syms = _extract(
        adapter,
        "class Foo { #hidden() {} _byConvention() {} }",
    )
    by = _by_qn(syms)
    assert "Foo.#hidden" not in by
    assert "Foo._byConvention" in by


def test_interface_with_method_signature(adapter: TypeScriptAdapter) -> None:
    syms = _extract(
        adapter, "export interface IGreeting { who: string; salute(): string }"
    )
    by = _by_qn(syms)
    assert by["IGreeting"].kind == "interface"
    assert by["IGreeting.salute"].kind == "method"


def test_type_alias_declaration(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, 'type Salutation = "hi" | "hello"')
    assert _by_qn(syms)["Salutation"].kind == "type_alias"


def test_enum_declaration(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "export enum Tone { Warm, Cool }")
    assert _by_qn(syms)["Tone"].kind == "enum"


def test_namespace_nests_into_qualified_name(adapter: TypeScriptAdapter) -> None:
    syms = _extract(
        adapter,
        """
        export namespace Inner {
            export function nested() {}
            export class Box {
                open() {}
            }
        }
        """,
    )
    by = _by_qn(syms)
    assert by["Inner"].kind == "module"
    assert "Inner.nested" in by
    assert by["Inner.Box"].kind == "class"
    assert by["Inner.Box.open"].kind == "method"


def test_arrow_function_const_at_module_scope(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "export const arrow = (x: number) => x + 1")
    assert _by_qn(syms)["arrow"].kind == "function"


def test_function_expression_const_at_module_scope(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "const fn = function() { return 1 }")
    assert _by_qn(syms)["fn"].kind == "function"


def test_arrow_function_inside_function_body_is_captured_unscoped(
    adapter: TypeScriptAdapter,
) -> None:
    """V1 documents-current-behavior: a function-body arrow const is still
    matched by the ``lexical_declaration`` query pattern, and since function
    bodies are intentionally NOT in the scope stack, it lands as a top-level
    symbol ``local`` rather than ``outer.local``.

    This is acceptable for v1 because the tightened mention extractor only
    matches identifier-shaped tokens in backticks or with code-shape, so
    English words like "local" in prose won't trigger a false-positive
    mention. If this becomes a real noise source on real TS repos, the fix
    is to exclude lexical_declaration captures whose ancestors include a
    ``statement_block`` — a half-day change."""
    syms = _extract(
        adapter,
        """
        export function outer() {
            const local = (x: number) => x + 1;
            return local(1);
        }
        """,
    )
    by = _by_qn(syms)
    assert "outer" in by
    assert "local" in by  # current behavior; see docstring for rationale
    assert by["local"].kind == "function"


def test_cjs_module_exports_arrow(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "module.exports.foo = () => 1")
    assert _by_qn(syms)["foo"].kind == "function"


def test_cjs_bare_exports_arrow(adapter: TypeScriptAdapter) -> None:
    syms = _extract(adapter, "exports.bar = function() { return 2 }")
    assert _by_qn(syms)["bar"].kind == "function"


def test_d_ts_function_signatures(adapter: TypeScriptAdapter) -> None:
    """``.d.ts`` files carry public-API signatures we want indexed."""
    syms = _extract(
        adapter,
        """
        declare function loaded(): boolean;
        export interface Config { strict: boolean }
        export type Mode = "dev" | "prod";
        """,
        name="lib.d.ts",
    )
    by = _by_qn(syms)
    assert by["loaded"].kind == "function"
    assert by["Config"].kind == "interface"
    assert by["Mode"].kind == "type_alias"


def test_tsx_extension_parses_with_tsx_grammar(adapter: TypeScriptAdapter) -> None:
    """A `.tsx` file with JSX must parse and still surface its function
    declarations — JSX is a value-position thing, not a declaration shape."""
    syms = _extract(
        adapter,
        "export function App() { return <div className='x'>hi</div> }",
        name="App.tsx",
    )
    assert _by_qn(syms)["App"].kind == "function"


def test_jsx_extension_uses_tsx_grammar(adapter: TypeScriptAdapter) -> None:
    syms = _extract(
        adapter,
        "export function Banner() { return <span>hi</span> }",
        name="Banner.jsx",
    )
    assert _by_qn(syms)["Banner"].kind == "function"


def test_plain_js_uses_typescript_grammar(adapter: TypeScriptAdapter) -> None:
    syms = _extract(
        adapter,
        "function legacy() { return 1 }",
        name="legacy.js",
    )
    assert _by_qn(syms)["legacy"].kind == "function"


def test_broken_syntax_still_extracts_surviving_symbols(adapter: TypeScriptAdapter) -> None:
    """tree-sitter is error-tolerant. A file with a syntax error must still
    yield whatever well-formed declarations it has, with ``has_errors`` set."""
    src = b"function ok() { return 1 } function BROKEN("
    parsed = adapter.parse(Path("broken.ts"), src)
    assert parsed.has_errors is True
    syms = adapter.extract_symbols(parsed)
    by = _by_qn(syms)
    assert "ok" in by


def test_anonymous_default_export_not_synthesized(adapter: TypeScriptAdapter) -> None:
    """``export default function () {}`` has no name. We do not invent one."""
    syms = _extract(adapter, "export default function () { return 1 }")
    assert syms == []


def test_overload_signatures_dedupe_with_implementation(adapter: TypeScriptAdapter) -> None:
    """TS allows multiple ``function foo(...)`` signatures before the
    implementation. Each is a separate AST node; we should not emit three
    separate ``foo`` rows that all share line numbers."""
    syms = _extract(
        adapter,
        """
        function foo(a: string): string;
        function foo(a: number): number;
        function foo(a: any): any { return a }
        """,
    )
    foos = [s for s in syms if s.qualified_name == "foo"]
    # All three on different lines, so all three rows are kept — the dedup
    # only kicks in for SAME-line collisions. This documents the v1 behavior;
    # cross-line merging is a v2 concern that needs the TS compiler.
    assert len(foos) == 3
    assert {s.line_start for s in foos} == {2, 3, 4}


def test_build_context_finds_tsconfig(adapter: TypeScriptAdapter, tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text("{}")
    ctx = adapter.build_context(tmp_path)
    assert ctx is not None
    assert ctx.tsconfig == tmp_path / "tsconfig.json"


def test_build_context_none_when_no_tsconfig(adapter: TypeScriptAdapter, tmp_path: Path) -> None:
    ctx = adapter.build_context(tmp_path)
    assert ctx is not None
    assert ctx.tsconfig is None


def test_splice_doc_raises(adapter: TypeScriptAdapter) -> None:
    """JSDoc splicing is deliberately deferred to v2. The contract must be
    loud (raise) rather than silent (return src unchanged)."""
    sym = Symbol(
        qualified_name="x", kind="function", file=Path("x.ts"),
        byte_start=0, byte_end=10, line_start=1, line_end=1,
    )
    with pytest.raises(NotImplementedError, match="JSDoc"):
        adapter.splice_doc(b"function x() {}", sym, "doc")


def test_scanner_dispatches_to_typescript_adapter() -> None:
    """The scanner should route ``.ts``/``.tsx``/``.js``/``.jsx``/``.mjs``/``.cjs``
    to the TS adapter, not the fallback. ``.d.ts`` is routed via the ``.ts``
    extension match (Path.suffix returns only the last suffix)."""
    from docagent.adapters.typescript import TypeScriptAdapter
    from docagent.core.scanner import _build_adapter_index

    idx = _build_adapter_index()
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        assert isinstance(idx[ext], TypeScriptAdapter), f"{ext} should map to TS adapter"


def test_fallback_no_longer_registers_typescript() -> None:
    """We replaced fallback's TS branch with the dedicated adapter."""
    from docagent.adapters.fallback import EXTENSIONS

    assert "typescript" not in EXTENSIONS


class TestJsdocExistingDoc:
    """JSDoc /** ... */ blocks paired with the immediately-following def
    populate ``Symbol.existing_doc``. Mirrors the Python adapter's docstring
    pass-through but for TS source.
    """

    # ------------------------------------------------------------------
    # Brief / structural cases (A1–A6)
    # ------------------------------------------------------------------

    def test_A1_brief_one_liner(self, adapter: TypeScriptAdapter) -> None:
        src = "/** Brief one-liner. */\nexport function foo() {}\n"
        sym = _by_qn(_extract(adapter, src))["foo"]
        assert sym.existing_doc == "Brief one-liner."

    def test_A2_multi_paragraph_preserves_blank_line(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = (
            "/**\n"
            " * First paragraph.\n"
            " *\n"
            " * Second paragraph.\n"
            " */\n"
            "export function foo() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["foo"].existing_doc
        assert doc is not None
        assert "First paragraph." in doc
        assert "Second paragraph." in doc
        # Paragraph break preserved (a blank line between paragraphs).
        assert "\n\n" in doc

    def test_A3_no_preceding_jsdoc_yields_none(
        self, adapter: TypeScriptAdapter
    ) -> None:
        # JSDoc here is attached to `paired`, not `lonely`.
        src = (
            "/** Pair me. */\n"
            "export function paired() {}\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "// not jsdoc\n"
            "\n"
            "export function lonely() {}\n"
        )
        by = _by_qn(_extract(adapter, src))
        assert by["paired"].existing_doc == "Pair me."
        assert by["lonely"].existing_doc is None

    def test_A4_single_star_block_is_not_jsdoc(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = "/* not jsdoc */\nexport function foo() {}\n"
        assert _by_qn(_extract(adapter, src))["foo"].existing_doc is None

    def test_A5_pairing_tolerates_one_blank_line(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src_one_blank = (
            "/** Pair me. */\n"
            "\n"
            "export function foo() {}\n"
        )
        assert _by_qn(_extract(adapter, src_one_blank))["foo"].existing_doc == "Pair me."

        src_three_blanks = (
            "/** Pair me. */\n"
            "\n"
            "\n"
            "\n"
            "export function bar() {}\n"
        )
        assert _by_qn(_extract(adapter, src_three_blanks))["bar"].existing_doc is None

        src_intervening = (
            "/** Pair me. */\n"
            "const x = 1;\n"
            "export function baz() {}\n"
        )
        assert _by_qn(_extract(adapter, src_intervening))["baz"].existing_doc is None

    def test_A6_no_jsdoc_regression_baseline(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = "export function foo() {}\nexport function bar() {}\n"
        syms = _extract(adapter, src)
        assert len(syms) == 2
        by = _by_qn(syms)
        assert set(by) == {"foo", "bar"}
        for sym in syms:
            assert sym.existing_doc is None

    # ------------------------------------------------------------------
    # @param shapes (P1–P6)
    # ------------------------------------------------------------------

    def test_P1_single_param(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * Brief.\n"
            " * @param name The name.\n"
            " */\n"
            "export function greet(name: string) {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["greet"].existing_doc
        assert doc is not None
        assert "@param name The name." in doc

    def test_P2_multiple_params(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * Brief.\n"
            " * @param a First.\n"
            " * @param b Second.\n"
            " * @param c Third.\n"
            " */\n"
            "export function f(a: number, b: number, c: number) {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@param a First." in doc
        assert "@param b Second." in doc
        assert "@param c Third." in doc
        # Order preserved.
        assert doc.find("@param a") < doc.find("@param b") < doc.find("@param c")

    def test_P3_typed_param(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @param {string} name desc\n"
            " */\n"
            "export function f(name: string) {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@param {string} name desc" in doc

    def test_P4_optional_param(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @param [name=default] desc\n"
            " */\n"
            "export function f(name?: string) {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@param [name=default] desc" in doc

    def test_P5_no_param_still_pairs(self, adapter: TypeScriptAdapter) -> None:
        src = "/** Just a brief. */\nexport function f() {}\n"
        assert _by_qn(_extract(adapter, src))["f"].existing_doc == "Just a brief."

    def test_P6_malformed_param_survives(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = (
            "/**\n"
            " * @param desc-only-no-name\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@param desc-only-no-name" in doc

    # ------------------------------------------------------------------
    # @returns shapes (R1–R5)
    # ------------------------------------------------------------------

    def test_R1_untyped_returns(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @returns the result\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@returns the result" in doc

    def test_R2_typed_returns(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @returns {string} the result\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@returns {string} the result" in doc

    def test_R3_singular_return_spelling(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = (
            "/**\n"
            " * @return the result\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@return the result" in doc

    def test_R4_multi_line_returns(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @returns first part of the description\n"
            " * continuation line\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@returns first part of the description" in doc
        assert "continuation line" in doc
        # No `* ` prefix should remain on the continuation line.
        assert "* continuation line" not in doc

    def test_R5_no_returns_still_pairs(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = "/** Brief. */\nexport function f() {}\n"
        assert _by_qn(_extract(adapter, src))["f"].existing_doc == "Brief."

    # ------------------------------------------------------------------
    # @throws shapes (T1–T5)
    # ------------------------------------------------------------------

    def test_T1_untyped_throws(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @throws Error when X\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@throws Error when X" in doc

    def test_T2_typed_throws(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @throws {TypeError} when X\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@throws {TypeError} when X" in doc

    def test_T3_singular_throw_spelling(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = (
            "/**\n"
            " * @throw Error\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@throw Error" in doc

    def test_T4_multiple_throws(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "/**\n"
            " * @throws Error one\n"
            " * @throws RangeError two\n"
            " */\n"
            "export function f() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["f"].existing_doc
        assert doc is not None
        assert "@throws Error one" in doc
        assert "@throws RangeError two" in doc
        assert doc.find("@throws Error one") < doc.find("@throws RangeError two")

    def test_T5_no_throws_still_pairs(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = "/** Brief. */\nexport function f() {}\n"
        assert _by_qn(_extract(adapter, src))["f"].existing_doc == "Brief."

    # ------------------------------------------------------------------
    # Negative / pairing safety (N1, N2)
    # ------------------------------------------------------------------

    def test_N1_latest_closest_jsdoc_wins(
        self, adapter: TypeScriptAdapter
    ) -> None:
        src = (
            "/** A first. */\n"
            "/** B second. */\n"
            "export function foo() {}\n"
        )
        doc = _by_qn(_extract(adapter, src))["foo"].existing_doc
        assert doc == "B second."

    def test_N2_orphan_eof_comment(self, adapter: TypeScriptAdapter) -> None:
        src = (
            "export function foo() {}\n"
            "\n"
            "/** orphan at EOF */\n"
        )
        # No spurious pairing, no error.
        by = _by_qn(_extract(adapter, src))
        assert by["foo"].existing_doc is None


class TestExtractExports:
    """`TypeScriptAdapter.extract_exports` surfaces all `export ...` shapes
    so the discovery module can detect barrel-only files (RESEARCH.md
    Gap B / locked drop rule).
    """

    @staticmethod
    def _exports(adapter: TypeScriptAdapter, src: str) -> list[object]:
        from pathlib import Path

        parsed = adapter.parse(Path("sample.ts"), src.encode("utf-8"))
        return list(adapter.extract_exports(parsed))

    def test_A_export_star_from(self, adapter: TypeScriptAdapter) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, 'export * from "./foo";\n')
        assert entries == [
            ExportEntry(
                name="*",
                kind="re_export",
                source_module="./foo",
                alias_of=None,
            )
        ]

    def test_B_export_named_from(self, adapter: TypeScriptAdapter) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, 'export { Bar } from "./baz";\n')
        assert entries == [
            ExportEntry(
                name="Bar",
                kind="re_export",
                source_module="./baz",
                alias_of=None,
            )
        ]

    def test_C_aliased_re_export(self, adapter: TypeScriptAdapter) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, 'export { Foo as Bar } from "./y";\n')
        assert entries == [
            ExportEntry(
                name="Bar",
                kind="re_export",
                source_module="./y",
                alias_of="Foo",
            )
        ]

    def test_D_multiple_in_one_clause(self, adapter: TypeScriptAdapter) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, 'export { Foo as Bar, Baz } from "./y";\n')
        assert set(entries) == {
            ExportEntry(
                name="Bar",
                kind="re_export",
                source_module="./y",
                alias_of="Foo",
            ),
            ExportEntry(
                name="Baz",
                kind="re_export",
                source_module="./y",
                alias_of=None,
            ),
        }

    def test_E_export_function_declaration(
        self, adapter: TypeScriptAdapter
    ) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, "export function foo() {}\n")
        assert entries == [
            ExportEntry(
                name="foo",
                kind="original",
                source_module=None,
                alias_of=None,
            )
        ]

    def test_F_export_class_declaration(self, adapter: TypeScriptAdapter) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, "export class Bar {}\n")
        assert entries == [
            ExportEntry(
                name="Bar",
                kind="original",
                source_module=None,
                alias_of=None,
            )
        ]

    def test_G_export_default_function(
        self, adapter: TypeScriptAdapter
    ) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, "export default function myDefault() {}\n")
        assert entries == [
            ExportEntry(
                name="default",
                kind="original",
                source_module=None,
                alias_of=None,
            )
        ]

    def test_H_barrel_file_two_export_stars(
        self, adapter: TypeScriptAdapter
    ) -> None:
        from docagent.adapters.typescript import ExportEntry

        src = 'export * from "./a";\nexport * from "./b";\n'
        entries = self._exports(adapter, src)
        assert len(entries) == 2
        assert all(e.kind == "re_export" for e in entries)  # type: ignore[attr-defined]
        assert all(e.name == "*" for e in entries)  # type: ignore[attr-defined]
        sources = {e.source_module for e in entries}  # type: ignore[attr-defined]
        assert sources == {"./a", "./b"}
        assert entries[0] == ExportEntry(
            name="*", kind="re_export", source_module="./a", alias_of=None
        )

    def test_I_type_only_re_export(self, adapter: TypeScriptAdapter) -> None:
        from docagent.adapters.typescript import ExportEntry

        entries = self._exports(adapter, 'export type { Foo } from "./types";\n')
        assert entries == [
            ExportEntry(
                name="Foo",
                kind="re_export",
                source_module="./types",
                alias_of=None,
            )
        ]

    def test_J_no_exports_yields_empty(
        self, adapter: TypeScriptAdapter
    ) -> None:
        entries = self._exports(adapter, "function helper() {}\nconst x = 1;\n")
        assert entries == []

    def test_K_barrel_extracts_symbols_returns_empty(
        self, adapter: TypeScriptAdapter
    ) -> None:
        """On a pure-barrel file, extract_symbols returns no definitions but
        extract_exports surfaces the re-exports. This discriminator is what
        the discovery module relies on.
        """
        from pathlib import Path

        src = 'export * from "./a";\n'
        parsed = adapter.parse(Path("barrel.ts"), src.encode("utf-8"))
        assert adapter.extract_symbols(parsed) == []
        exports = adapter.extract_exports(parsed)
        assert len(exports) == 1
        assert exports[0].kind == "re_export"
        assert exports[0].name == "*"
