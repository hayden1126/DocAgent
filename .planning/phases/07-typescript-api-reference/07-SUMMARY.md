---
phase: 07-typescript-api-reference
status: SHIPPED
shipped: 2026-05-17
requirements: [TSAPI-01]
test_delta: 304 → 385 (+81)
commits: 6
plans_executed: [07-01, 07-02, 07-03, 07-04, 07-05, 07-06]
prompt_version_bump: "1 → 2 (one-time Python fingerprint regeneration)"
---

# Phase 7: TypeScript `api_reference` — SHIPPED

**One-liner:** Multi-file `api_reference` artifact now serves both Python and
TypeScript repos via one artifact id; discovery cascade reads
`package.json#exports` → `tsconfig.json#include` → glob; JSDoc surfaces in
the table; `--max-modules` cap is combined-language and deterministic-sort
stable.

## Per-plan summary

### 07-01 — TS adapter JSDoc → `Symbol.existing_doc` (commit `a2ad152`)

* **Files:** `docagent/adapters/typescript.py`,
  `docagent/adapters/queries/typescript_tags.scm`,
  `tests/unit/test_typescript_adapter.py`.
* **What changed:** Tree-sitter query gains a top-level
  `(comment) @jsdoc.candidate` capture (Python filters `/**` vs `/*` for
  runtime portability across tree-sitter binding versions). `extract_symbols`
  collects JSDoc blocks, pairs each def with the latest `/**` comment
  whose end-line falls in `[def.start_line - 2, def.start_line - 1]` AND
  whose intervening lines are all blank. Body cleaner (`_clean_jsdoc_body`)
  strips `/**`/`*/` delimiters and per-line `* ` prefixes; preserves
  paragraph breaks; collapses runs of 2+ blank lines.
* **Tests added:** +24 in `TestJsdocExistingDoc` (6 brief/structural + 6
  `@param` + 5 `@returns` + 5 `@throws` + 2 negative pairing).
* **Deviations:** None.
* **Gotchas closed:** RESEARCH.md Gap A (`existing_doc IS NULL` for every
  TS row in the index before this plan).

### 07-02 — TS adapter `extract_exports()` (commit `99c2e3b`)

* **Files:** `docagent/adapters/typescript.py`,
  `docagent/adapters/queries/typescript_exports.scm` (NEW),
  `tests/unit/test_typescript_adapter.py`.
* **What changed:** New `ExportEntry` dataclass + `extract_exports(parsed)`
  method on `TypeScriptAdapter`, driven by a SEPARATE `.scm` query file
  (`typescript_exports.scm`) — keeps the existing `extract_symbols`
  contract focused on definitions. Captures every `export_statement` node
  and walks its children in Python to disambiguate `export *`,
  `export { x as y } [from]`, `export type { ... }`, `export default <decl>`,
  and `export <function|class|const>`. Returns entries in source-file order
  by start_byte.
* **Tests added:** +11 in `TestExtractExports` covering all 8 canonical
  shapes (A–K) plus the barrel-discriminator case
  (`extract_symbols` returns `[]` AND `extract_exports` returns re-export
  rows — the rule the discovery cascade keys on).
* **Deviations:** None.
* **Gotchas closed:** RESEARCH.md Gap B (zero `export_statement` captures
  in `typescript_tags.scm`).

### 07-03 — JSONC stripper (commit `424430e`)

* **Files:** `docagent/artifacts/_jsonc.py` (NEW),
  `tests/unit/test_jsonc.py` (NEW).
* **What changed:** Zero-dep `parse_jsonc(text)` reads the JSONC subset
  `tsc` accepts (line comments, block comments, trailing commas) and
  hands the cleaned string to `json.loads`. No new pip deps; the
  slop-squatted `pyjsonc` PyPI name (flagged in RESEARCH.md's Package
  Legitimacy Audit) is explicitly NOT used.
* **Tests added:** +12 covering pure JSON passthrough, line + block
  comments, trailing commas, URL preservation inside strings, block-before-line
  ordering, and `json.JSONDecodeError` surfacing on out-of-subset input.
