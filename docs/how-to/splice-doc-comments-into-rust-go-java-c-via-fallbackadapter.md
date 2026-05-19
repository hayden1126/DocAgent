---
title: "Splice doc comments into Rust/Go/Java/C++ via FallbackAdapter"
slug: splice-doc-comments-into-rust-go-java-c-via-fallbackadapter
docagent_artifact: how_to_guides
---

# Splice doc comments into Rust/Go/Java/C++ via FallbackAdapter

## Goal
Use `FallbackAdapter` to lexically discover symbols in a Rust, Go, Java, or C++ source file and splice a generated doc comment above a chosen symbol using that language's native comment style. <!-- ground: docs/reference/docagent.adapters.fallback.md:42-48 -->

## Steps
1. Import `FallbackAdapter` and instantiate it with the target language id (e.g. `"rust"`). <!-- ground: docs/reference/docagent.adapters.fallback.md:30-33 -->
2. Read the source file as bytes and call `adapter.parse(path, source_bytes)` to obtain a parse result. <!-- ground: docs/reference/docagent.adapters.fallback.md:34-35 -->
3. Call `adapter.extract_symbols(result)` to enumerate discovered symbols with their `kind`, `qualified_name`, `line_start`, and `line_end`. <!-- ground: docs/reference/docagent.adapters.fallback.md:36-38 -->
4. Call `adapter.splice_doc(result.source, symbol, "Adds two integers.")` to produce new source bytes with the doc comment inserted above the symbol in the language's comment style (`///` for Rust, `/** … */` for Java/C++). <!-- ground: docs/reference/docagent.adapters.fallback.md:42-46 -->
5. Write the returned bytes back to the file with `Path(...).write_bytes(new_src)`. <!-- ground: docs/reference/docagent.adapters.fallback.md:46-46 -->

## Verify
Re-read the file and confirm the doc comment appears immediately above the symbol in the correct comment style for that language. <!-- ground: docs/reference/docagent.adapters.fallback.md:42-47 -->

## Troubleshoot
If you instantiate `FallbackAdapter` with an unregistered language id, the constructor raises `KeyError`; pass one of the supported ids instead. <!-- ground: docs/reference/docagent.adapters.fallback.md:50-50 -->

## See also

- [docagent.adapters.fallback](../reference/docagent.adapters.fallback.md)
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
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
