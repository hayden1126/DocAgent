"""Tests for LiteLLMBackend (Plan 08-03).

Covers:
- Tested-model allowlist (`_TESTED_MODELS` frozenset) + WARN dedup via
  `_warned_allowlist_models`.
- Tool-loop terminates on no tool_calls.
- Tool dispatch (Read/Glob/Grep) routes through.
- `_safe_path` sandbox escapes (parent, absolute, symlink).
- Multi-turn token accumulation (mirrors `test_backend_token_extraction.py`).
- `tc.model_dump()` round-trip on assistant message (Pitfall 4).
- Empty `fn.arguments` doesn't crash.
- `max_turns` exhaustion logs WARN.
- Per-turn cost accumulation via the Wave 2 shim → `cost_usd`.
- OpenRouter opt-in: `extra_body={"usage": {"include": True}}` passed
  when model starts with `openrouter/`, omitted otherwise.
- Missing `litellm` raises `BackendUnavailableError`.

Fakes mirror RESEARCH.md Code Example 2: small attribute-access
dataclasses, sys.modules monkeypatch for the lazy `import litellm` path.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from docagent.backends.base import GenerationRequest

# ---- Fake LiteLLM response shapes ------------------------------------------


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | str | None = None


@dataclass
class _FakeFunction:
    name: str = ""
    arguments: str = "{}"


@dataclass
class _FakeToolCall:
    id: str = "call_1"
    type: str = "function"
    function: _FakeFunction = field(default_factory=_FakeFunction)

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


@dataclass
class _FakeMessage:
    content: str | None = ""
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage = field(default_factory=_FakeMessage)


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice] = field(default_factory=list)
    usage: _FakeUsage | None = None
    model: str = "test"


def _msg(content: str = "", tool_calls: list[_FakeToolCall] | None = None) -> _FakeResponse:
    """Helper: build a terminating response (with content, no tool_calls) or
    a tool-call response."""
    return _FakeResponse(
        choices=[_FakeChoice(message=_FakeMessage(content=content, tool_calls=tool_calls))],
        usage=_FakeUsage(prompt_tokens=10, completion_tokens=5),
    )


# ---- Fake litellm module install ------------------------------------------


def _install_fake_litellm(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_FakeResponse],
) -> dict[str, Any]:
    """Install a fake `litellm` module whose `completion()` pops from
    `responses` and records the last kwargs for spying.

    Returns a dict with a `captured` key holding a list of every kwargs
    dict passed to `completion()`. Tests can inspect it post-run.
    """
    state: dict[str, Any] = {"captured": [], "completion_cost_calls": []}
    queue = list(responses)

    fake = types.ModuleType("litellm")

    def completion(**kwargs: Any) -> _FakeResponse:
        state["captured"].append(kwargs)
        if not queue:
            # Default: terminate with a tiny response so the loop ends.
            return _msg(content="done")
        return queue.pop(0)

    def completion_cost(**kwargs: Any) -> float:
        state["completion_cost_calls"].append(kwargs)
        return 0.001

    fake.completion = completion  # type: ignore[attr-defined]
    fake.completion_cost = completion_cost  # type: ignore[attr-defined]
    fake.drop_params = True  # type: ignore[attr-defined]
    fake.AuthenticationError = type("AuthenticationError", (Exception,), {})  # type: ignore[attr-defined]
    fake.BadRequestError = type("BadRequestError", (Exception,), {})  # type: ignore[attr-defined]
    fake.RateLimitError = type("RateLimitError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return state


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_logger_propagation() -> Generator[None, None, None]:
    """Mirror the propagation fix from test_pricing.py."""
    logger = logging.getLogger("docagent")
    prior = logger.propagate
    logger.propagate = True
    try:
        yield
    finally:
        logger.propagate = prior


@pytest.fixture(autouse=True)
def _reset_dedup_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset both allowlist + pricing dedup sets per test."""
    from docagent.backends import _litellm_pricing, litellm_backend

    monkeypatch.setattr(litellm_backend, "_warned_allowlist_models", set())
    monkeypatch.setattr(_litellm_pricing, "_warned_pricing_models", set())


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A throwaway repo for path-sandbox tests."""
    (tmp_path / "README.md").write_text("hello\nworld\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('x')\n")
    return tmp_path


def _make_request(repo_root: Path) -> GenerationRequest:
    return GenerationRequest(
        artifact_id="readme",
        prompt="Write a README.",
        repo_root=repo_root,
    )


# ---- Allowlist dedup -------------------------------------------------------


def test_allowlist_contains_six_locked_models() -> None:
    """Pin the allowlist content — fail-fast on drift from CONTEXT.md."""
    from docagent.backends.litellm_backend import _TESTED_MODELS

    expected = frozenset({
        "gemini/gemini-2.5-pro",
        "gemini/gemini-2.5-flash",
        "openrouter/anthropic/claude-sonnet-4-6",
        "openrouter/anthropic/claude-opus-4-7",
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-opus-4-7",
    })
    assert expected == _TESTED_MODELS
    # Explicit: Ollama is NOT on the allowlist (spike verdict).
    assert not any(m.startswith("ollama") for m in _TESTED_MODELS)


def test_known_model_no_warn(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="hi")])
    caplog.set_level(logging.WARNING)
    backend = LiteLLMBackend(model="gemini/gemini-2.5-pro")
    backend.run(_make_request(repo_root))
    unsupported = [r for r in caplog.records if "[unsupported-model]" in r.getMessage()]
    assert unsupported == []


def test_unknown_model_warns_once(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="hi")])
    caplog.set_level(logging.WARNING)
    backend = LiteLLMBackend(model="foo/bar")
    backend.run(_make_request(repo_root))
    unsupported = [r for r in caplog.records if "[unsupported-model]" in r.getMessage()]
    assert len(unsupported) == 1
    assert "foo/bar" in unsupported[0].getMessage()


def test_unknown_model_dedup_same_process(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="hi"), _msg(content="hi")])
    caplog.set_level(logging.WARNING)
    backend = LiteLLMBackend(model="foo/bar")
    backend.run(_make_request(repo_root))
    backend.run(_make_request(repo_root))
    unsupported = [r for r in caplog.records if "[unsupported-model]" in r.getMessage()]
    assert len(unsupported) == 1


def test_multiple_unknowns_each_warn_once(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="x") for _ in range(3)])
    caplog.set_level(logging.WARNING)
    LiteLLMBackend(model="foo/bar").run(_make_request(repo_root))
    LiteLLMBackend(model="baz/qux").run(_make_request(repo_root))
    LiteLLMBackend(model="foo/bar").run(_make_request(repo_root))
    unsupported = [r for r in caplog.records if "[unsupported-model]" in r.getMessage()]
    assert len(unsupported) == 2


# ---- Tool-loop termination -------------------------------------------------


def test_single_turn_no_tool_calls(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="Hello world.")])
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6")
    resp = backend.run(_make_request(repo_root))
    assert resp.content == "Hello world."
    assert resp.tool_calls == 0


# ---- Tool dispatch ---------------------------------------------------------


def test_tool_dispatch_read(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """First turn requests a Read; second turn terminates. The tool result
    must reach the second-turn input."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc = _FakeToolCall(
        id="t1",
        function=_FakeFunction(name="Read", arguments=json.dumps({"path": "README.md"})),
    )
    state = _install_fake_litellm(
        monkeypatch,
        [
            _msg(tool_calls=[tc]),
            _msg(content="done."),
        ],
    )
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6")
    resp = backend.run(_make_request(repo_root))
    assert resp.tool_calls == 1
    # Second-turn kwargs.messages should include a tool-role message with
    # the README contents.
    second_msgs = state["captured"][1]["messages"]
    tool_msg = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msg, "expected a tool-role message on second turn"
    assert "hello" in tool_msg[0]["content"]


