"""CLAUDE.md generator (Anthropic project-context convention)."""

from __future__ import annotations

from pathlib import Path

from docagent.artifacts._base import SingleFileArtifact
from docagent.prompts.claude_md import CLAUDE_MD_PROMPT, PROMPT_VERSION


class ClaudeMdArtifact(SingleFileArtifact):
    def __init__(self) -> None:
        super().__init__(
            id="claude_md",
            audience="agent",
            depends_on=("readme",),
            target=Path("CLAUDE.md"),
            prompt=CLAUDE_MD_PROMPT,
            prompt_version=PROMPT_VERSION,
        )
