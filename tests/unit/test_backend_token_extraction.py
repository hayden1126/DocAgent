"""Regression tests for token extraction from `ResultMessage.usage`.

`ResultMessage.usage` is typed `dict[str, Any] | None` by the
`claude_agent_sdk` types. Prior to the Phase 5 fix, `agent_sdk._run_async`
used `getattr(usage, "input_tokens", 0)`, which on a dict always returns
the default — silently producing zero token counts in `GenerationResponse`.

These tests pin the contract: dict-shaped `usage` populates the response
fields, and the `or 0` defense survives `None` keys.
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


@dataclass
class _FakeResultMessage:
    usage: dict[str, Any] | None


@dataclass
class _FakeClaudeAgentOptions:
    """Accepts any kwargs; we don't introspect."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch, usage: dict[str, Any] | None) -> None:
    """Install a fake `claude_agent_sdk` module that yields one assistant message
    followed by a `ResultMessage` whose `usage` is the supplied object.
    """

    async def _query(prompt: str, options: Any) -> AsyncIterator[Any]:
        yield _FakeAssistantMessage(content=[_FakeTextBlock(text="hi")])
        yield _FakeResultMessage(usage=usage)

    fake_module = types.ModuleType("claude_agent_sdk")
    fake_module.AssistantMessage = _FakeAssistantMessage  # type: ignore[attr-defined]
    fake_module.ClaudeAgentOptions = _FakeClaudeAgentOptions  # type: ignore[attr-defined]
    fake_module.ResultMessage = _FakeResultMessage  # type: ignore[attr-defined]
    fake_module.TextBlock = _FakeTextBlock  # type: ignore[attr-defined]
    fake_module.query = _query  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_module)


def _run(backend: AgentSDKBackend, repo_root: Path) -> Any:
    req = GenerationRequest(artifact_id="readme", prompt="x", repo_root=repo_root)
    return asyncio.run(backend._run_async(req))


def test_dict_usage_populates_tokens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_sdk(monkeypatch, usage={"input_tokens": 123, "output_tokens": 45})
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 123
    assert resp.output_tokens == 45
    assert resp.content == "hi"


def test_none_usage_yields_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_sdk(monkeypatch, usage=None)
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


def test_empty_dict_usage_yields_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_sdk(monkeypatch, usage={})
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


def test_none_valued_keys_defended_by_or_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Upstream may serialize a missing field as `None`; the `or 0` form must
    coerce it to 0 without raising.
    """
    _install_fake_sdk(monkeypatch, usage={"input_tokens": None, "output_tokens": 7})
    resp = _run(AgentSDKBackend(), tmp_path)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 7
