"""llms.txt generator (per llmstxt.org)."""

from __future__ import annotations

from pathlib import Path

from docagent.artifacts._base import SingleFileArtifact
from docagent.prompts.llms_txt import LLMS_TXT_PROMPT, PROMPT_VERSION


class LlmsTxtArtifact(SingleFileArtifact):
    def __init__(self) -> None:
        super().__init__(
            id="llms_txt",
            audience="agent",
            depends_on=("readme",),
            target=Path("llms.txt"),
            prompt=LLMS_TXT_PROMPT,
            prompt_version=PROMPT_VERSION,
        )
