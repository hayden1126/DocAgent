Two documents disagree on the same factual claim. You have an excerpt of
the source code that DocAgent cited when making its claim. Your job is
to decide which side the source supports.

## Original claim

{original_claim}

## DocAgent claim

{docagent_claim}

## Source excerpt (what DocAgent's `<!-- ground -->` citation points at)

```
{source_excerpt}
```

## Output (JSON only)

```json
{{
  "resolution": "docagent OR original OR both_wrong OR unverifiable",
  "reasoning": "one or two sentences pointing at the specific line(s) in the excerpt"
}}
```

Resolution rules:
- `"docagent"` - the source supports DocAgent's claim and contradicts the original.
- `"original"` - the source supports the original claim and contradicts DocAgent's. (This includes cases where DocAgent cited a span that doesn't actually back its claim.)
- `"both_wrong"` - the source supports neither.
- `"unverifiable"` - the excerpt is missing, empty, or doesn't address the disputed fact. Use this when you genuinely cannot tell from what you have. Do NOT use it as a default - prefer a concrete verdict whenever the excerpt gives you one.