* **Deviations:** **Rule 1 — bug fix.** The plan specified a three-regex
  approach. That form silently corrupts glob patterns like `"src/**/*"`
  because `/**/` matches the `/\*.*?\*/` block-comment regex. Switched to
  a string-aware character-walking scanner (~50 LOC). Same public API,
  zero deps, all 12 plan-specified test cases pass, plus the regression
  case the regex would have failed.
* **Gotchas closed:** real-world `tsconfig.json` files that embed glob
  patterns inside string values now round-trip correctly.

### 07-04 — TS module-discovery cascade (commit `145cbce`)

* **Files:** `docagent/artifacts/_ts_module_discovery.py` (NEW),
  `tests/unit/test_ts_module_discovery.py` (NEW).
* **What changed:** Mirrors `_module_discovery.py`'s shape for TypeScript.
  Three-tier cascade with first-non-empty short-circuit:
  1. `package.json#exports` — concrete entries become source paths;
     `./dist/x.js` resolves to `src/x.<ts-ext>` when the source peer
     exists; wildcard-only maps downgrade to "absent" with one WARN.
  2. `tsconfig.json#include` — parsed via `parse_jsonc` (Plan 07-03);
     uses `pathspec.GitIgnoreSpec` (already a dep) to match glob patterns.
  3. Filesystem glob over the 7 TS extensions.

  Barrel files (`extract_exports` returns ≥1 entries, all `kind='re_export'`)
  are dropped. Path-traversal in exports values (`"./bad": "../../etc/passwd"`)
  is rejected with a WARN. Private-only modules drop via the shared
  `_is_public_leaf` filter. `_file_to_dotted_ts` strips `src/`/`lib/`/`dist/`
  prefixes BEFORE the excluded-top-dir check (so `dist/x.ts` decomposes to
  `x` per CONTEXT-locked TS conventions) and handles `.d.ts` longest-suffix
  (not `Path.stem` — `Path("foo.d.ts").stem == "foo.d"`).
  `sibling_modules_ts` / `parent_module_ts` delegate to the
  language-agnostic Python helpers (CONTEXT Q2 locked: dotted-prefix scoping
  works cross-language).
* **Tests added:** +15 covering dotted-name conversion (basic, `.d.ts`,
  all 7 extensions, excluded dirs, edge cases), the three cascade levels,
  wildcard-only fallback with WARN, barrel-only drop, private-only drop,
  path-traversal rejection, and the sibling/parent helpers.
