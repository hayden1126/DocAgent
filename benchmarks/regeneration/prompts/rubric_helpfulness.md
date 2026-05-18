You are scoring **helpfulness** of a regenerated documentation artifact.
This is one of three independent axes from the DocAgent paper's
evaluation rubric (Yang et al., ACL Demo 2025).

**Helpfulness** asks: does this doc actually let a competent reader
accomplish their goal — install the thing, write their first call,
diagnose a typical error, configure for production — without leaving
the doc to consult source code or external sources? It measures
**utility to a reader**, not coverage and not correctness.

## What helpfulness looks like

A helpful doc:
- Sequences information from "what is this" → "how do I try it" →
  "how do I use the common features" → "how do I configure for my
  case" → "where to look next." A high-coverage doc that jumps
  straight into class signatures with no quickstart is unhelpful.
- Uses copy-pasteable code blocks with language hints and realistic
  values. Pseudocode and `<placeholder>` snippets score lower.
- Anticipates the next question. ("Note: by default this writes to
  the current directory; pass `path=` to override.") A doc that
  states facts but never explains *why* a reader might care is
  shallow.
- Surfaces failure modes proactively. ("If you see `ImportError:
  cannot import name X`, you're on the v1 release line — see Migration.")
- Uses consistent terminology throughout. Switching between
  "extension", "plugin", "addon" for the same concept costs the
  reader.

## What does NOT count

- Factual accuracy (that's truthfulness).
- Surface coverage (that's completeness).
- Prose elegance for its own sake. Crisp imperative beats flowing
  prose for technical docs.
- Marketing punch. A "fun" tone with poor instructions is unhelpful.

## Inputs

### Regenerated doc

{regenerated_doc}

### Reader persona

Imagine a working developer (3-5 years experience) opening this
project for the first time. They are competent in the project's
language but new to the project itself. They need to be productive
within 15 minutes.

## Scoring

Score 0 to 5, integer:

- **5** — A reader following the doc top-to-bottom can install,
  successfully run a first example, and configure for a common
  non-trivial case without leaving the doc. Common failure modes
  documented near where they bite.
- **4** — Productive within 15 minutes; install + first-example
  flow is clear. Configuration for non-trivial cases requires
  some inference. No major terminological churn.
- **3** — Install + a first example work, but the doc reads as a
  reference rather than a guide. Reader will need to consult source
  or external resources to do anything beyond the canonical example.
- **2** — First example is partial, broken in obvious ways, or
  requires undocumented prereqs. Multiple terminological collisions.
- **1** — Reader cannot get a first example running from the doc.
- **0** — Doc provides no operational guidance.

## Output (JSON only)

```json
{{
  "score": 0,
  "first_example_runnable": false,
  "failure_modes_documented": false,
  "terminology_consistent": false,
  "next_question_anticipation": false,
  "rationale": "two sentences naming the specific reader-experience friction or wins"
}}
```

Independence: do NOT lower for factual errors (truthfulness) or
missing API surface (completeness). A small, focused, helpful doc
is allowed to score 5 here even if it's incomplete.
