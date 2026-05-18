"""Shared output cleaners for artifact generators.

The Claude Agent SDK occasionally returns assistant text with a preamble
("I'll use the Skill tool…"), a trailing commentary, or an outer ```markdown
fence despite prompt instructions to the contrary. Every artifact that emits
Markdown needs the same defensive scrubbing. Keep it in one place so when the
model behavior shifts we update a single function.
"""

from __future__ import annotations

MIN_CLEAN_BYTES = 64
"""Minimum length (in characters) of a cleaned artifact body. Outputs shorter
than this almost always indicate over-strip (the LLM returned only a fence,
preamble, or whitespace) and would otherwise be silently written to disk and
locked into the fingerprint cache. Even the shortest legitimate artifact
(an `llms.txt` stub) clears this floor."""


class OutputTooSmallError(ValueError):
    """Raised when a cleaner produces output below `MIN_CLEAN_BYTES`.

    The orchestrator catches this, records it as a finding, and refuses
    to write the artifact or upsert its digest — so a future run will
    regenerate instead of cache-hitting on the broken output.
    """

    def __init__(self, *, actual: int, minimum: int, require_h1: bool) -> None:
        self.actual = actual
        self.minimum = minimum
        self.require_h1 = require_h1
        super().__init__(
            f"cleaned output too small: {actual} < {minimum} bytes "
            f"(require_h1={require_h1})"
        )


def clean_markdown_output(text: str, *, require_h1: bool = True) -> str:
    """Strip preambles, trailing commentary, and outer fences from LLM output.

    - Trims whitespace.
    - If the output starts with a ``` fence, drop the fence line and any
      matching trailing fence.
    - If `require_h1` is True (the default), drop every line before the first
      `# ` H1. Most top-level Markdown artifacts (README, AGENTS.md,
      CLAUDE.md) begin with an H1, so this is a reliable anchor.
    - Ensure exactly one trailing newline.
    """
    stripped = text.strip()

    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[: -3]
        stripped = stripped.strip()

    if require_h1:
        lines = stripped.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                stripped = "\n".join(lines[i:]).strip()
                break

    if len(stripped) < MIN_CLEAN_BYTES:
        raise OutputTooSmallError(
            actual=len(stripped),
            minimum=MIN_CLEAN_BYTES,
            require_h1=require_h1,
        )

    if not stripped.endswith("\n"):
        stripped += "\n"
    return stripped


def clean_plain_text(text: str) -> str:
    """For artifacts that aren't Markdown (e.g. llms.txt). Strips fences only."""
    return clean_markdown_output(text, require_h1=False)
