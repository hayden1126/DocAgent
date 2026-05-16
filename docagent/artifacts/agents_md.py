"""AGENTS.md generator (per agents.md spec)."""

from __future__ import annotations

from pathlib import Path

from docagent.artifacts._base import SingleFileArtifact
from docagent.prompts.agents_md import AGENTS_MD_PROMPT, PROMPT_VERSION


class AgentsMdArtifact(SingleFileArtifact):
    def __init__(self) -> None:
        super().__init__(
            id="agents_md",
            audience="agent",
            depends_on=("readme",),
            target=Path("AGENTS.md"),
            prompt=AGENTS_MD_PROMPT,
            prompt_version=PROMPT_VERSION,
        )
