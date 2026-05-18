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
| `write_rate` | `len(artifacts_written ∩ expected) / len(expected)` from `run.json` | **First-class metric.** DocAgent's verifier is a moat that gate-fails bad LLM output. On stripped third-party repos the write rate is uncomfortably variable (tinydb: 0/4 root files on one run, 3/4 on another, same SHA). Coverage-vs-correctness tradeoff is real and needs to be reported alongside any quality score. |
| `factscore` | LLM judge (`prompts/factual_divergence.md`) | FActScore (Min et al. EMNLP 2023): atomic-claim decomposition, fraction supported by source. `supported_count / total_claims`. |
| `claims_per_1000_tokens` | derived in `score.py` | Length normalization. Pair with raw `total_claims` so a terse doc can't silently win on divergence count. |
| `completeness` (0–5) | LLM judge (`prompts/rubric_completeness.md`) | 3-axis rubric from Yang et al. ACL Demo 2025. How much public API + external-facing surface is mentioned, regardless of correctness. |
| `helpfulness` (0–5) | LLM judge (`prompts/rubric_helpfulness.md`) | Can a competent developer get a first example running from the doc alone? |
| `truthfulness` (0–5) | LLM judge (`prompts/rubric_truthfulness.md`) | Rolled-up axis score built on the FActScore JSON. Bucket boundaries are FActScore-anchored. |
| `inter_judge_axis_disagreement` | derived in `score.py` | Max gap across `--judge-model` panel. Cross-family judge required before publication (KNOWN-GAPS.md §2). |
| `verifier_pass` | `docagent verify` exit code | Gate, not quality. Confirms citation line ranges resolve; says nothing about whether the span supports the claim. See KNOWN-GAPS.md §3. |
| `topic_coverage_jaccard` | LLM judge (`prompts/topic_coverage.md`) | Did DocAgent miss things humans considered essential? |
| `divergence_resolution` | LLM judge + source code check (`prompts/divergence_resolution.md`) | For contradicted FActScore claims: DocAgent / original / both-wrong / unverifiable. |
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
- `run.json` — RunRecord (init/verify exit codes, write_rate, cost,
  timeout notes)
- `metrics.json` (or `metrics.identity.json` / `metrics.empty.json`
  in baseline mode) — RepoMetrics: per-judge passes with FActScore,
  topic coverage, 3-axis rubric (completeness, helpfulness,
  truthfulness), divergence resolution bucket, judge cost, and the
  inter-judge axis disagreement summary
- `claims.<judge_or_baseline>.jsonl` — per-claim FActScore verdicts
  (supported / unsupported / contradicted) with citations

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
