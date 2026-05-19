---
docagent_artifact: api_reference
module: benchmarks.regeneration.score
generated_by: docagent
---

# `benchmarks.regeneration.score`


This module is the scoring phase of the regeneration benchmark: for each `results/<name>-<sha>/` directory written by `run.py`, it invokes LLM judges over the (original, regenerated) README pair and emits `metrics.json`, `claims.jsonl`, and `divergences.jsonl`. The dataclasses `Claim`, `Divergence`, `AxisScore`, `JudgePassMetrics`, and `RepoMetrics` are the on-disk schema; the `score_*` functions each implement one judge pass (FActScore decomposition, topic-coverage Jaccard, three-axis rubric, and per-divergence resolution) on top of `call_judge` / `load_prompt`, while `score_one` orchestrates a single repo-and-judge pass, `aggregate` rolls all `metrics.json` files into `results/aggregate.json`, and `main` is the argparse entry point that fans pass invocations out across `--judge-model` and optional `--baseline` modes. <!-- ground: benchmarks/regeneration/score.py:1-29 --> <!-- ground: benchmarks/regeneration/score.py:51-105 --> <!-- ground: benchmarks/regeneration/score.py:366-568 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `Claim` | class | `Claim` |
| `Divergence` | class | `Divergence` |
| `AxisScore` | class | `AxisScore` |
| `JudgePassMetrics` | class | `JudgePassMetrics` |
| `RepoMetrics` | class | `RepoMetrics` |
| `call_judge` | function | `call_judge` |
| `load_prompt` | function | `load_prompt` |
| `score_factscore` | function | `score_factscore` |
| `score_topic_coverage` | function | `score_topic_coverage` |
| `resolve_divergence` | function | `resolve_divergence` |
| `score_completeness` | function | `score_completeness` |
| `score_helpfulness` | function | `score_helpfulness` |
| `score_truthfulness` | function | `score_truthfulness` |
| `score_one` | function | `score_one` |
| `aggregate` | function | `aggregate` |
| `main` | function | `main` |

## Common workflows

Score a single repo result directory with a single judge model and inspect the resulting metrics:

```python
from pathlib import Path
from benchmarks.regeneration.score import score_one

metrics = score_one(
    result_dir=Path("benchmarks/regeneration/results/tinydb-abc1234"),
    judge_model="anthropic/claude-opus-4-7",
    repo_root=Path("benchmarks/regeneration/clones/tinydb"),
)
print(metrics.factscore, metrics.topic_coverage_jaccard, metrics.judge_cost_usd)
```
<!-- ground: benchmarks/regeneration/score.py:366-459 -->

Run a calibration baseline (identity = original vs. original; empty = "" vs. original) instead of a regen comparison, matching the CLI's `--baseline` flag:

```python
from pathlib import Path
from benchmarks.regeneration.score import score_one

noise_floor = score_one(
    result_dir=Path("benchmarks/regeneration/results/tinydb-abc1234"),
    judge_model="anthropic/claude-opus-4-7",
    repo_root=Path("benchmarks/regeneration/clones/tinydb"),
    baseline="identity",
)
for note in noise_floor.notes:
    print(note)
```
<!-- ground: benchmarks/regeneration/score.py:340-361 --> <!-- ground: benchmarks/regeneration/score.py:374-382 -->

Call a single judge metric directly — useful when iterating on prompts — and then roll all `metrics.json` files in `results/` into `aggregate.json`:

```python
from benchmarks.regeneration.score import score_topic_coverage, aggregate

jaccard, cost_usd, err = score_topic_coverage(
    original=open("results/tinydb-abc1234/original/README.md").read(),
    regenerated=open("results/tinydb-abc1234/regenerated/README.md").read(),
    model="anthropic/claude-opus-4-7",
)
print(jaccard, cost_usd, err)

aggregate()  # writes benchmarks/regeneration/results/aggregate.json
```
<!-- ground: benchmarks/regeneration/score.py:257-269 --> <!-- ground: benchmarks/regeneration/score.py:481-490 -->

## See also

- [`benchmarks.regeneration.run`](benchmarks.regeneration.run.md)

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
