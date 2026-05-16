"""Shared base for single-file Markdown artifacts.

Four artifacts in v1 (README, AGENTS.md, CLAUDE.md, llms.txt) have the same
shape: one task, one LLM call against the repo, a cleaner pass, a single-file
write. Subclasses provide only the prompt, the prompt version, the target
filename, and the audience/depends_on metadata. Anything richer (per-symbol
fan-out, multi-file outputs, build-detection) belongs in its own artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from docagent.artifacts._cleaners import clean_markdown_output
from docagent.artifacts.registry import (
    Audience,
    DocPatch,
    GenerationContext,
    Task,
    VerifyResult,
)
from docagent.backends.base import GenerationRequest, LLMBackend


@dataclass
class SingleFileArtifact:
    """A one-task, one-file, one-LLM-call artifact.

    Subclasses override class attributes (or pass them at construction) to
    specialize. The cleaner defaults to ``clean_markdown_output`` which is
    correct for README/AGENTS.md/CLAUDE.md/llms.txt (all H1-anchored).
    """

    id: str
    audience: Audience
    depends_on: tuple[str, ...]
    target: Path
    prompt: str
    prompt_version: str
    cleaner: Callable[[str], str] = clean_markdown_output

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / self.target)]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        backend: LLMBackend = ctx.backend  # type: ignore[assignment]
        response = backend.run(
            GenerationRequest(
                artifact_id=self.id,
                prompt=self.prompt,
                repo_root=ctx.repo_root,
            )
        )
        content = self.cleaner(response.content)
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=content.encode("utf-8"),
            in_place=False,
            prompt_version=self.prompt_version,
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        from docagent.verify.pipeline import default_pipeline

        return default_pipeline().run(patch, ctx)
