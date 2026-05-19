---
docagent_artifact: api_reference
module: docagent.adapters.python
generated_by: docagent
---

# `docagent.adapters.python`


The Python adapter is the v1 "deepener" that gives DocAgent format-preserving symbol extraction and docstring splicing for `.py`/`.pyi` files via libcst, with Jedi-backed semantic references scaffolded but intentionally unwired. <!-- ground: docagent/adapters/python.py:1-7 --> `PythonAdapter` implements the `LanguageAdapter` protocol — `parse` produces a `ParseResult` wrapping a libcst module, `extract_symbols` walks the tree with `_SymbolCollector` (which uses `_ByteOffsetTable.at` to convert libcst's code-point columns into UTF-8 byte offsets and tracks nested scope so `FunctionDef` inside a `ClassDef` becomes `"method"`), and `splice_doc` runs `_DocstringSplicer` to rewrite or insert a docstring at a target qualified name. <!-- ground: docagent/adapters/python.py:195-216 --> <!-- ground: docagent/adapters/python.py:35-65 --> <!-- ground: docagent/adapters/python.py:105-123 --> `doc_comment_style` returns the module-level `PYTHON_DOC_STYLE` (triple-quoted, placed `inside` the def, indented four spaces), while `local_references`, `semantic_references`, and `build_context` are deliberate no-ops that callers fall through past in v1. <!-- ground: docagent/adapters/python.py:26-32 --> <!-- ground: docagent/adapters/python.py:209-225 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `_ByteOffsetTable.at` | method | `at` |
| `_SymbolCollector.visit_FunctionDef` | method | `visit_FunctionDef` |
| `_SymbolCollector.leave_FunctionDef` | method | `leave_FunctionDef` |
| `_SymbolCollector.visit_ClassDef` | method | `visit_ClassDef` |
| `_SymbolCollector.leave_ClassDef` | method | `leave_ClassDef` |
| `_DocstringSplicer.visit_FunctionDef` | method | `visit_FunctionDef` |
| `_DocstringSplicer.leave_FunctionDef` | method | `leave_FunctionDef` |
| `_DocstringSplicer.visit_ClassDef` | method | `visit_ClassDef` |
| `_DocstringSplicer.leave_ClassDef` | method | `leave_ClassDef` |
| `PythonAdapter` | class | `PythonAdapter` |
| `PythonAdapter.parse` | method | `parse` |
| `PythonAdapter.extract_symbols` | method | `extract_symbols` |
| `PythonAdapter.doc_comment_style` | method | `doc_comment_style` |
| `PythonAdapter.splice_doc` | method | `splice_doc` |
| `PythonAdapter.local_references` | method | `local_references` |
| `PythonAdapter.semantic_references` | method | `semantic_references` |
| `PythonAdapter.build_context` | method | `build_context` |

## Common workflows

Parse a file and extract its symbol table:

```python
from pathlib import Path
from docagent.adapters.python import PythonAdapter

adapter = PythonAdapter()
path = Path("docagent/adapters/python.py")
src = path.read_bytes()

tree = adapter.parse(path, src)
symbols = adapter.extract_symbols(tree)
for sym in symbols:
    print(sym.kind, sym.qualified_name, sym.line_start, sym.line_end)
```
<!-- ground: docagent/adapters/python.py:199-207 -->

Splice a new docstring into a target symbol by qualified name; the splicer replaces an existing leading string expression or inserts a new one at the top of the body:

```python
new_src = adapter.splice_doc(
    src,
    sym=next(s for s in symbols if s.qualified_name == "PythonAdapter.parse"),
    doc="Parse *src* into a libcst ParseResult.",
)
Path("docagent/adapters/python.py").write_bytes(new_src)
```
<!-- ground: docagent/adapters/python.py:212-216 --> <!-- ground: docagent/adapters/python.py:177-192 -->

Query the doc-comment style and the (currently stubbed) reference hooks; the latter two return empty/None so the orchestrator can fall through to lexical fallbacks:

```python
style = adapter.doc_comment_style(symbols[0])           # PYTHON_DOC_STYLE
assert adapter.local_references(tree) == []
assert adapter.semantic_references(Path(".")) is None
assert adapter.build_context(Path(".")) is None
```
<!-- ground: docagent/adapters/python.py:209-225 -->

## See also

- [`docagent.adapters.base`](docagent.adapters.base.md)
- [`docagent.adapters.fallback`](docagent.adapters.fallback.md)
- [`docagent.adapters.typescript`](docagent.adapters.typescript.md)

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
