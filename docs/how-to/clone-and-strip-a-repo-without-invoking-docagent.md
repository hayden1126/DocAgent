---
title: "Clone and strip a repo without invoking docagent"
slug: clone-and-strip-a-repo-without-invoking-docagent
docagent_artifact: how_to_guides
---

# Clone and strip a repo without invoking docagent

## Goal
Shallow-clone an arbitrary repo and archive its existing human-authored docs into a results directory, using the regeneration harness's lower-level helpers directly — without running the full `docagent` regeneration pipeline. <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->

## Steps
1. Import `RepoSpec`, `shallow_clone`, and `strip_docs` from `benchmarks.regeneration.run`. <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->
2. Construct a `RepoSpec` with `name`, `language`, `url`, and `sha` (pass `sha=None` to take the remote default). <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->
3. Call `shallow_clone(spec, clone_dir)` with the target clone path; it returns the resolved commit SHA. <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->
4. Call `strip_docs(clone_dir, Path(f"results/<name>-{sha[:12]}/original"))` to move existing docs into the archive directory. <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->
5. Inspect the returned list of moved paths to confirm which docs were archived or skipped. <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->

## Verify
Print the return value of `strip_docs` — a non-empty list such as `['README.md', 'docs/ (skipped:sphinx)']` confirms the clone and strip succeeded. <!-- ground: docs/reference/benchmarks.regeneration.run.md:48-55 -->

## See also

- [benchmarks.regeneration.run](../reference/benchmarks.regeneration.run.md)
- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
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
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
