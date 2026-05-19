---
title: "Aggregate per-repo metrics into aggregate.json"
slug: aggregate-per-repo-metrics-into-aggregate-json
docagent_artifact: how_to_guides
---

# Aggregate per-repo metrics into aggregate.json

## Goal
Roll up every per-repo `metrics.json` under `results/` into a single `benchmarks/regeneration/results/aggregate.json` summary you can analyze. <!-- ground: docs/reference/benchmarks.regeneration.score.md:67-79 -->

## Steps
1. Import `aggregate` from `benchmarks.regeneration.score`. <!-- ground: docs/reference/benchmarks.regeneration.score.md:70-70 -->
2. Call `aggregate()` with no arguments to roll every `metrics.json` in `results/` into `aggregate.json`. <!-- ground: docs/reference/benchmarks.regeneration.score.md:67-79 -->

## Verify
Confirm the file was written by checking that `benchmarks/regeneration/results/aggregate.json` now exists. <!-- ground: docs/reference/benchmarks.regeneration.score.md:79-79 -->

## See also

- [benchmarks.regeneration.score](../reference/benchmarks.regeneration.score.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
- [enable-debug-logging-for-docagent](./enable-debug-logging-for-docagent.md)
- [extract-python-symbols-with-pythonadapter](./extract-python-symbols-with-pythonadapter.md)
- [generate-all-artifacts-with-docagent-init](./generate-all-artifacts-with-docagent-init.md)
- [install-docagent-with-multi-provider-extras](./install-docagent-with-multi-provider-extras.md)
- [re-verify-on-disk-artifacts-with-docagent-verify](./re-verify-on-disk-artifacts-with-docagent-verify.md)
- [restrict-a-run-to-a-single-artifact-with-only](./restrict-a-run-to-a-single-artifact-with-only.md)
- [run-an-identity-baseline-to-measure-judge-noise-floor](./run-an-identity-baseline-to-measure-judge-noise-floor.md)
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
