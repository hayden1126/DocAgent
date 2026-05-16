"""Tests for the affected-artifact resolver."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from docagent.artifacts.registry import GenerationContext, Registry, Task, VerifyResult
from docagent.core.affected import compute_affected_artifacts
from docagent.index.store import open_store


@dataclass
class _StubArtifact:
    id: str
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx):
        return []

    def generate(self, task, ctx):
        ...

    def verify(self, patch, ctx):
        return VerifyResult(ok=True)


def _seed_symbols(store, file: str, qns: list[str]) -> None:
    rows = [(qn, "function", file, 0, 0, 1, 1, "", None, "python", "h") for qn in qns]
    store.replace_symbols_for_file(file, rows)


def _register(reg: Registry, ids: list[str]) -> None:
    for i in ids:
        reg.register(_StubArtifact(id=i))


def _record_mentions(store, artifact_id: str, path: str, names: list[str]) -> None:
    store.replace_mentions_for_artifact(
        artifact_id, [(n, artifact_id, path) for n in names]
    )


def test_no_changes_no_affected(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    _register(reg, ["readme"])
    out = compute_affected_artifacts(tmp_path, store, [], {}, reg)
    assert out == []
    store.close()


def test_removed_symbol_flags_mentioning_artifact(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    _seed_symbols(store, "src/x.py", ["foo", "Bar.baz"])
    _record_mentions(store, "readme", "README.md", ["foo"])
    _record_mentions(store, "agents_md", "AGENTS.md", ["unrelated"])

    reg = Registry()
    _register(reg, ["readme", "agents_md"])

    # The file changed; `foo` is gone in the new symbols.
    out = compute_affected_artifacts(
        tmp_path, store, [tmp_path / "src/x.py"], {"src/x.py": set()}, reg
    )
    assert out == ["readme"]
    store.close()


def test_added_symbol_flags_artifact_that_already_mentions_it(tmp_path: Path) -> None:
    """A new symbol counts only if some artifact already mentions the name.

    This catches the case where prose was written assuming a symbol exists,
    and then someone finally adds it (or renames toward it). The artifact
    should refresh to re-validate citations.
    """
    store = open_store(tmp_path)
    _seed_symbols(store, "src/x.py", [])  # no symbols yet
    _record_mentions(store, "agents_md", "AGENTS.md", ["new_helper"])

    reg = Registry()
    _register(reg, ["agents_md"])

    out = compute_affected_artifacts(
        tmp_path, store, [tmp_path / "src/x.py"], {"src/x.py": {"new_helper"}}, reg
    )
    assert out == ["agents_md"]
    store.close()


def test_tail_match_works(tmp_path: Path) -> None:
    """Prose mentioning ``baz`` is caught when the symbol's qualified name is
    ``Bar.baz``."""
    store = open_store(tmp_path)
    _seed_symbols(store, "src/x.py", ["Bar.baz"])
    _record_mentions(store, "readme", "README.md", ["baz"])

    reg = Registry()
    _register(reg, ["readme"])

    out = compute_affected_artifacts(
        tmp_path, store, [tmp_path / "src/x.py"], {"src/x.py": set()}, reg
    )
    assert out == ["readme"]
    store.close()


def test_path_citation_flags_artifact_when_cited_file_changes(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    store.upsert_artifact("readme", "README.md", "d", now)
    (tmp_path / "README.md").write_text(
        "# Project\n\nSee config <!-- ground: pyproject.toml:1-3 -->.\n"
    )

    reg = Registry()
    _register(reg, ["readme"])

    out = compute_affected_artifacts(
        tmp_path,
        store,
        [tmp_path / "pyproject.toml"],
        {"pyproject.toml": set()},
        reg,
    )
    assert out == ["readme"]
    store.close()


def test_user_edited_artifact_is_skipped(tmp_path: Path) -> None:
    """A user editing README.md directly should NOT trigger anything."""
    store = open_store(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    store.upsert_artifact("readme", "README.md", "d", now)
    _record_mentions(store, "readme", "README.md", ["foo"])

    reg = Registry()
    _register(reg, ["readme"])

    out = compute_affected_artifacts(
        tmp_path, store, [tmp_path / "README.md"], {}, reg
    )
    assert out == []
    store.close()


def test_unknown_artifact_filtered_out(tmp_path: Path) -> None:
    """If the mentions table references an artifact the registry no longer
    knows about, it should be silently dropped."""
    store = open_store(tmp_path)
    _seed_symbols(store, "src/x.py", ["foo"])
    _record_mentions(store, "ghost_artifact", "WAT.md", ["foo"])

    reg = Registry()
    _register(reg, ["readme"])  # no ghost_artifact

    out = compute_affected_artifacts(
        tmp_path, store, [tmp_path / "src/x.py"], {"src/x.py": set()}, reg
    )
    assert out == []
    store.close()


def test_topo_order_preserved(tmp_path: Path) -> None:
    """When multiple artifacts are affected, they are returned in topo order."""
    store = open_store(tmp_path)
    _seed_symbols(store, "src/x.py", ["foo"])
    _record_mentions(store, "readme", "README.md", ["foo"])
    _record_mentions(store, "agents_md", "AGENTS.md", ["foo"])

    reg = Registry()
    reg.register(_StubArtifact(id="readme"))
    reg.register(_StubArtifact(id="agents_md", depends_on=("readme",)))

    out = compute_affected_artifacts(
        tmp_path, store, [tmp_path / "src/x.py"], {"src/x.py": set()}, reg
    )
    assert out == ["readme", "agents_md"]
    store.close()
