"""Orchestrator behavior when an artifact's cleaner rejects too-small output.

Pins the v1.0.1 cache lock-in fix: when ``clean_markdown_output`` raises
``OutputTooSmallError`` from inside ``artifact.generate()``, the orchestrator
must:

1. Record a finding describing the under-size,
2. Mark ``run.verify_ok = False``,
3. Skip the on-disk write,
4. Skip the post-write hook (so the SQLite ``artifacts`` table does NOT
   gain a digest row that would short-circuit the next run).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from docagent.artifacts._cleaners import OutputTooSmallError
from docagent.artifacts.registry import (
    DocPatch,
    GenerationContext,
    Registry,
    Task,
    VerifyResult,
)
from docagent.core.orchestrator import Orchestrator
from docagent.index.store import open_store


class _StubBackend:
    name = "stub"

    def run(self, request):
        raise AssertionError("backend.run should not be called in this test")


@dataclass
class _TooSmallArtifact:
    """Generates by directly raising OutputTooSmallError — same path the
    SingleFileArtifact takes when its cleaner rejects under-size output."""

    id: str = "too_small"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / "TOO_SMALL.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        raise OutputTooSmallError(actual=1, minimum=64, require_h1=True)

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        raise AssertionError("verify should not be reached on OutputTooSmallError")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return tmp_path


def test_too_small_skips_write_and_cache(repo: Path) -> None:
    store = open_store(repo)
    registry = Registry()
    registry.register(_TooSmallArtifact())

    orch = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=_StubBackend(),
        store=store,
    )
    runs = orch.run()

    assert len(runs) == 1
    r = runs[0]
    assert r.verify_ok is False
    assert r.error is None  # not a hard error — handled cleanly
    assert r.writes == []
    assert r.digest is None
    assert r.mention_count == 0
    assert any("too small" in f for f in r.findings)
    assert any("1 < 64 bytes" in f for f in r.findings)

    # The load-bearing assertion: no digest row was upserted, so the next
    # run will regenerate instead of cache-hitting on broken output.
    assert store.get_artifact_digest("too_small") is None
    assert not (repo / "TOO_SMALL.md").exists()
    store.close()
