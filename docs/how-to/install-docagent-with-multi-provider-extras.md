---
title: "Install docagent with multi-provider extras"
slug: install-docagent-with-multi-provider-extras
docagent_artifact: how_to_guides
---

# Install docagent with multi-provider extras

## Goal
Install the `docagent` package together with the optional `multi` extra so the LiteLLM-backed providers (Gemini, OpenRouter, Anthropic-direct) are available alongside the default backend. <!-- ground: README.md:17-21 -->

## Steps
1. Ensure you are running Python 3.11 or newer before installing. <!-- ground: README.md:11-11 -->
2. Install the base package with `pip install docagent`. <!-- ground: README.md:13-15 -->
3. Install the multi-provider extra with `pip install 'docagent[multi]'`. <!-- ground: README.md:19-21 -->

## Verify
Re-run `pip install 'docagent[multi]'`; pip should report the requirement as already satisfied, confirming the `multi` extra is installed. <!-- ground: README.md:19-21 -->

## See also

- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
- [enable-debug-logging-for-docagent](./enable-debug-logging-for-docagent.md)
- [extract-python-symbols-with-pythonadapter](./extract-python-symbols-with-pythonadapter.md)
- [generate-all-artifacts-with-docagent-init](./generate-all-artifacts-with-docagent-init.md)
- [re-verify-on-disk-artifacts-with-docagent-verify](./re-verify-on-disk-artifacts-with-docagent-verify.md)
- [restrict-a-run-to-a-single-artifact-with-only](./restrict-a-run-to-a-single-artifact-with-only.md)
- [run-an-identity-baseline-to-measure-judge-noise-floor](./run-an-identity-baseline-to-measure-judge-noise-floor.md)
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
