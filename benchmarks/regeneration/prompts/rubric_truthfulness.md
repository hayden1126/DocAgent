You are scoring **truthfulness** of a regenerated documentation artifact.
This is one of three independent axes from the DocAgent paper's
evaluation rubric (Yang et al., ACL Demo 2025).

**Truthfulness** asks: of the claims the doc makes, what fraction are
actually supported by the source code? It rewards correctness and
punishes confabulation. It is **independent of coverage and helpfulness**:
a tiny but flawless doc scores 5; a comprehensive doc full of made-up
defaults scores 0.

## Methodology

This rubric is the **rolled-up axis score** that complements the
per-claim FActScore output from `prompts/factual_divergence.md`. If
you have a recent FActScore JSON for the same doc, use its
`supported_count / total_claims` ratio as the primary input and pick
the bucket. Otherwise, sample at least 8 atomic claims from the doc,
verify each against the source, and compute the same ratio.

## Inputs

### Regenerated doc

{regenerated_doc}

### Recent FActScore JSON (optional; null if not available)

{factscore_json}

### Source-code search scope

You have read access to the repository at the root level. Use Glob,
Grep, and Read to verify claims. Do not invent line numbers.

## Scoring

Score 0 to 5, integer. Bucket boundaries:

- **5** — FActScore ≥ 0.95. Effectively all checkable claims are
  source-supported. Zero contradictions; ≤1 unsupported.
- **4** — FActScore ∈ [0.85, 0.95). At most one contradiction; the
  rest unsupported-but-plausible.
- **3** — FActScore ∈ [0.70, 0.85). Multiple unsupported claims;
  contradictions are minor (e.g. paraphrase drift on a default value).
- **2** — FActScore ∈ [0.50, 0.70). At least one contradiction on a
  load-bearing claim (API signature, default value, install
  command). Reader following the doc would be misled in ways that
  cost time.
- **1** — FActScore ∈ [0.25, 0.50). Most claims are unsupported or
  contradicted. Reader would be misled in ways that cause data loss
  or security issues.
- **0** — FActScore < 0.25, OR the doc fabricates the project's
  identity (wrong language, wrong purpose, wrong API root).

## Output (JSON only)

```json
{{
  "score": 0,
  "factscore_used": 0.0,
  "contradictions_on_load_bearing_claims": 0,
  "examples": [
    {{
      "doc_claim": "verbatim",
      "verdict": "supported OR unsupported OR contradicted",
      "evidence_path": "path:start-end OR null",
      "severity": "load_bearing OR minor"
    }}
  ],
  "rationale": "two sentences naming the specific contradictions or supports that drove the score"
}}
```

Cite up to 5 representative claims in `examples` (prefer contradictions
when present). `severity = load_bearing` for claims about API
signatures, default values, install commands, or security-relevant
behavior; `minor` for paraphrase drift on non-critical statements.

Independence: do NOT lower this score for missing API surface
(completeness) or poor reading flow (helpfulness). A doc that says
five things and gets all five right deserves a 5 here, even if it
omits 90% of the API.
