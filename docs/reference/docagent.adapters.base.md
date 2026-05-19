---
docagent_artifact: api_reference
module: docagent.adapters.base
generated_by: docagent
---

# `docagent.adapters.base`


`docagent.adapters.base` defines the `LanguageAdapter` Protocol and the shared dataclasses that every per-language adapter exchanges with the rest of DocAgent — parsing, symbol extraction, doc-comment styling, in-place doc splicing, and lexical/semantic references. <!-- ground: docagent/adapters/base.py:1-6 --> The frozen dataclasses (`DocStyle`, `Symbol`, `Ref`, `ParseResult`, `BuildContext`) carry data between stages: `parse` returns a `ParseResult`, `extract_symbols` turns it into `Symbol`s, `doc_comment_style` reports the adapter's preferred `DocStyle`, `splice_doc` rewrites source bytes, and `local_references` / `semantic_references` emit `Ref`s tagged `lexical` or `semantic`. <!-- ground: docagent/adapters/base.py:79-102 --> `BuildContext` is an optional bundle of tool-config paths (e.g. `compile_commands`, `cargo_toml`, `tsconfig`) that deepeners need when computing semantic references. <!-- ground: docagent/adapters/base.py:68-76 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `DocStyle` | class | `DocStyle` |
| `Symbol` | class | `Symbol` |
| `Ref` | class | `Ref` |
| `ParseResult` | class | `ParseResult` |
| `BuildContext` | class | `BuildContext` |
| `LanguageAdapter` | class | `LanguageAdapter` |
| `LanguageAdapter.parse` | method | `parse` |
| `LanguageAdapter.extract_symbols` | method | `extract_symbols` |
| `LanguageAdapter.doc_comment_style` | method | `doc_comment_style` |
| `LanguageAdapter.splice_doc` | method | `splice_doc` |
| `LanguageAdapter.local_references` | method | `local_references` |
| `LanguageAdapter.semantic_references` | method | `semantic_references` |
| `LanguageAdapter.build_context` | method | `build_context` |

## Common workflows

Type-check a concrete adapter against the protocol at runtime — `LanguageAdapter` is `@runtime_checkable`, so `isinstance` works:

```python
from pathlib import Path
from docagent.adapters.base import LanguageAdapter, ParseResult, Symbol

def index_file(adapter: LanguageAdapter, path: Path) -> list[Symbol]:
    assert isinstance(adapter, LanguageAdapter)
    src = path.read_bytes()
    tree: ParseResult = adapter.parse(path, src)
    return adapter.extract_symbols(tree)
```
<!-- ground: docagent/adapters/base.py:79-87 -->

Construct a `DocStyle` for a language that puts doc comments above the symbol with a line prefix (e.g. Rust-style `///`):

```python
from docagent.adapters.base import DocStyle

rust_doc = DocStyle(
    delim_open="",
    delim_close="",
    line_prefix="/// ",
    placement="above",
)
```
<!-- ground: docagent/adapters/base.py:21-29 -->

Splice a generated docstring into a file and merge lexical refs with semantic refs when a deepener is configured:

```python
from pathlib import Path
from docagent.adapters.base import LanguageAdapter, Ref

def rewrite_with_doc(adapter: LanguageAdapter, sym, doc: str, src: bytes) -> bytes:
    return adapter.splice_doc(src, sym, doc)

def all_refs(adapter: LanguageAdapter, tree, repo_root: Path) -> list[Ref]:
    refs = list(adapter.local_references(tree))
    semantic = adapter.semantic_references(repo_root)
    if semantic is not None:
        refs.extend(semantic)
    return refs
```
<!-- ground: docagent/adapters/base.py:90-100 -->

## See also

- [`docagent.adapters.fallback`](docagent.adapters.fallback.md)
- [`docagent.adapters.python`](docagent.adapters.python.md)
- [`docagent.adapters.typescript`](docagent.adapters.typescript.md)

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
