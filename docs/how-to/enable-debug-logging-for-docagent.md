---
title: "Enable debug logging for docagent"
slug: enable-debug-logging-for-docagent
docagent_artifact: how_to_guides
---

# Enable debug logging for docagent

## Goal
Turn on verbose debug-level log output from docagent so you can see what the CLI is doing during a run, either by passing a flag in code or by setting an environment variable. <!-- ground: docs/reference/docagent._logging.md:21-28 -->

## Steps
1. Import the logging initialiser from `docagent._logging` at your CLI entry point. <!-- ground: docs/reference/docagent._logging.md:23-24 -->
2. Call `setup_logging(debug=True)` once at startup to opt into debug output. <!-- ground: docs/reference/docagent._logging.md:24-27 -->
3. Alternatively, leave the code alone and set `DOCAGENT_DEBUG=1` in the environment before invoking docagent — it is equivalent to `setup_logging(debug=True)`. <!-- ground: docs/reference/docagent._logging.md:26-26 -->

## Verify
Run your docagent entry point and confirm debug-level records now appear; the call to `setup_logging(debug=True)` initialises logging once at CLI entry. <!-- ground: docs/reference/docagent._logging.md:21-28 -->

## See also

- [docagent._logging](../reference/docagent._logging.md)
- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
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
