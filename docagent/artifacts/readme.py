"""README.md generator — first real artifact in the v1 vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docagent.artifacts.registry import (
    Audience,
    DocPatch,
    GenerationContext,
    Task,
    VerifyResult,
)
from docagent.backends.base import GenerationRequest, LLMBackend
from docagent.prompts.readme import README_PROMPT


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
        content = _clean_readme_output(response.content)
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=content.encode("utf-8"),
            in_place=False,
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        from docagent.verify.pipeline import default_pipeline

        return default_pipeline().run(patch, ctx)


def _clean_readme_output(text: str) -> str:
    """Strip model preamble/postamble around the actual README content.

    The model occasionally emits status text ("I'll use the Skill tool...")
    before or commentary after the README. We seek the first H1 (`# `) line
    and discard anything before it, then strip a trailing markdown fence if
    one was emitted around the whole thing.
    """
    # Strip an outer ```markdown fence if present.
    stripped = text.strip()
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[: -3]
        stripped = stripped.strip()

    # Drop everything before the first H1.
    lines = stripped.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            stripped = "\n".join(lines[i:]).strip()
            break

    if not stripped.endswith("\n"):
        stripped += "\n"
    return stripped
