---
title: "Run the regeneration benchmark from the CLI"
slug: run-the-regeneration-benchmark-from-the-cli
docagent_artifact: how_to_guides
---

# Run the regeneration benchmark from the CLI

## Goal
Drive the regeneration benchmark script from your shell to regenerate documentation for one or more corpus entries under a bounded cost and timeout, using a chosen backend. <!-- ground: docs/reference/benchmarks.regeneration.run.md:57-65 -->

## Steps
1. Invoke the benchmark as a module with `python -m benchmarks.regeneration.run`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:60-60 -->
2. Pass `--backend agent_sdk` to select the backend used for each `docagent` invocation. <!-- ground: docs/reference/benchmarks.regeneration.run.md:61-61 -->
3. Cap spend by adding `--max-cost 5.0`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:62-62 -->
4. Filter the corpus to a single entry with `--only tinydb`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:63-63 -->
5. Bound each `docagent` invocation with `--timeout-seconds 1800`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:64-64 -->

## Verify
Run the full command and confirm it completes without exceeding the configured cost or per-invocation timeout:

```bash
python -m benchmarks.regeneration.run \
    --backend agent_sdk \
    --max-cost 5.0 \
    --only tinydb \
    --timeout-seconds 1800
```
<!-- ground: docs/reference/benchmarks.regeneration.run.md:59-65 -->

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
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
