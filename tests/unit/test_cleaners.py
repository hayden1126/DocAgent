"""Tests for shared output cleaners."""

from __future__ import annotations

from docagent.artifacts._cleaners import clean_markdown_output, clean_plain_text


def test_clean_markdown_strips_preamble_before_h1():
    raw = (
        "I'll use the Skill tool to check for relevant skills first, but given "
        "the very specific procedural task, let me proceed efficiently. "
        "Reading key files in parallel:\n# Project\n\nBody.\n"
    )
    out = clean_markdown_output(raw)
    assert out.startswith("# Project\n")
    assert "Skill tool" not in out


def test_clean_markdown_strips_outer_fence():
    raw = "```markdown\n# Project\n\nBody.\n```"
    out = clean_markdown_output(raw)
    assert out == "# Project\n\nBody.\n"


def test_clean_markdown_strips_fence_then_preamble():
    raw = "```\nI need to think about this.\n# Project\n\nBody.\n```"
    out = clean_markdown_output(raw)
    assert out.startswith("# Project\n")


def test_clean_markdown_ensures_single_trailing_newline():
    assert clean_markdown_output("# A\nbody").endswith("\n")
    assert not clean_markdown_output("# A\nbody\n\n\n").endswith("\n\n")


def test_clean_markdown_idempotent():
    raw = "# A\nbody\n"
    once = clean_markdown_output(raw)
    twice = clean_markdown_output(once)
    assert once == twice


def test_clean_plain_text_does_not_require_h1():
    raw = "```\n> Project: a tool\n\n[docs](/docs)\n```"
    out = clean_plain_text(raw)
    assert out.startswith("> Project")
