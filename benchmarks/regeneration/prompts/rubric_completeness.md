You are scoring **completeness** of a regenerated documentation artifact.
This is one of three axes from the DocAgent paper's evaluation rubric
(Yang et al., ACL Demo 2025). The three axes are scored INDEPENDENTLY so
a doc can't trade one for another.

**Completeness** asks: how much of the project's important public surface
is documented at all? It is concerned with **coverage**, not correctness.
A confidently-wrong but comprehensive doc scores high on completeness and
low on truthfulness.

## What counts as the project's public surface

For libraries: every public class, function, decorator, and module-level
constant in the import path. Use the source tree to enumerate (exclude
underscore-prefixed names, `__all__` overrides if present).

For CLIs: every subcommand, top-level flag, and config option.

For frameworks: every public extension point (hook, middleware, plugin
interface) plus the public API of the core engine.

External-facing concerns also count:
- Install / quickstart paths
- Compatibility matrix (Python / Node / OS versions)
- Configuration file format
- Dependency requirements

## Inputs

### Source code surface (build the inventory)

You have read access to the repository at the root level. Use Glob and
Grep to enumerate the public surface BEFORE reading the regenerated doc.
Do not let the doc anchor your expectations.

### Regenerated doc

{regenerated_doc}

## Scoring

Score 0 to 5, integer. Anchor each level concretely so re-runs are
stable:

- **5** — Every name in the public-API inventory is mentioned by name
  at least once; install/quickstart/config/version-compat all present.
- **4** — ≥80% of public-API names mentioned; install + quickstart
  present; at most one of {{config, version-compat}} missing.
- **3** — ≥50% of public-API names mentioned; install present;
  several gaps in the external-facing concerns.
- **2** — <50% of public-API names mentioned; clear major omissions
  (e.g. quickstart absent, headline feature undocumented).
- **1** — Doc covers only the install step and a marketing tagline.
- **0** — Doc is empty, irrelevant, or covers nothing checkable.

## Output (JSON only)

```json
{{
  "public_surface_size": 0,
  "surface_items_mentioned": 0,
  "coverage_ratio": 0.0,
  "missing_critical": ["names of critical public-API or concerns the doc omits"],
  "score": 0,
  "rationale": "two sentences max, naming the specific gaps that drove the score down"
}}
```

`coverage_ratio = surface_items_mentioned / public_surface_size` (3 decimals).

Independence: do NOT lower this score for factual errors (that's
truthfulness) or for poor prose (that's helpfulness). Mention by name
with the wrong description still counts as covered.
