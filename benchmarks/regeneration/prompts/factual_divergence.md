You are auditing the factual grounding of a regenerated documentation
artifact against the source code. The methodology is FActScore (Min
et al., EMNLP 2023): break the doc into atomic claims, then mark each
one as supported / unsupported / contradicted against the source.

## Atomic claim

An atomic claim is a single, independently checkable factual statement
about the project. Each claim has:
- A subject (a specific API, flag, file path, version, default value,
  install step, return type, behavior).
- A predicate (what the doc asserts about the subject).

Compound sentences split into multiple atomic claims. Examples:
- "TinyDB stores data in JSON and supports custom storages" →
  2 claims: (a) "stores data in JSON", (b) "supports custom storages".
- "Install with `pip install tinydb`" → 1 claim: "the install command
  is `pip install tinydb`".
- "Lightweight, document-oriented database" → 2 claims if both
  "lightweight" and "document-oriented" are independently checkable
  in the source (rarely true; "lightweight" is usually marketing and
  should be excluded as not checkable).

Skip prose that is **not independently checkable from the source**:
marketing adjectives ("powerful", "easy"), audience framing ("for
beginners"), tutorial scaffolding ("first, let's..."), and any claim
whose subject is the project's reputation rather than its behavior.

## Verdict per claim

For each atomic claim in the regenerated doc:

- **`supported`** — the source code (including docstrings, type
  hints, configuration files, tests) contains evidence consistent
  with the claim. Cite the supporting span by relative path and line
  range. If the doc already has a `<!-- ground: path:start-end -->`
  citation, use that citation's contents as your starting point but
  verify it actually supports the claim — citations are LLM-emitted
  and not always faithful.
- **`unsupported`** — no evidence in the source either way. The claim
  may be true but cannot be verified from the code.
- **`contradicted`** — the source contains evidence that disagrees
  with the claim (different default, different argument name,
  different return type, etc.).

## Inputs

### Regenerated doc

{regenerated_doc}

### Source-code search scope

You have read access to the repository at the root level. Use Read /
Glob / Grep to verify each claim. Do not invent line numbers.

## Output (JSON only)

```json
{{
  "claims": [
    {{
      "id": "c1",
      "text": "the atomic claim, paraphrased crisply",
      "doc_excerpt": "the verbatim phrase from the regenerated doc",
      "doc_citation": "path:start-end OR null (if the doc carried one)",
      "verdict": "supported OR unsupported OR contradicted",
      "evidence_path": "path:start-end OR null",
      "reasoning": "one sentence pointing at the specific evidence"
    }}
  ],
  "supported_count": 0,
  "unsupported_count": 0,
  "contradicted_count": 0,
  "total_claims": 0,
  "factscore": 0.0
}}
```

`factscore = supported_count / total_claims` (3 decimals). This is the
FActScore metric: fraction of atomic claims with source support.

Be strict but charitable: if the source plausibly backs a claim even
if not explicit, mark `supported` with reasoning that names the
specific evidence. If you can't find evidence, prefer `unsupported`
over `contradicted` — the absence of evidence is not evidence of
absence.
