---
title: "Configure the LiteLLM backend for Gemini or OpenRouter"
slug: configure-the-litellm-backend-for-gemini-or-openrouter
docagent_artifact: how_to_guides
---

# Configure the LiteLLM backend for Gemini or OpenRouter

## Goal
Route DocAgent through the opt-in LiteLLM backend so generation goes to Google Gemini or OpenRouter instead of the default Claude Agent SDK, by pairing `--backend litellm` with a provider-prefixed `--model` string and the matching API-key environment variable. <!-- ground: README.md:32-43 -->

## Steps
1. Export the API key that matches your chosen provider — `GEMINI_API_KEY` for Gemini or `OPENROUTER_API_KEY` for OpenRouter. <!-- ground: README.md:37-38 -->
2. Pick a provider-prefixed model string, for example `gemini/gemini-2.5-pro` or `openrouter/anthropic/claude-sonnet-4-6`. <!-- ground: README.md:37-38 -->
3. Run `docagent init --backend litellm --model <model-string>` to invoke the LiteLLM backend with your selected model. <!-- ground: README.md:40-43 -->

## Verify
Run `docagent init --backend litellm` with no `--model`; it should exit with a multi-line hint listing the supported routing strings, confirming the LiteLLM backend is wired up and waiting on a model selection. <!-- ground: README.md:45-45 -->

## See also

- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
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