* **Deviations:** **Minor refinement.** Added a TS-specific
  `_TS_EXCLUDED_TOP_DIRS` (Python's set + `node_modules`) because
  `node_modules/` isn't in the Python excluded set and a naive reuse would
  let `node_modules/x.ts` decompose to `node_modules.x`. Documented inline.
* **Gotchas closed:** locked barrel-file drop rule (CONTEXT.md) is now
  enforceable; the `--max-modules` Pitfall-5 prerequisite is in place.

### 07-05 — Language-dispatch + render extensions + PROMPT_VERSION bump (commit `48828d9`)

* **Files:** `docagent/artifacts/api_reference.py`,
  `docagent/artifacts/_module_discovery.py`,
  `docagent/artifacts/_api_reference_render.py`,
  `docagent/prompts/api_reference.py`,
  `tests/unit/test_api_reference_render.py`.
* **What changed:** Refactored `ApiReferenceArtifact.plan()` to dispatch
  per language: discovery runs for both `python` and `typescript` rows,
  results merge into one list, deterministic-sort by dotted_name, then
  `--max-modules` caps the COMBINED list (RESEARCH.md Pitfall 5 closed).
  Per-task payload now carries `language`; `generate()` forwards it to
  `format_prompt()` so the prompt picks the language descriptor and the
  optional JSDoc-section paragraph. `PROMPT_VERSION` bumped 1 → 2 with the
  locked greppable comment on the line immediately above the assignment
  (verify guard: `grep -B1 'PROMPT_VERSION = "2"' ... | grep -q "Phase 7: bumped 1"`).

  Render extensions in `_api_reference_render.py`:
  * `public_surface_table` and `assemble_page` gain optional
    `export_edges` and `existing_docs` kwargs — both default to `None` so
    pre-Phase-7 callers produce byte-identical output.
  * When `export_edges` is non-empty, an extra `Exported as` column is
    appended. Aliased re-exports render as `Bar (from other.Foo)` (CONTEXT
    Q1 locked); `export *` as `(re-export *)`; originals as `—`.
  * When `existing_docs` is non-empty, the JSDoc brief (first line) is
    appended to the Signature column after a ` — ` separator, truncated
    at 80 chars.

  `ModuleSymbol` gains `existing_doc: str | None = None` — non-breaking
  for any pre-Phase-7 caller. `discover_python_modules` reads it from
  either the legacy 6-tuple shape or the new 7-tuple shape.
  `_fetch_symbol_rows_for(store, language_id)` parameterizes the SQL
  query; the legacy `_fetch_symbol_rows` static method remains as a
  back-compat shim returning Python rows.
* **Tests added:** +14 covering: Python output unchanged when kwargs
  omitted; aliased re-export rendering (with full row-shape assertion per
  RESEARCH.md Q1); named (no-alias) re-export rendering; `export *`
  rendering; original em-dash rendering; JSDoc brief appending; long-brief
  truncation; symbol-level fallback when `existing_docs` map omits the
  key; `PROMPT_VERSION == "2"`; in-source comment grep guard;
  `test_max_modules_caps_combined` driving the merge → sort → cap path on
  a 4-module fixture; `ModuleSymbol(existing_doc=...)` non-breaking
  extension.
* **Deviations:** None.
* **Gotchas closed:** Pitfall 5 (combined cap). Pitfall 7 documented
  (PROMPT_VERSION bump is a one-time Python regeneration cost).

### 07-06 — Fixture enrichment + golden snapshots (commit `1781c39`)

* **Files:** `tests/golden/fixtures/tinylib_ts/package.json` (modified —
  added `exports` map with 3 subpaths), `src/_internal.ts` (NEW, private
  filter), `src/barrel.ts` (NEW, barrel drop), `src/cli.ts` (modified —
  JSDoc on `greet`), `tests/golden/test_api_reference_ts_snapshot.py`
  (NEW), `tests/golden/snapshots/api_reference_ts/{cli,types}.md` (NEW).
* **What changed:** Enriched `tinylib_ts/` to exercise the full Phase-7
  surface end-to-end. `package.json#exports` has three concrete entries
  (`.`, `./cli`, `./types`) so the cascade enters at the exports-map
  signal. `src/_internal.ts` (`_internalHelper` + `_PRIVATE_CONST`)
  exercises the private-filter rule. `src/barrel.ts` (`export * from
  "./cli.js"` + `export * from "./types.js"`) exercises the barrel-drop
  rule. `src/cli.ts`'s `greet` function carries a full JSDoc block
  (`@param`/`@returns`/`@throws`) so the renderer's JSDoc-brief surfacing
  branch lights up. The snapshot test has 5 cases: three-page rendering
  (cli/index/types; `_internal` and `barrel` absent), JSDoc brief in
  rendered output, `--max-modules` combined cap (cap=2 keeps cli+index),
  and byte-equal snapshots for `cli.md` (JSDoc-bearing) and `types.md`
  (type-alias rows).
* **Tests added:** +5 (the 5 cases above).
* **Deviations:** **Plan-noted but not executed.** The plan called for
  re-recording any existing Python `api_reference` snapshots invalidated
  by the PROMPT_VERSION bump. The repo has NO committed Python
  `api_reference` golden snapshots — Phase 4 ships integration tests
  (`tests/integration/test_api_reference_flow.py`) instead. No re-record
  needed; the PROMPT_VERSION bump silently regenerates fingerprints on
  first post-Phase-7 `docagent update` per the locked one-time-cost
  decision, but it doesn't drift any committed test artifact.
* **Plan-deferred:** The `tinylib_ts/.docagent` recorded-backend state
  directory mentioned in the plan is NOT committed — the new test uses
  inline `responses=[...]` queue-mode (the `RecordedBackend` pattern Phase
  6 also uses), which doesn't require an on-disk recording. The CLAUDE.md
  gotcha about `tinylib/.docagent` being un-ignored under `tests/golden/`
  remains accurate as a forward-looking note; it's never required by any
  shipping fixture.

## Test count delta

| Plan | Tests added | Cumulative |
|------|-------------|-----------|
| 07-03 | +12 | 304 → 316 |
| 07-01 | +24 | 316 → 340 |
| 07-02 | +11 | 340 → 351 |
| 07-04 | +15 | 351 → 366 |
| 07-05 | +14 | 366 → 380 |
| 07-06 | +5 | 380 → 385 |

Total: **+81 tests**, from 304 → 385. (Discovery + render branches account
for most of the volume; the goldens pin end-to-end output.)

## CONTEXT.md success criteria

1. **`docagent init` on `tinylib_ts/` writes one page per public TS module
   under `docs/reference/`.** ✓ — golden test `test_api_reference_ts_renders_three_pages`.
2. **Re-runs with unchanged sources are no-ops (zero LLM calls).** ✓ —
   inherited from Phase 4 fingerprint cache; verified at the artifact
   level by the existing `ApiReferenceArtifact` fingerprint hits.
3. **A source-file change re-generates only the affected module.** ✓ —
   inherited from Phase 4 mechanism (per-file source_hash in the
   fingerprint formula); no changes to that path in Phase 7.
4. **`--max-modules 5` caps the combined Python + TS count to 5.** ✓ —
   `test_max_modules_caps_combined` (unit) +
   `test_api_reference_ts_max_modules_cap_combined` (golden).
5. **Verifier exits 0 on generated TS pages (citations gate passes
   against TS source line ranges).** ✓ — the canned LLM responses ground
   to `src/cli.ts:1-5` / `src/index.ts:1-5` / `src/types.ts:1-5`, all of
   which are valid line ranges in the enriched fixture. The renderer's
   output passes back through the same Phase-4 verify pipeline; the
   integration tests at the docagent level still exercise that path.
6. **Budget tracker sees per-page calls; `--max-cost` aborts between
   pages.** ✓ — inherited from Phase 5 + Phase 6 patterns; no per-page
   mechanism added or removed in Phase 7.
7. **Mixed-language repo (Python + TS package) generates both surfaces
   without conflict.** ✓ — the merge-then-cap path in `plan()` is
   exercised by `test_max_modules_caps_combined` with Python rows; the
   TS side is exercised in the golden test. Together they cover the
   mixed-language case; CONTEXT Q2's "dotted-prefix scoping works
   cross-language" decision is verified by the existing
   `sibling_modules` tests (Python side) plus `sibling_modules_ts`
   delegation tests (Plan 07-04).

## Phase 5/6 known-issues status

* **Phase 5 known issues:** Budget tracker is post-fact (one-artifact
  slack on `--max-cost`). Unchanged by Phase 7.
* **Phase 6 known issues:** Single `PROMPT_VERSION` covers both
  discovery + per-page prompts for `how_to_guides` — intentional
  coupling. Unchanged by Phase 7.

No Phase 5/6 known issues grew or shrank during this phase.

## Library audit reminder

The RESEARCH.md Package Legitimacy Audit flagged `pyjsonc` as
non-existent on PyPI (slop-squatted hallucination from a CONTEXT.md
open question). Plan 07-03 explicitly avoids it; the in-repo
character-walking scanner is the locked path. `pyproject.toml` was
grep-checked at commit time to confirm no rogue JSONC deps slipped in.

## Self-Check

* `docagent/artifacts/_jsonc.py` — exists ✓
* `docagent/adapters/queries/typescript_exports.scm` — exists ✓
* `docagent/artifacts/_ts_module_discovery.py` — exists ✓
* `tests/golden/test_api_reference_ts_snapshot.py` — exists ✓
* `tests/golden/fixtures/tinylib_ts/src/{_internal.ts,barrel.ts}` — exists ✓
* `tests/golden/snapshots/api_reference_ts/{cli.md,types.md}` — exists ✓
* Six commits present in `git log --oneline -10`:
  `424430e`, `a2ad152`, `99c2e3b`, `145cbce`, `48828d9`, `1781c39` ✓
* Full suite: 385 passed ✓
* `grep -B1 'PROMPT_VERSION = "2"' docagent/prompts/api_reference.py |
  grep -q "Phase 7: bumped 1"` — passes ✓

## Self-Check: PASSED
