---
title: "Restrict a run to a single artifact with --only"
slug: restrict-a-run-to-a-single-artifact-with-only
docagent_artifact: how_to_guides
---

# Restrict a run to a single artifact with --only

## Goal
Limit a `docagent init` or `docagent update` invocation so it processes only the artifact(s) you name, instead of regenerating the full set. <!-- ground: README.md:62-62 -->

## Steps
1. Pick the artifact id you want to (re)generate (for example `readme`). <!-- ground: README.md:62-62 -->
2. Run `docagent init --only <artifact_id>` to restrict the run to that artifact. <!-- ground: README.md:62-62 -->
3. For an incremental refresh restricted to the same artifact, run `docagent update --only <artifact_id>`. <!-- ground: README.md:62-62 -->
4. To preview the result without writing, combine it with `--dry-run`, e.g. `docagent init --only <artifact_id> --dry-run`. <!-- ground: README.md:62-62 -->

## Verify
Re-run the command without `--dry-run` and confirm only the named artifact is produced; `--only <artifact_id>` is documented to restrict the run to specific artifacts. <!-- ground: README.md:62-62 -->

## See also

- [aggregate-per-repo-metrics-into-aggregate-json](./aggregate-per-repo-metrics-into-aggregate-json.md)
- [clone-and-strip-a-repo-without-invoking-docagent](./clone-and-strip-a-repo-without-invoking-docagent.md)
- [configure-the-litellm-backend-for-gemini-or-openrouter](./configure-the-litellm-backend-for-gemini-or-openrouter.md)
- [enable-debug-logging-for-docagent](./enable-debug-logging-for-docagent.md)
- [extract-python-symbols-with-pythonadapter](./extract-python-symbols-with-pythonadapter.md)
- [generate-all-artifacts-with-docagent-init](./generate-all-artifacts-with-docagent-init.md)
- [install-docagent-with-multi-provider-extras](./install-docagent-with-multi-provider-extras.md)
- [re-verify-on-disk-artifacts-with-docagent-verify](./re-verify-on-disk-artifacts-with-docagent-verify.md)
- [run-an-identity-baseline-to-measure-judge-noise-floor](./run-an-identity-baseline-to-measure-judge-noise-floor.md)
- [run-the-regeneration-benchmark-against-one-repo-from-python](./run-the-regeneration-benchmark-against-one-repo-from-python.md)
- [run-the-regeneration-benchmark-from-the-cli](./run-the-regeneration-benchmark-from-the-cli.md)
- [score-a-regeneration-result-with-llm-judges](./score-a-regeneration-result-with-llm-judges.md)
- [splice-a-docstring-into-a-python-source-file](./splice-a-docstring-into-a-python-source-file.md)
- [splice-doc-comments-into-rust-go-java-c-via-fallbackadapter](./splice-doc-comments-into-rust-go-java-c-via-fallbackadapter.md)
