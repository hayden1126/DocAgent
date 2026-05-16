"""Post-write hook tests for the Orchestrator.

Without this hook every artifact written has zero mention rows in SQLite and
the `artifacts` table is never populated — `update` mode is silently broken.
These tests pin the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from docagent.artifacts.registry import DocPatch, GenerationContext, Registry, Task, VerifyResult
from docagent.backends.base import GenerationResponse
from docagent.core.orchestrator import Orchestrator
from docagent.index.store import open_store


class _StubBackend:
    """No-op backend; artifacts under test must not call run()."""

    name = "stub"

    def run(self, request):
        raise AssertionError("backend.run should not be called in this test")


@dataclass
class _FixedArtifact:
    """An artifact that emits a fixed Markdown body referencing two known symbols."""

    id: str = "fixed"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / "FIXED.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        body = (
            "# Fixed\n\n"
            "This artifact mentions `Scanner.walk` and the `open_store` helper.\n"
            "It also mentions `nonexistent_symbol_xyz`, which should not be indexed.\n"
        ).encode("utf-8")
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=body,
            prompt_version="t1",
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return tmp_path


def _seed_symbols(store, qns: list[str]) -> None:
    now = "2026-01-01T00:00:00Z"
    rows = [
        (qn, "function", "src/x.py", 0, 0, 1, 1, "", None, "python", "deadbeef")
        for qn in qns
    ]
    store.replace_symbols_for_file("src/x.py", rows)
    store.upsert_file_hash("src/x.py", "deadbeef", "python", now)


def test_post_write_hook_populates_mentions_and_artifacts(repo: Path) -> None:
    store = open_store(repo)
    _seed_symbols(store, ["Scanner.walk", "open_store", "Other.thing"])

    registry = Registry()
    registry.register(_FixedArtifact())

    orch = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=_StubBackend(),
        store=store,
    )
    runs = orch.run()

    assert len(runs) == 1
    r = runs[0]
    assert r.verify_ok
    assert r.error is None
    assert r.digest is not None
    assert r.mention_count >= 2  # both Scanner.walk and open_store

    # Mentions table: known identifiers got indexed, unknown ones did not.
    rows = store.artifacts_mentioning("walk")
    assert any(aid == "fixed" for aid, _ in rows)
    rows = store.artifacts_mentioning("open_store")
    assert any(aid == "fixed" for aid, _ in rows)
    rows = store.artifacts_mentioning("nonexistent_symbol_xyz")
    assert rows == []

    # Artifacts table row exists with a digest.
    digest = store.get_artifact_digest("fixed")
    assert digest is not None
    assert digest == r.digest
    store.close()


def test_post_write_hook_skipped_in_dry_run(repo: Path) -> None:
    store = open_store(repo)
    _seed_symbols(store, ["Scanner.walk"])
    registry = Registry()
    registry.register(_FixedArtifact())
    orch = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=_StubBackend(),
        store=store,
        dry_run=True,
    )
    runs = orch.run()
    assert runs[0].digest is None
    assert runs[0].mention_count == 0
    assert store.get_artifact_digest("fixed") is None
    store.close()


def test_post_write_hook_idempotent_persists_digest(repo: Path) -> None:
    """Re-running with identical content is a no-op write, but the persisted
    digest from the first run remains valid in the artifacts table."""
    store = open_store(repo)
    _seed_symbols(store, ["Scanner.walk"])
    registry = Registry()
    registry.register(_FixedArtifact())
    orch = Orchestrator(repo_root=repo, registry=registry, backend=_StubBackend(), store=store)
    first_run = orch.run()[0]
    assert first_run.digest is not None
    persisted_after_first = store.get_artifact_digest("fixed")
    assert persisted_after_first == first_run.digest

    second_run = orch.run()[0]
    # Identical content → unchanged write → hook does not re-fire.
    assert second_run.digest is None
    assert second_run.writes and not second_run.writes[0].written
    # The persisted digest from run 1 is still authoritative.
    assert store.get_artifact_digest("fixed") == persisted_after_first
    store.close()
