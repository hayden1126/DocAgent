"""Tests for the in-repo JSONC stripper used by TS module discovery.

Covers: pure JSON passthrough, // line comments, /* */ block comments
(single-line and multi-line), trailing commas in objects and arrays,
URL preservation in strings (negative-lookbehind on `//`), block-first
ordering (a `//` inside a block comment must not survive), and
caller-handled invalid input (json.JSONDecodeError surfaces).
"""

from __future__ import annotations

import json

import pytest

from docagent.artifacts._jsonc import parse_jsonc


def test_pure_json_passthrough() -> None:
    assert parse_jsonc('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_line_comment() -> None:
    assert parse_jsonc('{\n  // hi\n  "a": 1\n}') == {"a": 1}


def test_block_comment_single_line() -> None:
    assert parse_jsonc('{/* hi */ "a": 1}') == {"a": 1}


def test_block_comment_multi_line() -> None:
    assert parse_jsonc('{\n  /*\n   hi\n  */\n  "a": 1\n}') == {"a": 1}


def test_trailing_comma_object() -> None:
    assert parse_jsonc('{"a": 1,}') == {"a": 1}


def test_trailing_comma_array() -> None:
    assert parse_jsonc('{"a": [1, 2,]}') == {"a": [1, 2]}


def test_combined() -> None:
    text = """{
  // tsconfig top
  "compilerOptions": {
    "target": "es2020", /* version */
    "strict": true,
  },
  "include": ["src/**/*",],
}
"""
    parsed = parse_jsonc(text)
    assert parsed["compilerOptions"]["target"] == "es2020"
    assert parsed["compilerOptions"]["strict"] is True
    assert parsed["include"] == ["src/**/*"]


def test_url_preserved_in_string() -> None:
    text = '{"url": "https://example.com//foo"}'
    assert parse_jsonc(text)["url"] == "https://example.com//foo"


def test_block_comment_containing_double_slash() -> None:
    # Block comments are stripped first, so the `//` inside never reaches
    # the line-comment regex.
    text = '{/* line 1 // not a comment */ "a": 1}'
    assert parse_jsonc(text) == {"a": 1}


def test_pure_json_with_newlines() -> None:
    text = '{\n  "a": 1,\n  "b": 2\n}'
    assert parse_jsonc(text) == {"a": 1, "b": 2}


def test_invalid_input_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_jsonc('{"a": ,}')


def test_real_world_tsconfig_sample() -> None:
    text = """{
  // tsconfig.json
  "compilerOptions": {
    "target": "es2020",
    /* module system */
    "module": "esnext",
    "strict": true,
    "rootDir": "./src",
    "outDir": "./dist",
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
"""
    parsed = parse_jsonc(text)
    assert parsed["compilerOptions"]["target"] == "es2020"
    assert parsed["compilerOptions"]["module"] == "esnext"
    assert parsed["include"] == ["src/**/*"]
