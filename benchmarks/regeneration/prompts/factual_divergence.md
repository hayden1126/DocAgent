You are detecting factual disagreements between two READMEs that describe
the same software project. One is hand-written; the other is regenerated
by an automated tool.

A "divergence" is a pair of claims that:
  1. Are about the same subject (same API, same config flag, same
     installation step, same default behavior, etc.), AND
  2. Disagree on a checkable fact (different default value, different
     supported version, different argument name, different return type,
     different file path).

Stylistic differences, ordering, and missing-topic-on-one-side do NOT
count as divergences. Vague-vs-specific is not a divergence unless they
genuinely conflict.

Where the regenerated doc has a `<!-- ground: path:start-end -->`
citation attached to its claim, extract it.

## Original

{original_doc}

## Regenerated

{regenerated_doc}

## Output (JSON only)

```json
{{
  "divergences": [
    {{
      "subject": "what API/flag/behavior this is about",
      "original_claim": "verbatim claim from the original",
      "docagent_claim": "verbatim claim from the regenerated doc",
      "docagent_citation": "path:start-end OR null",
      "resolution": "unresolved",
      "reasoning": ""
    }}
  ]
}}
```

Leave `resolution` and `reasoning` empty - they're filled in by a later
pass that checks the source. Be conservative: if you're not sure two
claims actually disagree, don't list them.
