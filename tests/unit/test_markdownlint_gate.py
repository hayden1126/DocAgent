"""Tests for the markdownlint gate (pymarkdown integration)."""

from __future__ import annotations

from pathlib import Path

import pytest

from docagent.artifacts.registry import DocPatch, GenerationContext
from docagent.verify import markdownlint


def _patch(content: bytes, target: str = "x.md") -> DocPatch:
    return DocPatch(artifact_id="t", target_path=Path(target), new_content=content)


def _ctx(tmp_path: Path) -> GenerationContext:
    return GenerationContext(repo_root=tmp_path, store=None, backend=None)


needs_pymarkdown = pytest.mark.skipif(
    markdownlint._find_binary() is None, reason="pymarkdown not installed"
)


def test_non_markdown_target_passes(tmp_path: Path) -> None:
    """Non-Markdown targets (llms.txt, AGENTS.md technically counts) bypass linting."""
    ok, findings = markdownlint.check(_patch(b"raw text", target="llms.txt"), _ctx(tmp_path))
    assert ok
    assert list(findings) == []


@needs_pymarkdown
def test_clean_markdown_passes(tmp_path: Path) -> None:
    content = b"# Title\n\nA short paragraph.\n"
    ok, findings = markdownlint.check(_patch(content), _ctx(tmp_path))
    assert ok, findings


@needs_pymarkdown
def test_dirty_markdown_reports_findings(tmp_path: Path) -> None:
    # MD018: no space after `##`, MD022: missing blank line around heading.
    content = b"# Title\n##NoSpace\n"
    ok, findings = markdownlint.check(_patch(content), _ctx(tmp_path))
    assert not ok
    assert any("MD018" in f or "MD022" in f for f in findings)


def test_missing_binary_skipped_silently(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(markdownlint, "_find_binary", lambda: None)
    ok, findings = markdownlint.check(_patch(b"# T\n"), _ctx(tmp_path))
    assert ok
    assert any("not installed" in f for f in findings)


@needs_pymarkdown
def test_findings_capped_at_25(tmp_path: Path) -> None:
    # Generate a file that will fan out many MD findings (no blank lines between headings).
    chunks = ["# Title"] + [f"##H{i}" for i in range(60)]
    content = ("\n".join(chunks) + "\n").encode("utf-8")
    ok, findings = markdownlint.check(_patch(content), _ctx(tmp_path))
    assert not ok
    assert len(findings) <= 26  # 25 findings + "(+ N more)" line
