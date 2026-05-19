---
docagent_artifact: api_reference
module: docagent.adapters.typescript
generated_by: docagent
---

# `docagent.adapters.typescript`


The TypeScript / JavaScript adapter implements the `LanguageAdapter` contract for `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, and `.d.ts` files, dispatching to the `tsx` tree-sitter grammar for JSX-bearing files and `typescript` otherwise. <!-- ground: docagent/adapters/typescript.py:1-6 --> `TypeScriptAdapter.parse` produces a `ParseResult`, `extract_symbols` walks tag-query captures to emit qualified-name `Symbol` rows (pairing each `@def.*` with its tightest `@name` capture and an optionally adjacent JSDoc block), and `extract_exports` returns `ExportEntry` rows describing the module's public surface (originals, aliased re-exports, `export *`, and `export default`). <!-- ground: docagent/adapters/typescript.py:239-345 --> <!-- ground: docagent/adapters/typescript.py:347-467 --> `doc_comment_style` returns a JSDoc style descriptor, `splice_doc` deliberately raises `NotImplementedError` (in-place JSDoc edits are out of v1 scope), `local_references` returns `[]` and `semantic_references` returns `None`, and `build_context` reports a `tsconfig.json` if one exists at the repo root. <!-- ground: docagent/adapters/typescript.py:469-488 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `ExportEntry` | class | `ExportEntry` |
| `TypeScriptAdapter` | class | `TypeScriptAdapter` |
| `TypeScriptAdapter.parse` | method | `parse` |
| `TypeScriptAdapter.extract_symbols` | method | `extract_symbols` |
| `TypeScriptAdapter.extract_exports` | method | `extract_exports` |
| `TypeScriptAdapter.doc_comment_style` | method | `doc_comment_style` |
| `TypeScriptAdapter.splice_doc` | method | `splice_doc` |
| `TypeScriptAdapter.local_references` | method | `local_references` |
| `TypeScriptAdapter.semantic_references` | method | `semantic_references` |
| `TypeScriptAdapter.build_context` | method | `build_context` |

## Common workflows

Parse a TypeScript file and extract its qualified-name symbol rows:

```python
from pathlib import Path
from docagent.adapters.typescript import TypeScriptAdapter

adapter = TypeScriptAdapter()
path = Path("src/foo.ts")
src = path.read_bytes()
parsed = adapter.parse(path, src)
for sym in adapter.extract_symbols(parsed):
    print(sym.qualified_name, sym.kind, sym.line_start)
```
<!-- ground: docagent/adapters/typescript.py:229-345 -->

Enumerate a module's exports to tell barrel files apart from modules with original declarations:

```python
parsed = adapter.parse(Path("src/index.ts"), Path("src/index.ts").read_bytes())
exports = adapter.extract_exports(parsed)
re_exports = [e for e in exports if e.kind == "re_export"]
originals = [e for e in exports if e.kind == "original"]
is_barrel = bool(re_exports) and not originals
```
<!-- ground: docagent/adapters/typescript.py:347-467 -->

Probe the per-repo build context and the doc-comment style; note that `splice_doc` is intentionally unimplemented in v1:

```python
ctx = adapter.build_context(Path("/path/to/repo"))
# ctx.tsconfig is a Path if tsconfig.json exists, else None
style = adapter.doc_comment_style(sym)  # JSDoc: /** ... */, line prefix " * "
# adapter.splice_doc(src, sym, doc)  # raises NotImplementedError in v1
```
<!-- ground: docagent/adapters/typescript.py:469-488 -->

## See also

- [`docagent.adapters.base`](docagent.adapters.base.md)
- [`docagent.adapters.fallback`](docagent.adapters.fallback.md)
- [`docagent.adapters.python`](docagent.adapters.python.md)

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
