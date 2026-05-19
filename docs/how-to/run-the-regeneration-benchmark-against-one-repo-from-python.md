---
title: "Run the regeneration benchmark against one repo from Python"
slug: run-the-regeneration-benchmark-against-one-repo-from-python
docagent_artifact: how_to_guides
---

# Run the regeneration benchmark against one repo from Python

## Goal
Execute the regeneration benchmark on a single corpus repository from a Python script and read back its write rate, cost, and wall-clock time without touching the CLI. <!-- ground: docs/reference/benchmarks.regeneration.run.md:30-40 -->

## Steps
1. Import `CORPUS`, `load_corpus`, and `run_one` from `benchmarks.regeneration.run`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:31-33 -->
2. Load the corpus specs by calling `load_corpus(CORPUS)`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:35-35 -->
3. Select the spec for the repo you want — for example, pick the `tinydb` entry from the loaded list. <!-- ground: docs/reference/benchmarks.regeneration.run.md:36-36 -->
4. Invoke `run_one(spec, backend="agent_sdk", max_cost=5.0, timeout_seconds=1800.0)` to execute the benchmark and capture the returned record. <!-- ground: docs/reference/benchmarks.regeneration.run.md:37-37 -->
5. Inspect `record.write_rate`, `record.cost_usd`, and `record.wall_seconds` on the returned object. <!-- ground: docs/reference/benchmarks.regeneration.run.md:38-38 -->

## Verify
Print the three fields from the record — `record.write_rate`, `record.cost_usd`, and `record.wall_seconds` — to confirm the run produced a populated result. <!-- ground: docs/reference/benchmarks.regeneration.run.md:38-38 -->

## See also

- [benchmarks.regeneration.run](../reference/benchmarks.regeneration.run.md)
- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
- [enable-debug-logging-for-docagent](./enable-debug-logging-for-docagent.md)
- [extract-python-symbols-with-pythonadapter](./extract-python-symbols-with-pythonadapter.md)
- [generate-all-artifacts-with-docagent-init](./generate-all-artifacts-with-docagent-init.md)
- [install-docagent-with-multi-provider-extras](./install-docagent-with-multi-provider-extras.md)
- [re-verify-on-disk-artifacts-with-docagent-verify](./re-verify-on-disk-artifacts-with-docagent-verify.md)
- [restrict-a-run-to-a-single-artifact-with-only](./restrict-a-run-to-a-single-artifact-with-only.md)
- [run-an-identity-baseline-to-measure-judge-noise-floor](./run-an-identity-baseline-to-measure-judge-noise-floor.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
