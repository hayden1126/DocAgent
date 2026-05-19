---
title: "Extract Python symbols with PythonAdapter"
slug: extract-python-symbols-with-pythonadapter
docagent_artifact: how_to_guides
---

# Extract Python symbols with PythonAdapter

## Goal
Use `PythonAdapter` to parse a Python source file and enumerate its symbols — each carrying a `kind`, `qualified_name`, and start/end line range — so you can drive downstream tooling such as docstring splicing. <!-- ground: docs/reference/docagent.adapters.python.md:43-50 -->

## Steps
1. Load the source bytes for the target file via `Path(...).read_bytes()`. <!-- ground: docs/reference/docagent.adapters.python.md:43-45 -->
2. Parse the bytes with `adapter.parse(path, src)` to obtain a tree. <!-- ground: docs/reference/docagent.adapters.python.md:46-46 -->
3. Call `adapter.extract_symbols(tree)` to get the list of symbols. <!-- ground: docs/reference/docagent.adapters.python.md:47-47 -->
4. Iterate the result and read `sym.kind`, `sym.qualified_name`, `sym.line_start`, and `sym.line_end` per symbol. <!-- ground: docs/reference/docagent.adapters.python.md:48-49 -->

## Verify
Run the snippet and confirm each printed line shows a kind, a dotted qualified name, and a numeric start/end line range for symbols defined in the parsed file. <!-- ground: docs/reference/docagent.adapters.python.md:48-50 -->

## See also

- [docagent.adapters.python](../reference/docagent.adapters.python.md)
- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
- [enable-debug-logging-for-docagent](./enable-debug-logging-for-docagent.md)
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