def test_tool_dispatch_unknown(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc = _FakeToolCall(
        id="t1", function=_FakeFunction(name="Eval", arguments="{}")
    )
    state = _install_fake_litellm(
        monkeypatch, [_msg(tool_calls=[tc]), _msg(content="done.")]
    )
    LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(_make_request(repo_root))
    second_msgs = state["captured"][1]["messages"]
    tool_msg = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msg and tool_msg[0]["content"].startswith("unknown tool")


# ---- Sandbox escapes -------------------------------------------------------


def test_safe_path_refuses_parent_escape(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    assert _safe_path("../../etc/passwd", repo_root) is None


def test_safe_path_refuses_absolute(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    assert _safe_path("/etc/passwd", repo_root) is None


def test_safe_path_refuses_symlink_escape(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    (repo_root / "escape_link").symlink_to("/tmp")
    assert _safe_path("escape_link/somefile", repo_root) is None


def test_safe_path_accepts_repo_relative(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    target = _safe_path("README.md", repo_root)
    assert target is not None
    assert target.relative_to(repo_root) == Path("README.md")


# ---- Multi-turn token accumulation ----------------------------------------


def test_token_accumulation_three_turns(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """3 turns: prompt=[100,80,50], completion=[20,15,10] → in=230 out=45."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc1 = _FakeToolCall(function=_FakeFunction(name="Read", arguments='{"path":"README.md"}'))
    tc2 = _FakeToolCall(function=_FakeFunction(name="Read", arguments='{"path":"src/main.py"}'))

    responses = [
        _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="", tool_calls=[tc1]))],
            usage=_FakeUsage(prompt_tokens=100, completion_tokens=20),
        ),
        _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="", tool_calls=[tc2]))],
            usage=_FakeUsage(prompt_tokens=80, completion_tokens=15),
        ),
        _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="done"))],
            usage=_FakeUsage(prompt_tokens=50, completion_tokens=10),
        ),
    ]
    _install_fake_litellm(monkeypatch, responses)
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(_make_request(repo_root))
    assert resp.input_tokens == 230
    assert resp.output_tokens == 45


def test_token_accumulation_handles_none_usage(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """One turn has usage=None; other turns still sum correctly."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc1 = _FakeToolCall(function=_FakeFunction(name="Read", arguments='{"path":"README.md"}'))
    responses = [
        _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="", tool_calls=[tc1]))],
            usage=None,  # missing usage on first turn
        ),
        _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="done"))],
            usage=_FakeUsage(prompt_tokens=50, completion_tokens=10),
        ),
    ]
    _install_fake_litellm(monkeypatch, responses)
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(_make_request(repo_root))
    assert resp.input_tokens == 50
    assert resp.output_tokens == 10


