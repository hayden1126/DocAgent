---
docagent_artifact: api_reference
module: docagent.adapters.fallback
generated_by: docagent
---

# `docagent.adapters.fallback`


`docagent.adapters.fallback` provides `FallbackAdapter`, a tree-sitter–only `LanguageAdapter` implementation used for languages without a dedicated deepener (Rust, Go, Java, C++). The class wires per-language tree-sitter queries (`GENERIC_QUERIES`), file extensions (`EXTENSIONS`), comment conventions (`DOC_STYLES`), and node-type-to-symbol-kind maps (`KIND_MAP`) so that `parse` and `extract_symbols` can locate functions/classes/methods, `doc_comment_style` and `splice_doc` can insert language-appropriate doc comments above a symbol, and `local_references` / `semantic_references` / `build_context` return empty results because cross-references are lexical-only in v1. <!-- ground: docagent/adapters/fallback.py:1-88 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `FallbackAdapter` | class | `FallbackAdapter` |
| `FallbackAdapter.parse` | method | `parse` |
| `FallbackAdapter.extract_symbols` | method | `extract_symbols` |
| `FallbackAdapter.doc_comment_style` | method | `doc_comment_style` |
| `FallbackAdapter.splice_doc` | method | `splice_doc` |
| `FallbackAdapter.local_references` | method | `local_references` |
| `FallbackAdapter.semantic_references` | method | `semantic_references` |
| `FallbackAdapter.build_context` | method | `build_context` |

## Common workflows

Construct an adapter for a supported language and parse a source file into a `ParseResult`, then extract its top-level symbols:

```python
from pathlib import Path
from docagent.adapters.fallback import FallbackAdapter

adapter = FallbackAdapter("rust")
path = Path("src/lib.rs")
result = adapter.parse(path, path.read_bytes())
symbols = adapter.extract_symbols(result)
for s in symbols:
    print(s.kind, s.qualified_name, s.line_start, s.line_end)
```
<!-- ground: docagent/adapters/fallback.py:91-141 -->

Splice a generated doc comment above a discovered symbol using the language's comment style (e.g. `///` for Rust, `/** … */` for Java/C++):

```python
new_src = adapter.splice_doc(result.source, symbols[0], "Adds two integers.")
Path("src/lib.rs").write_bytes(new_src)
```
<!-- ground: docagent/adapters/fallback.py:143-162 -->

Instantiating with an unregistered language id raises `KeyError`, and the reference/context hooks intentionally return empty/`None` since the fallback only supports lexical extraction:

```python
FallbackAdapter("python")          # raises KeyError
adapter.local_references(result)   # []
adapter.semantic_references(Path("."))  # None
adapter.build_context(Path("."))        # None
```
<!-- ground: docagent/adapters/fallback.py:92-98 --> <!-- ground: docagent/adapters/fallback.py:164-171 -->

## See also

- [`docagent.adapters.base`](docagent.adapters.base.md)
- [`docagent.adapters.python`](docagent.adapters.python.md)
- [`docagent.adapters.typescript`](docagent.adapters.typescript.md)

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
