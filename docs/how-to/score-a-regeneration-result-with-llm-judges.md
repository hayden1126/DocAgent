---
title: "Score a regeneration result with LLM judges"
slug: score-a-regeneration-result-with-llm-judges
docagent_artifact: how_to_guides
---

# Score a regeneration result with LLM judges

## Goal
Run an LLM-judge pass over a single regeneration result directory and read back the factscore, topic-coverage Jaccard, and judge cost for that run. <!-- ground: docs/reference/benchmarks.regeneration.score.md:35-46 -->

## Steps
1. Import `score_one` and `Path` in your Python session. <!-- ground: docs/reference/benchmarks.regeneration.score.md:38-39 -->
2. Call `score_one` with `result_dir` pointing at the regeneration output directory for the repo you want to score. <!-- ground: docs/reference/benchmarks.regeneration.score.md:41-42 -->
3. Pass `judge_model` set to the model identifier you want the judges to run under (e.g. `"anthropic/claude-opus-4-7"`). <!-- ground: docs/reference/benchmarks.regeneration.score.md:43-43 -->
4. Pass `repo_root` pointing at the cloned source tree the result was generated against. <!-- ground: docs/reference/benchmarks.regeneration.score.md:44-44 -->
5. Print `metrics.factscore`, `metrics.topic_coverage_jaccard`, and `metrics.judge_cost_usd` from the returned object. <!-- ground: docs/reference/benchmarks.regeneration.score.md:46-46 -->

## Verify
Confirm the call returned a metrics object whose `factscore`, `topic_coverage_jaccard`, and `judge_cost_usd` attributes print without error. <!-- ground: docs/reference/benchmarks.regeneration.score.md:46-46 -->

## See also

- [benchmarks.regeneration.score](../reference/benchmarks.regeneration.score.md)
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
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