# ---- tc.model_dump round-trip (Pitfall 4) ---------------------------------


def test_tool_call_serialization_round_trip(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """The assistant message on turn N+1 must include the dumped tool_calls
    list in the standard OpenAI shape."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc = _FakeToolCall(
        id="abc",
        function=_FakeFunction(name="Read", arguments='{"path":"README.md"}'),
    )
    state = _install_fake_litellm(
        monkeypatch, [_msg(tool_calls=[tc]), _msg(content="done")]
    )
    LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(_make_request(repo_root))
    second_msgs = state["captured"][1]["messages"]
    asst = [m for m in second_msgs if m.get("role") == "assistant"]
    assert asst, "expected an assistant message on second turn"
    dumped = asst[0]["tool_calls"]
    assert dumped == [
        {
            "id": "abc",
            "type": "function",
            "function": {"name": "Read", "arguments": '{"path":"README.md"}'},
        }
    ]


# ---- Empty fn.arguments ---------------------------------------------------


def test_empty_tool_call_arguments(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """fn.arguments == "" → falls back to {} via the json.loads guard.
    Tool runs without crashing (Glob with empty pattern returns an error
    string; what matters is no exception)."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc = _FakeToolCall(function=_FakeFunction(name="Glob", arguments=""))
    state = _install_fake_litellm(
        monkeypatch, [_msg(tool_calls=[tc]), _msg(content="ok")]
    )
    LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(_make_request(repo_root))
    second_msgs = state["captured"][1]["messages"]
    tool_msg = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msg  # got SOMETHING back, no crash


# ---- max_turns exhaustion -------------------------------------------------


def test_max_turns_exhausted_logs_warn(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Model never stops calling tools → loop exits after max_turns, WARN."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc = _FakeToolCall(
        function=_FakeFunction(name="Read", arguments='{"path":"README.md"}')
    )
    # Build a generator of always-tool-calling responses; let it be unbounded
    # (queue exhausts -> default 'done'; max_turns of 3 caps before that).
    responses = [_msg(tool_calls=[tc]) for _ in range(10)]
    _install_fake_litellm(monkeypatch, responses)
    caplog.set_level(logging.WARNING)
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6", max_turns=3)
    backend.run(_make_request(repo_root))
    msgs = [r.getMessage() for r in caplog.records]
    assert any("max_turns=3 exhausted" in m for m in msgs), f"got: {msgs}"


# ---- Per-turn cost accumulation -------------------------------------------


def test_cost_accumulation_sums_across_turns(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """Three turns → cost_for_response monkeypatched to [0.001, 0.002, 0.0005]
    → resp.cost_usd == 0.0035 (within float tolerance)."""
    from docagent.backends import litellm_backend

    tc = _FakeToolCall(function=_FakeFunction(name="Read", arguments='{"path":"README.md"}'))
    responses = [
        _msg(tool_calls=[tc]),
        _msg(tool_calls=[tc]),
        _msg(content="done"),
    ]
    _install_fake_litellm(monkeypatch, responses)

    costs = iter([0.001, 0.002, 0.0005])

    def fake_cost(model: str, response: Any) -> float:
        return next(costs)

    monkeypatch.setattr(
        "docagent.backends._litellm_pricing.cost_for_response", fake_cost
    )
    resp = litellm_backend.LiteLLMBackend(
        model="anthropic/claude-sonnet-4-6"
    ).run(_make_request(repo_root))
    assert resp.cost_usd is not None
    assert abs(resp.cost_usd - 0.0035) < 1e-9


def test_cost_usd_attached_when_known_model(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """For an allowlist model, resp.cost_usd is a float (not None)."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="hi")])
    resp = LiteLLMBackend(model="gemini/gemini-2.5-pro").run(_make_request(repo_root))
    assert isinstance(resp.cost_usd, float)


def test_cost_usd_attached_when_unknown_model(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """For unknown model + Tier-3 zero: cost_usd is 0.0 (NOT None)."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, [_msg(content="hi")])

    # Force Tier 3 by making completion_cost raise.
    def raise_cost(**_kw: Any) -> float:
        raise Exception("unmapped")

    sys.modules["litellm"].completion_cost = raise_cost  # type: ignore[attr-defined]
    resp = LiteLLMBackend(model="foo/bar").run(_make_request(repo_root))
    assert resp.cost_usd == 0.0


# ---- OpenRouter opt-in -----------------------------------------------------


def test_openrouter_passes_usage_include(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """openrouter/* → completion() kwargs include extra_body.usage.include=True."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    state = _install_fake_litellm(monkeypatch, [_msg(content="ok")])
    LiteLLMBackend(model="openrouter/anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    kw = state["captured"][0]
    assert "extra_body" in kw
    assert kw["extra_body"] == {"usage": {"include": True}}


def test_non_openrouter_omits_usage_include(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    from docagent.backends.litellm_backend import LiteLLMBackend

    state = _install_fake_litellm(monkeypatch, [_msg(content="ok")])
    LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(_make_request(repo_root))
    kw = state["captured"][0]
    # Either missing entirely, or present without the usage.include flag.
    assert "extra_body" not in kw or kw.get("extra_body", {}).get("usage", {}).get(
        "include"
    ) is not True


# ---- BackendUnavailableError on missing litellm ---------------------------


def test_missing_litellm_raises_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """ImportError → BackendUnavailableError with pip-install hint."""
    from docagent.backends.litellm_backend import (
        BackendUnavailableError,
        LiteLLMBackend,
    )

    # Block `import litellm`.
    monkeypatch.delitem(sys.modules, "litellm", raising=False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__  # type: ignore[index]

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "litellm" or name.startswith("litellm."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6")
    with pytest.raises(BackendUnavailableError) as exc:
        backend.run(_make_request(repo_root))
    assert "pip install docagent[multi]" in str(exc.value)
