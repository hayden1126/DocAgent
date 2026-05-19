---
title: "Run an identity baseline to measure judge noise floor"
slug: run-an-identity-baseline-to-measure-judge-noise-floor
docagent_artifact: how_to_guides
---

# Run an identity baseline to measure judge noise floor

## Goal
Establish the judge noise floor for a regeneration result by scoring the original documentation against itself, so you can interpret real regen metrics relative to a calibrated baseline. <!-- ground: docs/reference/benchmarks.regeneration.score.md:50-65 -->

## Steps
1. Import `score_one` from `benchmarks.regeneration.score` and `Path` from `pathlib`. <!-- ground: docs/reference/benchmarks.regeneration.score.md:53-54 -->
2. Call `score_one` with `result_dir` pointing at the run's results directory, `judge_model` set to the judge you want to calibrate, `repo_root` pointing at the cloned repo, and `baseline="identity"` to compare original against original. <!-- ground: docs/reference/benchmarks.regeneration.score.md:56-61 -->
3. Iterate `noise_floor.notes` and print each entry to surface the baseline annotations the scorer attached to this run. <!-- ground: docs/reference/benchmarks.regeneration.score.md:62-63 -->

## Verify
Confirm the notes stream printed in step 3 includes the identity-baseline annotations emitted by the scorer; this matches the CLI's `--baseline` flag behavior. <!-- ground: docs/reference/benchmarks.regeneration.score.md:50-65 -->

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
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
