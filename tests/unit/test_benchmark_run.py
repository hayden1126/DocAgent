"""Tests for the regeneration benchmark's deterministic half.

Covers helpers in `benchmarks/regeneration/run.py`:
- `_is_sphinx_dir` — detection used to skip RST docs that DocAgent
  can't reproduce (KNOWN-GAPS.md §4).
- `strip_docs` — full Sphinx-skip integration: a Sphinx tree stays in
  the clone and is recorded as `docs/ (skipped:sphinx)`.
- `_parse_cost_from_stdout` — best-effort cost extraction from
  docagent stdout.
"""

from __future__ import annotations

from pathlib import Path

from benchmarks.regeneration.run import (
    EXPECTED_ROOT_ARTIFACTS,
    _is_sphinx_dir,
    _parse_cost_from_stdout,
    strip_docs,
)


def test_is_sphinx_dir_detects_conf_py(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "conf.py").write_text("project = 'x'\n")
    assert _is_sphinx_dir(docs) is True


def test_is_sphinx_dir_detects_rst(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.rst").write_text("Hello\n=====\n")
    assert _is_sphinx_dir(docs) is True


def test_is_sphinx_dir_skips_markdown_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("# hi\n")
    assert _is_sphinx_dir(docs) is False


def test_strip_docs_leaves_sphinx_in_place(tmp_path: Path) -> None:
    clone = tmp_path / "repo"
    clone.mkdir()
    docs = clone / "docs"
    docs.mkdir()
    (docs / "conf.py").write_text("")
    (docs / "api.rst").write_text("")
    archive = tmp_path / "archive"

    moved = strip_docs(clone, archive)

    assert moved == ["docs/ (skipped:sphinx)"]
    assert (clone / "docs").exists(), "Sphinx tree must stay in clone for benchmark fairness"
    assert not (archive / "docs").exists(), "Sphinx tree must NOT be archived as stripped"


def test_strip_docs_archives_markdown_docs(tmp_path: Path) -> None:
    clone = tmp_path / "repo"
    clone.mkdir()
    docs = clone / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# guide")
    (clone / "README.md").write_text("# proj")
    archive = tmp_path / "archive"

    moved = strip_docs(clone, archive)

    assert "README.md" in moved
    assert "docs/" in moved
    assert not (clone / "README.md").exists()
    assert not (clone / "docs").exists()
    assert (archive / "README.md").read_text() == "# proj"
    assert (archive / "docs" / "guide.md").read_text() == "# guide"


def test_parse_cost_from_stdout_finds_value() -> None:
    stdout = "Generating artifacts...\nin=100 out=200 cost=$0.012 wall=1.5s\n"
    assert _parse_cost_from_stdout(stdout) == 0.012


def test_parse_cost_from_stdout_returns_last_match() -> None:
    """Multiple cost prints (per-task lines) — we want the rollup at the end."""
    stdout = "cost=$0.001\nmore work\ncost=$0.005\nfinal cost=$0.028\n"
    assert _parse_cost_from_stdout(stdout) == 0.028


def test_parse_cost_from_stdout_returns_none_on_no_match() -> None:
    assert _parse_cost_from_stdout("no cost line here\n") is None


def test_expected_root_artifacts_unchanged() -> None:
    """Canary: if this list changes, write_rate semantics change too."""
    assert EXPECTED_ROOT_ARTIFACTS == ("README.md", "AGENTS.md", "CLAUDE.md", "llms.txt")
