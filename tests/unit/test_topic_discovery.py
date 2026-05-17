"""Unit tests for docagent.artifacts._topic_discovery (Phase 6, Plan 02)."""

from __future__ import annotations

import re

import pytest

from docagent.artifacts._topic_discovery import (
    Topic,
    dedupe_topics,
    topic_slug,
)

# ---- topic_slug -----------------------------------------------------------------


def test_slug_strips_how_to_prefix() -> None:
    assert topic_slug("How to run docagent in CI") == "run-docagent-in-ci"


def test_slug_prefix_strip_case_insensitive() -> None:
    assert topic_slug("how to set up GitHub Actions") == "set-up-github-actions"


def test_slug_no_how_to_prefix() -> None:
    assert topic_slug("Run docagent in CI") == "run-docagent-in-ci"


def test_slug_collapses_non_alphanumerics() -> None:
    # Backticks + flags + parentheses all collapse to single hyphens; no leading/trailing.
    assert topic_slug("Add `--max-cost` flag") == "add-max-cost-flag"


def test_slug_complex_punctuation_cap_and_no_double_hyphens() -> None:
    title = "Use docagent's `verify` against your repo's CI/CD pipeline (advanced)"
    slug = topic_slug(title)
    assert len(slug) <= 60
    assert not slug.endswith("-")
    assert "--" not in slug
    assert re.fullmatch(r"[a-z0-9-]+", slug)


def test_slug_empty_falls_back_to_hash() -> None:
    s = topic_slug("")
    assert re.fullmatch(r"howto-[a-f0-9]{8}", s)
    # Deterministic: same input → same slug.
    assert topic_slug("") == s


def test_slug_only_non_alphanumeric_falls_back_to_hash() -> None:
    s = topic_slug("!!!")
    assert re.fullmatch(r"howto-[a-f0-9]{8}", s)
    assert topic_slug("!!!") == s


def test_slug_long_input_capped_and_no_trailing_hyphen() -> None:
    s = topic_slug("a" * 200)
    assert len(s) <= 60
    assert not s.endswith("-")


# ---- dedupe_topics --------------------------------------------------------------


def _t(title: str, sources: list[str] | None = None) -> Topic:
    return Topic(slug=topic_slug(title), title=title, sources=sources or [])


def test_dedupe_keeps_first_and_warns_once_per_pair() -> None:
    warns: list[str] = []
    a = _t("Run docagent in CI")
    b = Topic(slug=a.slug, title="Different title same slug", sources=[])
    out = dedupe_topics([a, b], warn=warns.append)
    assert out == [a]
    assert len(warns) == 1
    msg = warns[0]
    assert a.title in msg
    assert b.title in msg


def test_dedupe_three_collisions_emit_two_warns() -> None:
    warns: list[str] = []
    a = _t("Run docagent in CI")
    b = Topic(slug=a.slug, title="second", sources=[])
    c = Topic(slug=a.slug, title="third", sources=[])
    out = dedupe_topics([a, b, c], warn=warns.append)
    assert out == [a]
    assert len(warns) == 2  # one per collision pair, not one total


def test_dedupe_all_unique_no_warns() -> None:
    warns: list[str] = []
    a = _t("Run docagent in CI")
    b = _t("Extend docagent with a new artifact")
    c = _t("Configure max cost")
    out = dedupe_topics([a, b, c], warn=warns.append)
    assert out == [a, b, c]
    assert warns == []


def test_dedupe_empty_input() -> None:
    warns: list[str] = []
    assert dedupe_topics([], warn=warns.append) == []
    assert warns == []


# ---- dataclass shape -----------------------------------------------------------


def test_topic_is_frozen() -> None:
    a = Topic(slug="x", title="X", sources=[])
    with pytest.raises(AttributeError):
        a.slug = "y"  # type: ignore[misc]
