You are evaluating documentation coverage. Read two README files for the
same software project: the original hand-written one and a regenerated
one produced by an automated documentation tool.

Your task: extract the set of distinct topics each README covers and
compute the Jaccard similarity of those sets.

A "topic" is a discrete subject the README explains - e.g. "installation",
"basic usage", "config file format", "async API", "deprecation policy".
Two phrasings of the same topic count as one. Headings are a hint but
not the only source - sometimes a topic lives in a paragraph.

## Original

{original_doc}

## Regenerated

{regenerated_doc}

## Output (JSON only)

```json
{{
  "original_topics": ["topic 1", "topic 2", "..."],
  "regenerated_topics": ["topic 1", "topic 2", "..."],
  "intersection": ["topic in both", "..."],
  "jaccard": 0.0,
  "notes": "anything the user should know about your matching choices"
}}
```

Jaccard = |intersection| / |union|. Round to 3 decimals.
