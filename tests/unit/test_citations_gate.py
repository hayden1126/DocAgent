"""Tests for the citations verifier gate.

The gate consumes the citation grammar from `docagent.citations` and confirms
each `<!-- ground: path:start-end -->` marker resolves to a real file and an
in-range line span. Regression coverage for the 2026-05-18 tinydb finding:
LLM-emitted citations to 0-byte marker files (PEP 561 `py.typed`, `.gitkeep`,
etc.) used to bottom out in the generic "exceeds file (0 lines)" message;
the gate now reports them as empty-file rejections.
"""

from __future__ import annotations

from pathlib import Path

from docagent.artifacts.registry import DocPatch, GenerationContext
from docagent.verify import citations


def _patch(body: str) -> DocPatch:
    return DocPatch("test", Path("/tmp/anything"), body.encode("utf-8"))


def _ctx(repo_root: Path) -> GenerationContext:
    return GenerationContext(repo_root=repo_root, store=None, backend=None)


def test_passes_on_valid_in_range_citation(tmp_path: Path) -> None:
    (tmp_path / "src.py").write_text("a\nb\nc\n")
    body = "Claim. <!-- ground: src.py:1-2 -->"
    ok, findings = citations.check(_patch(body), _ctx(tmp_path))
    assert ok is True
    assert findings == []


def test_fails_on_missing_file(tmp_path: Path) -> None:
    body = "Claim. <!-- ground: nope.py:1-1 -->"
    ok, findings = citations.check(_patch(body), _ctx(tmp_path))
    assert ok is False
    assert any("missing file: nope.py" in f for f in findings)


def test_fails_on_out_of_range_line(tmp_path: Path) -> None:
    (tmp_path / "short.py").write_text("one\n")
    body = "Claim. <!-- ground: short.py:1-5 -->"
    ok, findings = citations.check(_patch(body), _ctx(tmp_path))
    assert ok is False
    assert any("exceeds file (1 lines)" in f for f in findings)


def test_fails_clearly_on_zero_byte_file(tmp_path: Path) -> None:
    """Regression for tinydb 2026-05-18: `py.typed` is a PEP 561 marker
    (0 bytes) and the LLM cited `range 1-1`. The previous generic
    `exceeds file (0 lines)` was technically correct but unhelpful — the
    operator-facing message now states the file is empty."""
    (tmp_path / "py.typed").write_text("")
    body = "Claim. <!-- ground: py.typed:1-1 -->"
    ok, findings = citations.check(_patch(body), _ctx(tmp_path))
    assert ok is False
    assert len(findings) == 1
    assert "py.typed: file is empty" in findings[0]
    assert "1-1" in findings[0]


def test_fails_on_zero_byte_file_with_any_line_range(tmp_path: Path) -> None:
    """Cover wider ranges too, not just the 1-1 case."""
    (tmp_path / ".gitkeep").write_text("")
    body = "Claim. <!-- ground: .gitkeep:5-10 -->"
    ok, findings = citations.check(_patch(body), _ctx(tmp_path))
    assert ok is False
    assert any(".gitkeep: file is empty" in f and "5-10" in f for f in findings)
