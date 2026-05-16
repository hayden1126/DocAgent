"""README.md generator — first real artifact in the v1 vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docagent.artifacts._cleaners import clean_markdown_output
from docagent.artifacts.registry import (
    Audience,
    DocPatch,
    GenerationContext,
    Task,
    VerifyResult,
)
from docagent.backends.base import GenerationRequest, LLMBackend
from docagent.prompts.readme import PROMPT_VERSION, README_PROMPT


@dataclass
class ReadmeArtifact:
    id: str = "readme"
    audience: Audience = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / "README.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        backend: LLMBackend = ctx.backend  # type: ignore[assignment]
        response = backend.run(
            GenerationRequest(
                artifact_id=self.id,
                prompt=README_PROMPT,
                repo_root=ctx.repo_root,
            )
        )
        content = clean_markdown_output(response.content)
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=content.encode("utf-8"),
            in_place=False,
            prompt_version=PROMPT_VERSION,
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        from docagent.verify.pipeline import default_pipeline

        return default_pipeline().run(patch, ctx)
