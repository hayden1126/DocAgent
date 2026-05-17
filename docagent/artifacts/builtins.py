"""Built-in v1 artifact stubs.

Each artifact owns its `plan → generate → verify` cycle. v1 ships scaffolds
that produce empty patches; real generation prompts are wired in follow-up
patches that depend on this skeleton compiling.

Dependency DAG (v1):
    readme              ←─ (root)
    python_docstrings   ←─ (root, --experimental gated)
    api_reference       ←─ (root; reads the symbol index, not docstring text)
    how_to_guides       ←─ depends on: readme, api_reference
    agents_md           ←─ depends on: readme
    claude_md           ←─ depends on: readme
    llms_txt            ←─ depends on: readme, api_reference
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docagent.artifacts.agents_md import AgentsMdArtifact
from docagent.artifacts.api_reference import ApiReferenceArtifact
from docagent.artifacts.claude_md import ClaudeMdArtifact
from docagent.artifacts.how_to_guides import HowToGuidesArtifact
from docagent.artifacts.llms_txt import LlmsTxtArtifact
from docagent.artifacts.readme import ReadmeArtifact
from docagent.artifacts.registry import (
    Audience,
    DocPatch,
    GenerationContext,
    Registry,
    Task,
    VerifyResult,
)


@dataclass
class _StubArtifact:
    id: str
    audience: Audience
    depends_on: tuple[str, ...]
    target: Path

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / self.target)]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        # TODO: invoke ctx.backend with the artifact-specific prompt template.
        placeholder = (
            f"<!-- docagent: {self.id} stub. Real generator not yet implemented. -->\n"
        ).encode("utf-8")
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=placeholder,
            in_place=False,
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


class PythonDocstringsArtifact(_StubArtifact):
    """In-place docstrings for Python symbols. Emits one task per affected symbol."""

    def plan(self, ctx: GenerationContext) -> list[Task]:
        # TODO: query store.symbols for python files, filter against changed_files.
        return []


def register_v1_builtins(registry: Registry) -> None:
    registry.register(ReadmeArtifact())
    registry.register(
        PythonDocstringsArtifact(
            id="python_docstrings",
            audience="both",
            depends_on=(),
            target=Path("."),
        )
    )
    registry.register(ApiReferenceArtifact())
    registry.register(HowToGuidesArtifact())
    registry.register(AgentsMdArtifact())
    registry.register(ClaudeMdArtifact())
    registry.register(LlmsTxtArtifact())
