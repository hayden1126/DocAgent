"""README.md generator — first artifact in the v1 vertical slice."""

from __future__ import annotations

from pathlib import Path

from docagent.artifacts._base import SingleFileArtifact
from docagent.prompts.readme import PROMPT_VERSION, README_PROMPT


class ReadmeArtifact(SingleFileArtifact):
    def __init__(self) -> None:
        super().__init__(
            id="readme",
            audience="human",
            depends_on=(),
            target=Path("README.md"),
            prompt=README_PROMPT,
            prompt_version=PROMPT_VERSION,
        )
