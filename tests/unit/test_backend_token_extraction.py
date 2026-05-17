"""Regression tests for token extraction from `AssistantMessage.usage`.

`AssistantMessage.usage` is typed `dict[str, Any] | None` by the
`claude_agent_sdk` types and is emitted *per turn* in an agentic tool-use
loop. The backend accumulates input/output tokens across every assistant
turn — reading only the final `ResultMessage.usage` (the prior
implementation) missed every intermediate turn's input tokens.

These tests pin the contract: dict-shaped per-turn `usage` accumulates,
the `or 0` defense survives `None` keys, and a multi-turn stream produces
the cumulative sum.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from docagent.backends.agent_sdk import AgentSDKBackend
from docagent.backends.base import GenerationRequest

# ---- Fake claude_agent_sdk module --------------------------------------------------

@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeAssistantMessage:
    content: list[Any]
    usage: dict[str, Any] | None = None


@dataclass
class _FakeClaudeAgentOptions:
    """Accepts any kwargs; we don't introspect."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _install_fake_sdk(
    monkeypatch: pytest.MonkeyPatch,
    turns: list[tuple[str, dict[str, Any] | None]],
) -> None:
    """Install a fake `claude_agent_sdk` whose `query` yields one
    `AssistantMessage` per (text, usage) entry in `turns`.
    """

    async def _query(prompt: str, options: Any) -> AsyncIterator[Any]:
        for text, usage in turns:
            yield _FakeAssistantMessage(
                content=[_FakeTextBlock(text=text)],
                usage=usage,
            )

    fake_module = types.ModuleType("claude_agent_sdk")
    fake_module.AssistantMessage = _FakeAssistantMessage  # type: ignore[attr-defined]
    fake_module.ClaudeAgentOptions = _FakeClaudeAgentOptions  # type: ignore[attr-defined]
    fake_module.TextBlock = _FakeTextBlock  # type: ignore[attr-defined]
    fake_module.query = _query  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_module)


def _run(backend: AgentSDKBackend, repo_root: Path) -> Any:
    req = GenerationRequest(artifact_id="readme", prompt="x", repo_root=repo_root)
    return asyncio.run(backend._run_async(req))


def test_single_turn_usage_populates_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sdk(
        monkeypatch,
        [("hi", {"input_tokens": 123, "output_tokens": 45})],
    )
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 123
    assert resp.output_tokens == 45
    assert resp.content == "hi"


def test_none_usage_yields_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_sdk(monkeypatch, [("hi", None)])
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


def test_empty_dict_usage_yields_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_sdk(monkeypatch, [("hi", {})])
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


def test_none_valued_keys_defended_by_or_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Upstream may serialize a missing field as `None`; the `or 0` form must
    coerce it to 0 without raising.
    """
    _install_fake_sdk(
        monkeypatch,
        [("hi", {"input_tokens": None, "output_tokens": 7})],
    )
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 7


def test_multi_turn_usage_accumulates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The agentic SDK emits one `AssistantMessage` per tool-use turn, each
    with its own `usage` dict. Tokens must accumulate across turns; the
    prior implementation that read only the final `ResultMessage.usage`
    silently dropped every intermediate turn.
    """
    _install_fake_sdk(
        monkeypatch,
        [
            ("turn1", {"input_tokens": 100, "output_tokens": 10}),
            ("turn2", {"input_tokens": 200, "output_tokens": 20}),
            ("turn3", {"input_tokens": 300, "output_tokens": 30}),
        ],
    )
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 600
    assert resp.output_tokens == 60
    assert "turn1" in resp.content
    assert "turn3" in resp.content


def test_mixed_present_and_absent_usage_across_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Some turns may legitimately have no usage attached; those count as
    zero and the present-usage turns still accumulate.
    """
    _install_fake_sdk(
        monkeypatch,
        [
            ("a", {"input_tokens": 50, "output_tokens": 5}),
            ("b", None),
            ("c", {"input_tokens": 75, "output_tokens": 8}),
        ],
    )
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 125
    assert resp.output_tokens == 13
