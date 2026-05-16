"""Parametrized golden snapshot tests for single-file Markdown artifacts.

For each (artifact, recording, snapshot) triple we exercise the full
post-pipeline path: backend recording → cleaner → DocPatch → write content.
Tests assert: (1) byte-equality with the committed snapshot, (2) every
ground citation resolves against the fixture repo, (3) the prompt_version
travels onto the DocPatch.

Update snapshots deliberately with::

    UPDATE_SNAPSHOTS=1 pytest tests/golden/

Then review the diff and commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from docagent.artifacts._base import SingleFileArtifact
from docagent.artifacts.agents_md import AgentsMdArtifact
from docagent.artifacts.claude_md import ClaudeMdArtifact
from docagent.artifacts.llms_txt import LlmsTxtArtifact
from docagent.artifacts.registry import GenerationContext
from docagent.verify import citations, links
from tests.golden._harness import (
    FIXTURES_DIR,
    RECORDINGS_DIR,
    RecordedBackend,
    assert_or_update_snapshot,
)


@dataclass(frozen=True)
class _Case:
    artifact_factory: type[SingleFileArtifact]
    recording_name: str
    snapshot_name: str


CASES: list[_Case] = [
    _Case(AgentsMdArtifact, "tinylib_agents_md.txt", "tinylib_agents_md.md"),
    _Case(ClaudeMdArtifact, "tinylib_claude_md.txt", "tinylib_claude_md.md"),
    _Case(LlmsTxtArtifact, "tinylib_llms_txt.txt", "tinylib_llms_txt.md"),
]


@pytest.fixture
def tinylib_root() -> Path:
    return FIXTURES_DIR / "tinylib"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.artifact_factory.__name__)
def test_snapshot_byte_equality(case: _Case, tinylib_root: Path) -> None:
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / case.recording_name)
    artifact = case.artifact_factory()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    tasks = artifact.plan(ctx)
    assert len(tasks) == 1
    patch = artifact.generate(tasks[0], ctx)
    assert_or_update_snapshot(case.snapshot_name, patch.new_content.decode("utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.artifact_factory.__name__)
def test_snapshot_citations_validate(case: _Case, tinylib_root: Path) -> None:
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / case.recording_name)
    artifact = case.artifact_factory()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    patch = artifact.generate(artifact.plan(ctx)[0], ctx)
    ok, findings = citations.check(patch, ctx)
    assert ok, f"citation gate failed for {case.artifact_factory.__name__}: {list(findings)}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.artifact_factory.__name__)
def test_snapshot_links_validate(case: _Case, tinylib_root: Path) -> None:
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / case.recording_name)
    artifact = case.artifact_factory()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    patch = artifact.generate(artifact.plan(ctx)[0], ctx)
    ok, findings = links.check(patch, ctx)
    assert ok, f"link gate failed for {case.artifact_factory.__name__}: {list(findings)}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.artifact_factory.__name__)
def test_snapshot_prompt_version_stamped(case: _Case, tinylib_root: Path) -> None:
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / case.recording_name)
    artifact = case.artifact_factory()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    patch = artifact.generate(artifact.plan(ctx)[0], ctx)
    assert patch.prompt_version != "0"
    assert patch.prompt_version == artifact.prompt_version
