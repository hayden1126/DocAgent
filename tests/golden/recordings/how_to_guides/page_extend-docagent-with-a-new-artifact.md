<<<HOWTO_PAGE_BEGIN>>>
# Extend docagent with a new artifact

## Goal
Add a new artifact module (e.g., `changelog`) that participates in the DAG and produces a Markdown file. <!-- ground: docs/reference/tinylib.cli.md:1-30 -->

## Steps
1. Create `docagent/artifacts/<name>.py` exporting a class that implements the artifact protocol. <!-- ground: docs/reference/tinylib.cli.md:1-30 -->
2. Register the artifact in `docagent/artifacts/builtins.py` with appropriate `depends_on`. <!-- ground: docs/reference/tinylib.cli.md:1-30 -->
3. Author the prompt under `docagent/prompts/<name>.py` with a `PROMPT_VERSION` constant. <!-- ground: docs/reference/tinylib.cli.md:1-30 -->

## Verify
Run `docagent init --only <name>` and confirm the page is written under the expected output directory. <!-- ground: docs/reference/tinylib.cli.md:1-30 -->

## Troubleshoot
If the verifier reports missing citations, confirm each grounded line range references real lines in the cited source. <!-- ground: docs/reference/tinylib.cli.md:1-30 -->
<<<HOWTO_PAGE_END>>>
