---
docagent_artifact: api_reference
module: benchmarks.regeneration.run
generated_by: docagent
---

# `benchmarks.regeneration.run`


`benchmarks.regeneration.run` is the clone-strip-regenerate driver for the regeneration benchmark: for each repo in `corpus.yaml` it shallow-clones at a pinned SHA, moves external-facing docs into an `original/` archive, invokes `docagent init` and `docagent verify`, and writes a per-repo `run.json` plus an aggregate `run-summary.json`. `RepoSpec` models one corpus entry and is produced by `load_corpus`; `shallow_clone` and `strip_docs` prepare the working tree; `run_docagent_init`/`run_docagent_verify` shell out to the CLI and `copy_regenerated` snapshots the output; `run_one` stitches those steps into a single `RunRecord`, and `main` is the argparse entry point that fans `run_one` across the corpus. <!-- ground: benchmarks/regeneration/run.py:1-14 --> <!-- ground: benchmarks/regeneration/run.py:226-272 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `RepoSpec` | class | `RepoSpec` |
| `RunRecord` | class | `RunRecord` |
| `load_corpus` | function | `load_corpus` |
| `shallow_clone` | function | `shallow_clone` |
| `strip_docs` | function | `strip_docs` |
| `run_docagent_init` | function | `run_docagent_init` |
| `run_docagent_verify` | function | `run_docagent_verify` |
| `copy_regenerated` | function | `copy_regenerated` |
| `run_one` | function | `run_one` |
| `main` | function | `main` |

## Common workflows

Load the pinned corpus and run the full pipeline against a single repo, capturing the resulting `RunRecord`:

```python
from pathlib import Path
from benchmarks.regeneration.run import CORPUS, load_corpus, run_one

corpus = load_corpus(CORPUS)
spec = next(s for s in corpus if s.name == "tinydb")
record = run_one(spec, backend="agent_sdk", max_cost=5.0, timeout_seconds=1800.0)
print(record.write_rate, record.cost_usd, record.wall_seconds)
```
<!-- ground: benchmarks/regeneration/run.py:226-272 -->

Use the lower-level helpers directly to clone and strip an arbitrary repo without invoking `docagent`:

```python
from pathlib import Path
from benchmarks.regeneration.run import RepoSpec, shallow_clone, strip_docs

spec = RepoSpec(name="demo", language="python",
                url="https://github.com/example/demo.git", sha=None)
clone_dir = Path("clones/demo")
sha = shallow_clone(spec, clone_dir)
moved = strip_docs(clone_dir, Path(f"results/demo-{sha[:12]}/original"))
print("archived:", moved)  # e.g. ['README.md', 'docs/ (skipped:sphinx)']
```
<!-- ground: benchmarks/regeneration/run.py:84-146 -->

Drive the script from the command line — `main` accepts `--only` to filter the corpus and `--timeout-seconds` to bound each `docagent` invocation:

```bash
python -m benchmarks.regeneration.run \
    --backend agent_sdk \
    --max-cost 5.0 \
    --only tinydb \
    --timeout-seconds 1800
```
<!-- ground: benchmarks/regeneration/run.py:275-315 -->

## See also

- [`benchmarks.regeneration.score`](benchmarks.regeneration.score.md)

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
