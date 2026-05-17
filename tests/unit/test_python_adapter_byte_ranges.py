"""Tests for ``PythonAdapter``'s byte-range population.

The symbol index uses ``byte_start``/``byte_end`` for ground citations and
(in `api_reference`) for fingerprints over the exact symbol bytes. Earlier
revisions of the adapter set both to zero, which silently corrupted any
caller that relied on the slice. These tests lock down the fix.
"""

from __future__ import annotations

from pathlib import Path

from docagent.adapters.python import PythonAdapter


def _extract(src: str) -> tuple[bytes, dict[str, tuple[int, int]]]:
    """Return (source_bytes, {qualified_name: (byte_start, byte_end)})."""
    adapter = PythonAdapter()
    data = src.encode("utf-8")
    parsed = adapter.parse(Path("x.py"), data)
    syms = adapter.extract_symbols(parsed)
    return data, {s.qualified_name: (s.byte_start, s.byte_end) for s in syms}


def test_byte_range_contains_symbol_name() -> None:
    """A function's byte range must include its own name."""
    src = "def greet(name):\n    return name\n"
    data, ranges = _extract(src)
    assert "greet" in ranges
    bs, be = ranges["greet"]
    assert b"greet" in data[bs:be]


def test_byte_range_covers_whole_definition() -> None:
    """The range should cover signature through body, not just the def line."""
    src = "def foo():\n    return 1 + 2\n"
    data, ranges = _extract(src)
    bs, be = ranges["foo"]
    slice_bytes = data[bs:be]
    assert b"def foo" in slice_bytes
    assert b"return 1 + 2" in slice_bytes


def test_nested_class_method_byte_range() -> None:
    """Class methods get qualified names AND correct byte ranges into source."""
    src = "class Bar:\n    def baz(self):\n        return self.x\n"
    data, ranges = _extract(src)
    bs, be = ranges["Bar.baz"]
    slice_bytes = data[bs:be]
    assert b"def baz" in slice_bytes
    assert b"self.x" in slice_bytes
    # Class range should encompass the method range.
    cls_bs, cls_be = ranges["Bar"]
    assert cls_bs <= bs and be <= cls_be


def test_multi_byte_utf8_in_source_does_not_shift_ranges() -> None:
    """A non-ASCII character in a docstring must not desync the byte offsets.

    Previously the column→byte mapping was identity, so a single emoji or
    smart quote earlier in the file would slide every downstream byte range
    by some amount.
    """
    src = (
        '"""Module docstring with non-ASCII: “quote” and emoji \U0001f600."""\n'
        "def foo():\n"
        "    return 1\n"
        "def bar():\n"
        "    return 2\n"
    )
    data, ranges = _extract(src)
    bs, be = ranges["foo"]
    assert data[bs:be].startswith(b"def foo")
    bs2, be2 = ranges["bar"]
    assert data[bs2:be2].startswith(b"def bar")


def test_byte_range_round_trips_through_slicing() -> None:
    """Slicing source by the byte range and decoding should yield valid UTF-8
    starting with the symbol's keyword."""
    src = "def greet():\n    pass\n\nclass Greeter:\n    def hello(self): pass\n"
    data, ranges = _extract(src)
    for qn, (bs, be) in ranges.items():
        chunk = data[bs:be].decode("utf-8")
        # Either starts with `def `, `class `, or `async def ` — that's the
        # full v1 taxonomy.
        assert chunk.lstrip().startswith(("def ", "class ", "async def ")), (
            f"{qn} chunk does not start with a def/class keyword: {chunk!r}"
        )


def test_byte_ranges_are_non_zero() -> None:
    """Regression guard for the original bug — neither end should be zero
    except for a hypothetical file-start symbol (which doesn't exist)."""
    src = "def x():\n    pass\n"
    _, ranges = _extract(src)
    bs, be = ranges["x"]
    assert bs >= 0 and be > bs


def test_async_function_byte_range() -> None:
    src = "async def fetch(url):\n    return url\n"
    data, ranges = _extract(src)
    bs, be = ranges["fetch"]
    assert data[bs:be].startswith(b"async def fetch")
