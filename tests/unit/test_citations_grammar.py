"""Tests for the canonical citation grammar.

Pins the regex shape so the verifier gate and the affected-artifact resolver
can't drift. Each malformed-input case here is a real one that's been seen
in practice or that the grammar deliberately rejects.
"""

from __future__ import annotations

from docagent.citations import CITATION_RE, cited_paths, iter_citations


def test_single_line_citation() -> None:
    out = iter_citations(b"foo <!-- ground: src/x.py:42 --> bar")
    assert len(out) == 1
    assert out[0].path == "src/x.py"
    assert out[0].line_start == 42
    assert out[0].line_end == 42


def test_line_range_citation() -> None:
    out = iter_citations(b"<!-- ground: README.md:1-10 -->")
    assert out[0].line_start == 1
    assert out[0].line_end == 10


def test_multiple_citations_in_one_doc() -> None:
    body = (
        b"Intro <!-- ground: a.py:1 -->.\n"
        b"Middle <!-- ground: b.py:5-7 -->.\n"
        b"End <!-- ground: c.py:99 -->.\n"
    )
    out = iter_citations(body)
    assert [c.path for c in out] == ["a.py", "b.py", "c.py"]
    assert [c.line_end for c in out] == [1, 7, 99]


def test_whitespace_variations() -> None:
    """Allow surrounding whitespace inside the comment."""
    out = iter_citations(b"<!--   ground:   x.py:1-3   -->")
    assert len(out) == 1
    assert out[0].path == "x.py"


def test_cited_paths_dedupes() -> None:
    body = b"<!-- ground: x.py:1 --> <!-- ground: x.py:9-12 --> <!-- ground: y.py:1 -->"
    assert cited_paths(body) == {"x.py", "y.py"}


def test_rejects_missing_line_number() -> None:
    assert iter_citations(b"<!-- ground: x.py -->") == []


def test_rejects_path_with_colon() -> None:
    """``:`` is reserved as the path/line delimiter — paths can't contain it.

    This documents the grammar constraint; Windows-style ``C:\\foo`` paths are
    out of scope and would require quoting or escaping to support.
    """
    assert iter_citations(b"<!-- ground: C:/x.py:1 -->") == []


def test_rejects_path_with_whitespace() -> None:
    assert iter_citations(b"<!-- ground: my file.md:1 -->") == []


def test_ignores_non_citation_html_comments() -> None:
    body = b"<!-- TODO: write more --> <!-- ground: x.py:1 --> <!-- end -->"
    out = iter_citations(body)
    assert len(out) == 1
    assert out[0].path == "x.py"


def test_regex_is_bytes() -> None:
    """The pattern must be a bytes pattern so callers can operate on raw
    artifact bytes without decoding."""
    assert CITATION_RE.pattern.__class__ is bytes
