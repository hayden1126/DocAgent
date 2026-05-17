---
title: "Run docagent in CI"
slug: run-docagent-in-ci
docagent_artifact: how_to_guides
---

# Run docagent in CI

## Goal
Run `docagent verify` on every pull request so documentation drift is caught before merge. <!-- ground: README.md:1-40 -->

## Steps
1. Add a `docagent verify` step to your CI workflow. <!-- ground: README.md:1-40 -->
2. Commit `.docagent/index.db` is NOT required — the action regenerates the index on each run. <!-- ground: README.md:1-40 -->
3. Fail the build on a non-zero exit code from `docagent verify`. <!-- ground: README.md:1-40 -->

## Verify
Open a pull request that breaks a citation and confirm the CI job fails. <!-- ground: README.md:1-40 -->

## See also

- [extend-docagent-with-a-new-artifact](./extend-docagent-with-a-new-artifact.md)
