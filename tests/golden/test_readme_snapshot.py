"""Golden snapshot test for ReadmeArtifact's post-pipeline output.

Verifies that against a known fixture repo and a recorded LLM response, the
ReadmeArtifact produces byte-identical output. This catches regressions in
the cleaner, citation handling, and write path without making real LLM calls.

Update the snapshot deliberately with::

    UPDATE_SNAPSHOTS=1 pytest tests/golden/test_readme_snapshot.py

Then review the diff and commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docagent.artifacts.readme import ReadmeArtifact
from docagent.artifacts.registry import GenerationContext
from docagent.verify import citations, links
from tests.golden._harness import (
    FIXTURES_DIR,
    RECORDINGS_DIR,
    RecordedBackend,
    assert_or_update_snapshot,
)


@pytest.fixture
def tinylib_root() -> Path:
    return FIXTURES_DIR / "tinylib"


def test_readme_snapshot_for_tinylib(tinylib_root: Path) -> None:
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / "tinylib_readme.txt")
    artifact = ReadmeArtifact()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    tasks = artifact.plan(ctx)
    assert len(tasks) == 1
    patch = artifact.generate(tasks[0], ctx)
    actual = patch.new_content.decode("utf-8")
    assert_or_update_snapshot("tinylib_readme.md", actual)


def test_readme_snapshot_citations_validate(tinylib_root: Path) -> None:
    """The committed snapshot must pass the citations gate against the fixture.

    This is the more important guarantee than byte-equality: if a snapshot
    update breaks ground citations, this test fails loudly.
    """
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / "tinylib_readme.txt")
    artifact = ReadmeArtifact()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    patch = artifact.generate(artifact.plan(ctx)[0], ctx)
    ok, findings = citations.check(patch, ctx)
    assert ok, f"citation gate failed: {list(findings)}"


def test_readme_snapshot_links_validate(tinylib_root: Path) -> None:
    backend = RecordedBackend(recording_path=RECORDINGS_DIR / "tinylib_readme.txt")
    artifact = ReadmeArtifact()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    patch = artifact.generate(artifact.plan(ctx)[0], ctx)
    ok, findings = links.check(patch, ctx)
    assert ok, f"link gate failed: {list(findings)}"


def test_readme_artifact_stamps_prompt_version(tinylib_root: Path) -> None:
    from docagent.prompts.readme import PROMPT_VERSION

    backend = RecordedBackend(recording_path=RECORDINGS_DIR / "tinylib_readme.txt")
    artifact = ReadmeArtifact()
    ctx = GenerationContext(repo_root=tinylib_root, store=None, backend=backend)
    patch = artifact.generate(artifact.plan(ctx)[0], ctx)
    assert patch.prompt_version == PROMPT_VERSION
