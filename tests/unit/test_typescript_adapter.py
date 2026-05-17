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
