---
docagent_artifact: api_reference
module: docagent.artifacts._api_reference_render
generated_by: docagent
---

# `docagent.artifacts._api_reference_render`


This module owns the deterministic Markdown chunks for the `api_reference` artifact, which renders a per-module page as a sandwich of fixed blocks around LLM-generated opener and workflows text. <!-- ground: docagent/artifacts/_api_reference_render.py:1-12 --> The pure functions `frontmatter`, `h1`, `public_surface_table`, `see_also_section`, and `footer` each emit one independently testable chunk from a tuple of `ModuleSymbol` rows plus optional Phase-7 inputs (`export_edges`, `existing_docs`), and `assemble_page` composes them with the LLM chunks into the final page string. <!-- ground: docagent/artifacts/_api_reference_render.py:89-103 --> <!-- ground: docagent/artifacts/_api_reference_render.py:116-137 --> <!-- ground: docagent/artifacts/_api_reference_render.py:230-270 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `frontmatter` | function | `frontmatter` |
| `h1` | function | `h1` |
| `public_surface_table` | function | `public_surface_table` |
| `see_also_section` | function | `see_also_section` |
| `footer` | function | `footer` |
| `assemble_page` | function | `assemble_page` |

## Common workflows

Compose a full module page from symbol rows plus the two LLM-generated chunks:

```python
from docagent.artifacts._api_reference_render import assemble_page

page = assemble_page(
    dotted_name="mypkg.submod",
    symbols=symbols,                  # tuple[ModuleSymbol, ...]
    siblings=["mypkg.other"],
    parent="mypkg",
    opener_md=opener_text,            # cleaned LLM output
    workflows_md=workflows_text,      # cleaned LLM output
)
```
<!-- ground: docagent/artifacts/_api_reference_render.py:230-270 -->

Render just the public-surface table — optionally with the Phase-7 `Exported as` column and JSDoc-brief suffixes — when you only need that chunk:

```python
from docagent.artifacts._api_reference_render import public_surface_table

md = public_surface_table(
    "mypkg.submod",
    symbols,
    export_edges=edges,        # Mapping[str, ExportEntry] or list[ExportEntry]
    existing_docs={"mypkg.submod.Foo": "Does the thing."},
)
```
<!-- ground: docagent/artifacts/_api_reference_render.py:116-200 -->

Build the smaller deterministic chunks directly — useful in tests or when splicing into a custom layout:

```python
from docagent.artifacts._api_reference_render import (
    frontmatter, h1, see_also_section, footer,
)

head = frontmatter("mypkg.submod") + h1("mypkg.submod")
tail = see_also_section("mypkg.submod", ["mypkg.other"], parent="mypkg") + footer()
```
<!-- ground: docagent/artifacts/_api_reference_render.py:89-103 --> <!-- ground: docagent/artifacts/_api_reference_render.py:207-227 -->

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
