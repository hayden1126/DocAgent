---
title: "Re-verify on-disk artifacts with docagent verify"
slug: re-verify-on-disk-artifacts-with-docagent-verify
docagent_artifact: how_to_guides
---

# Re-verify on-disk artifacts with docagent verify

## Goal
Re-run DocAgent's deterministic-first verifier against the artifacts already written to disk, without regenerating them, so you can confirm they still pass the gate pipeline. <!-- ground: README.md:58-59 -->

## Steps
1. Ensure the `docagent` console entry point is available on your PATH after installation. <!-- ground: README.md:49-49 -->
2. From the repository root, run `docagent verify` to invoke the verifier against the artifacts on disk. <!-- ground: README.md:58-59 -->

## Verify
Running `docagent verify` exercises the deterministic-first verifier against the on-disk artifacts; a clean exit indicates the gate pipeline accepted them. <!-- ground: README.md:58-59 -->

## See also

- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
- [enable-debug-logging-for-docagent](./enable-debug-logging-for-docagent.md)
- [extract-python-symbols-with-pythonadapter](./extract-python-symbols-with-pythonadapter.md)
- [generate-all-artifacts-with-docagent-init](./generate-all-artifacts-with-docagent-init.md)
- [install-docagent-with-multi-provider-extras](./install-docagent-with-multi-provider-extras.md)
- [restrict-a-run-to-a-single-artifact-with-only](./restrict-a-run-to-a-single-artifact-with-only.md)
- [run-an-identity-baseline-to-measure-judge-noise-floor](./run-an-identity-baseline-to-measure-judge-noise-floor.md)
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
