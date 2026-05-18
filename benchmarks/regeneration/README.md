# Regeneration benchmark

Strip a repo's external-facing docs, regenerate them with DocAgent, then
compare the regenerated docs against the originals using **the source
code as arbiter** — not the originals themselves.

## Why this design

Hand-written docs are not ground truth. They are stylistically
idiosyncratic, often partially stale, and frequently omit things the
author considered obvious. Scoring DocAgent on *similarity* to the
original measures prose style (BLEU theater), not accuracy.

The reframe: when DocAgent and the human-written doc disagree, **check
the code**. DocAgent's `<!-- ground: -->` citations make its claims
auditable; hand-written docs are not. The headline metric is the
fraction of disagreements where DocAgent is correct per the source.

## Metrics

| Metric | Source | What it tells you |
|---|---|---|
| `write_rate` | `len(artifacts_written) / artifacts_expected` from `run.json` | **First-class metric.** DocAgent's verifier is a moat that gate-fails bad LLM output. On stripped third-party repos the write rate is uncomfortably variable (tinydb: 0/4 root files on one run, 3/4 on another, same SHA). Coverage-vs-correctness tradeoff is real and needs to be reported alongside any quality score. |
| `verifier_pass` | `docagent verify` exit code | Gate, not quality. Confirms citation line ranges resolve; says nothing about whether the span supports the claim. See KNOWN-GAPS.md §3. |
| `topic_coverage_jaccard` | LLM judge (`prompts/topic_coverage.md`) | Did DocAgent miss things humans considered essential? |
| `factual_divergence_rate` | LLM judge (`prompts/factual_divergence.md`) | How often do the two docs disagree on the same subject |
| `divergence_resolution` | LLM judge + source code check (`prompts/divergence_resolution.md`) | **The killer chart.** For each disagreement: DocAgent / original / both-wrong |
| `unique_facts_docagent` | LLM judge (`prompts/unique_facts.md`) | Facts DocAgent surfaced that original missed |
| `cost_usd`, `wall_seconds` | `docagent init` telemetry | Free; already emitted |

## What gets stripped

Only **external-facing** docs:
- `README.md`, `README.rst`
- `AGENTS.md`, `CLAUDE.md`
- `llms.txt`, `llms-full.txt`
- `docs/` directory (if it's prose docs, not auto-generated API ref)

Inline docstrings and code comments are **kept** — DocAgent is allowed
to use them as source signal (same as a human would). Removing them
would make the comparison circular and unfair.

## Corpus selection

Repos must:
- Have substantial hand-written docs (skip skeletal READMEs that inflate
  win rate)
- Fit comfortably in a 200k-context window (skip megaprojects)
- Not appear in DocAgent's golden fixtures (filter out anything
  resembling `tests/golden/fixtures/tinylib/`)

See `corpus.yaml` for the pinned list. Each entry includes a commit SHA
so runs are reproducible even after upstream changes.

## Running

```bash
# 1. Clone + strip + regenerate (deterministic, needs API key for chosen backend)
python -m benchmarks.regeneration.run --backend anthropic --max-cost 5.00

# 2. Score regenerated docs against originals (needs judge LLM key)
python -m benchmarks.regeneration.score --judge-model claude-opus-4-7

# 3. Aggregate
python -m benchmarks.regeneration.score --aggregate
```

Outputs land in `results/<repo>-<sha>/`:
- `original/` — preserved copies of the stripped docs
- `regenerated/` — DocAgent output
- `metrics.json` — per-repo scores
- `divergences.jsonl` — one row per detected disagreement with resolution

## Status

**Scaffold only.** `run.py` is wired through to `docagent init`; `score.py`
contains prompt templates and a judge harness skeleton with the actual
LLM calls marked as TODO. Wire to `docagent.backends.litellm_backend`
when ready to spend tokens on a full eval pass.

## Known limitations (call out in any writeup)

- LLM judges need >=2 raters + kappa for inter-rater reliability before any
  number is publishable. Single-judge scores are directional only.
- Corpus is biased toward Python + small TS libs. Don't generalize to
  Java/Go/Rust without expanding it.
- "Divergence resolution" judge is itself an LLM and can be wrong;
  surface its reasoning + the cited span so a human can audit a sample.
