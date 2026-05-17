"""Tests for the tightened mention extractor.

Pinning the rules: a bare English word in prose must not match; backticked
identifiers count; identifiable code shapes (underscore, camelCase, dotted)
count even outside backticks.
"""

from __future__ import annotations

from docagent.index.mentions import extract_mentions


def _ext(s: str) -> set[str]:
    return extract_mentions(s.encode("utf-8"))


def test_plain_english_words_do_not_match() -> None:
    assert _ext("the cat ran swiftly across the room") == set()


def test_common_stopwords_named_like_symbols_do_not_leak() -> None:
    # The old matcher would catch `init` and `run` here as bare words; the
    # tightened one requires backticks or code shape.
    assert _ext("we run init checks during init phase") == set()


def test_backticked_bare_word_matches() -> None:
    assert "init" in _ext("call `init` first")
    assert "run" in _ext("the `run` step is mandatory")


def test_snake_case_outside_backticks_matches() -> None:
    out = _ext("see open_store for details")
    assert "open_store" in out


def test_pascal_case_with_two_humps_matches() -> None:
    out = _ext("the FooBar wraps GenerationContext")
    assert "FooBar" in out
    assert "GenerationContext" in out


def test_single_pascal_case_word_does_not_match_outside_backticks() -> None:
    # `Scanner` alone — could be a symbol or a noun. Convention: backtick it
    # if you mean the code.
    assert "Scanner" not in _ext("the Scanner reads files")
    assert "Scanner" in _ext("the `Scanner` reads files")


def test_camel_case_matches() -> None:
    assert "fooBar" in _ext("invoke fooBar to apply")


def test_dotted_form_matches_with_leaf() -> None:
    out = _ext("see docagent.core.orchestrator for the loop")
    assert "docagent.core.orchestrator" in out
    assert "orchestrator" in out  # the leaf, so lookups by tail work


def test_backticked_dotted_form_yields_components() -> None:
    out = _ext("call `Scanner.walk` on the tree")
    assert "Scanner.walk" in out
    assert "walk" in out
    assert "Scanner" in out


def test_all_uppercase_short_words_do_not_match() -> None:
    # AND, OR, NOT, URL, API — common in prose, ambiguous as symbols.
    assert _ext("AND OR NOT match") == set()


def test_underscore_prefixed_private_matches() -> None:
    assert "_private_helper" in _ext("the _private_helper is used internally")
