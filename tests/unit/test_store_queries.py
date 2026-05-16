"""Tests for the new Store query helpers used by update mode."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from docagent.index.store import open_store


def _seed_symbols(store, file: str, rows: list[tuple[str, str]]) -> None:
    seeded = [
        (qn, kind, file, 0, 0, 1, 1, "", None, "python", "hash")
        for qn, kind in rows
    ]
    store.replace_symbols_for_file(file, seeded)


def test_symbols_for_file_round_trips(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    _seed_symbols(store, "a.py", [("foo", "function"), ("Bar.baz", "method")])
    _seed_symbols(store, "b.py", [("qux", "function")])

    got = store.symbols_for_file("a.py")
    names = {qn for qn, _ in got}
    assert names == {"foo", "Bar.baz"}

    got_b = store.symbols_for_file("b.py")
    assert {qn for qn, _ in got_b} == {"qux"}

    # Missing file → empty list.
    assert store.symbols_for_file("nope.py") == []
    store.close()


def test_replace_symbols_for_file_replaces_not_appends(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    _seed_symbols(store, "a.py", [("foo", "function"), ("bar", "function")])
    _seed_symbols(store, "a.py", [("baz", "function")])  # replace, not add
    names = {qn for qn, _ in store.symbols_for_file("a.py")}
    assert names == {"baz"}
    store.close()


def test_artifact_paths_returns_known_set(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    store.upsert_artifact("readme", "README.md", "deadbeef", now)
    store.upsert_artifact("agents_md", "AGENTS.md", "feedface", now)
    paths = store.artifact_paths()
    assert paths == {"README.md", "AGENTS.md"}
    store.close()


def test_list_artifacts_sorted(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    store.upsert_artifact("readme", "README.md", "d1", now)
    store.upsert_artifact("agents_md", "AGENTS.md", "d2", now)
    ids = [row[0] for row in store.list_artifacts()]
    assert ids == ["agents_md", "readme"]
    store.close()
