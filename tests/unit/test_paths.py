"""Path normalization tests.

Every path that lands in SQLite must be repo-relative POSIX. These pin the
helper so the post-write hook, affected resolver, and indexer can't drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docagent.core.paths import to_repo_rel_posix, try_repo_rel_posix


def test_absolute_path_under_repo(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "x.md"
    target.parent.mkdir()
    target.write_text("x")
    assert to_repo_rel_posix(tmp_path, target) == "docs/x.md"


def test_relative_path_under_repo(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("x")
    # cwd does not matter; we resolve against repo_root
    assert to_repo_rel_posix(tmp_path, Path("docs/x.md")) == "docs/x.md"


def test_outside_repo_raises(tmp_path: Path) -> None:
    other = tmp_path.parent / "elsewhere.md"
    with pytest.raises(ValueError, match="not under repo root"):
        to_repo_rel_posix(tmp_path, other)


def test_try_variant_returns_none_outside(tmp_path: Path) -> None:
    assert try_repo_rel_posix(tmp_path, tmp_path.parent / "x.md") is None


def test_try_variant_returns_path_inside(tmp_path: Path) -> None:
    assert try_repo_rel_posix(tmp_path, tmp_path / "a" / "b.md") == "a/b.md"
