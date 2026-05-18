Compare two READMEs for the same project. Count the substantive,
checkable facts that appear in one but not the other.

A "fact" is a discrete claim about behavior, configuration, default
values, file paths, supported versions, or required dependencies.
Marketing prose, headers, and structural framing don't count.

## Original

{original_doc}

## Regenerated

{regenerated_doc}

## Output (JSON only)

```json
{{
  "unique_to_original": 0,
  "unique_to_docagent": 0,
  "examples_unique_to_original": ["short fact", "..."],
  "examples_unique_to_docagent": ["short fact", "..."],
  "notes": "any caveats about close-but-not-identical pairs you decided to count as shared"
}}
```

Cap examples at 5 per side. Counts cover the full set, not just the
examples.
