---
title: "Splice a docstring into a Python source file"
slug: splice-a-docstring-into-a-python-source-file
docagent_artifact: how_to_guides
---

# Splice a docstring into a Python source file

## Goal
Replace or insert a leading docstring on a named Python symbol and write the updated source back to disk, using `PythonAdapter.splice_doc`. <!-- ground: docs/reference/docagent.adapters.python.md:53-62 -->

## Steps
1. Instantiate the adapter, read the target file as bytes, and parse it into a tree. <!-- ground: docs/reference/docagent.adapters.python.md:53-62 -->
2. Extract symbols from the tree and pick the one whose `qualified_name` matches your target (for example, `PythonAdapter.parse`). <!-- ground: docs/reference/docagent.adapters.python.md:56-59 -->
3. Call `adapter.splice_doc(src, sym=<symbol>, doc="<new docstring>")` to get the rewritten source bytes. <!-- ground: docs/reference/docagent.adapters.python.md:55-60 -->
4. Write the returned bytes back to the original path with `Path(...).write_bytes(new_src)`. <!-- ground: docs/reference/docagent.adapters.python.md:61-61 -->

## Verify
Re-parse the file and confirm the targeted symbol's leading string expression now matches the docstring you supplied. <!-- ground: docs/reference/docagent.adapters.python.md:53-62 -->

## See also

- [docagent.adapters.python](../reference/docagent.adapters.python.md)
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
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
