"""Tests for shared output cleaners."""

from __future__ import annotations

import pytest

from docagent.artifacts._cleaners import (
    MIN_CLEAN_BYTES,
    OutputTooSmallError,
    clean_markdown_output,
    clean_plain_text,
)

_BODY = (
    "Body paragraph long enough to clear the minimum-bytes floor "
    "so the cleaner does not flag it as over-stripped output.\n"
)


def test_clean_markdown_strips_preamble_before_h1():
    raw = (
        "I'll use the Skill tool to check for relevant skills first, but given "
        "the very specific procedural task, let me proceed efficiently. "
        f"Reading key files in parallel:\n# Project\n\n{_BODY}"
    )
    out = clean_markdown_output(raw)
    assert out.startswith("# Project\n")
    assert "Skill tool" not in out


def test_clean_markdown_strips_outer_fence():
    raw = f"```markdown\n# Project\n\n{_BODY}```"
    out = clean_markdown_output(raw)
    assert out == f"# Project\n\n{_BODY}"


def test_clean_markdown_strips_fence_then_preamble():
    raw = f"```\nI need to think about this.\n# Project\n\n{_BODY}```"
    out = clean_markdown_output(raw)
    assert out.startswith("# Project\n")


def test_clean_markdown_ensures_single_trailing_newline():
    body_no_trail = f"# Project\n\n{_BODY.rstrip()}"
    assert clean_markdown_output(body_no_trail).endswith("\n")
    assert not clean_markdown_output(body_no_trail + "\n\n\n").endswith("\n\n")


def test_clean_markdown_idempotent():
    raw = f"# Project\n\n{_BODY}"
    once = clean_markdown_output(raw)
    twice = clean_markdown_output(once)
    assert once == twice


def test_clean_plain_text_does_not_require_h1():
    body = (
        "> Project description that is long enough to satisfy the "
        "minimum-bytes floor in the shared cleaner.\n\n[docs](/docs)\n"
    )
    out = clean_plain_text(f"```\n{body}```")
    assert out.startswith("> Project")


# --- New: too-small output guard (v1.0.1 cache lock-in fix) ---


def test_too_small_raises_on_fence_only_input():
    """LLM returns only a fenced empty block → no content survives."""
    with pytest.raises(OutputTooSmallError) as exc:
        clean_markdown_output("```\n```")
    assert exc.value.actual < MIN_CLEAN_BYTES
    assert exc.value.minimum == MIN_CLEAN_BYTES
    assert exc.value.require_h1 is True


def test_too_small_raises_on_whitespace_only_input():
    with pytest.raises(OutputTooSmallError):
        clean_markdown_output("   \n\n\t  \n")


def test_too_small_raises_when_h1_present_but_body_trivial():
    """The bug case: an H1 with near-nothing after it cleans to ~1 byte after strip."""
    with pytest.raises(OutputTooSmallError):
        clean_markdown_output("# A\n")


def test_too_small_message_includes_byte_counts():
    with pytest.raises(OutputTooSmallError, match=r"too small: \d+ < 64 bytes"):
        clean_markdown_output("# A\n")


def test_plain_text_also_enforces_floor():
    """clean_plain_text delegates to the same path with require_h1=False."""
    with pytest.raises(OutputTooSmallError) as exc:
        clean_plain_text("```\nshort\n```")
    assert exc.value.require_h1 is False
