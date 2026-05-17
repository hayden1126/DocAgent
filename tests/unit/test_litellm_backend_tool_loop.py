"""Tests closing the 9 spike-prototype gaps + RateLimitError retry
behavior (Plan 08-05).

Reuses the fake-litellm pattern from `test_litellm_backend.py`. The
only NEW behavior in 08-05's code is the RateLimitError single-retry
branch; everything else here is regression-pinning for gaps already
closed by 08-01 and 08-03.
"""

from __future__ import annotations

import logging
import sys
import time
import types
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from docagent.backends.base import GenerationRequest

# ---- Fake LiteLLM shapes (mirror test_litellm_backend.py) ------------------


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None


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
    return _FakeResponse(
        choices=[_FakeChoice(message=_FakeMessage(content=content, tool_calls=tool_calls))],
        usage=_FakeUsage(prompt_tokens=10, completion_tokens=5),
    )


def _install_fake_litellm(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_FakeResponse],
    raises_per_call: list[Exception | None] | None = None,
) -> dict[str, Any]:
    """Install a fake `litellm` module supporting per-call raises.

    `raises_per_call[i]` if not None is raised on the (i+1)-th call;
    otherwise the next entry from `responses` is returned.
    """
    state: dict[str, Any] = {"captured": [], "call_count": 0}
    queue = list(responses)
    raise_queue = list(raises_per_call or [])

    fake = types.ModuleType("litellm")

    def completion(**kwargs: Any) -> _FakeResponse:
        state["captured"].append(kwargs)
        state["call_count"] += 1
        if raise_queue:
            exc = raise_queue.pop(0)
            if exc is not None:
                raise exc
        if not queue:
            return _msg(content="done")
        return queue.pop(0)

    fake.completion = completion  # type: ignore[attr-defined]
    fake.completion_cost = lambda **kw: 0.001  # type: ignore[attr-defined]
    fake.drop_params = True  # type: ignore[attr-defined]
    fake.AuthenticationError = type("AuthenticationError", (Exception,), {})  # type: ignore[attr-defined]
    fake.BadRequestError = type("BadRequestError", (Exception,), {})  # type: ignore[attr-defined]
    fake.RateLimitError = type("RateLimitError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return state


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_logger_propagation() -> Generator[None, None, None]:
    logger = logging.getLogger("docagent")
    prior = logger.propagate
    logger.propagate = True
    try:
        yield
    finally:
        logger.propagate = prior


@pytest.fixture(autouse=True)
def _reset_dedup_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    from docagent.backends import _litellm_pricing, litellm_backend

    monkeypatch.setattr(litellm_backend, "_warned_allowlist_models", set())
    monkeypatch.setattr(_litellm_pricing, "_warned_pricing_models", set())


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("hi\n")
    return tmp_path


def _make_request(repo_root: Path) -> GenerationRequest:
    return GenerationRequest(
        artifact_id="readme", prompt="x", repo_root=repo_root
    )


# ---- Retry behavior --------------------------------------------------------


def test_rate_limit_error_retries_once_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """First call raises RateLimitError, second call returns terminating
    response. sleep(2) called once. resp.content matches second call."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    state = _install_fake_litellm(
        monkeypatch,
        responses=[_msg(content="recovered")],
        raises_per_call=[None],  # placeholder; we'll set below
    )
    # Install RateLimitError on the first call by replacing the completion
    # function dynamically.
    fake = sys.modules["litellm"]
    real_completion = fake.completion  # type: ignore[attr-defined]
    call_count = {"n": 0}

    def first_raises_then_passes(**kwargs: Any) -> _FakeResponse:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise fake.RateLimitError("throttled")  # type: ignore[attr-defined]
        return real_completion(**kwargs)

    fake.completion = first_raises_then_passes  # type: ignore[attr-defined]

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    assert resp.content == "recovered"
    assert call_count["n"] == 2  # one retry
    assert sleeps == [2]  # exactly one sleep, 2 seconds
    # state["call_count"] is only the calls that reached real_completion
    assert state["call_count"] == 1


def test_rate_limit_error_retries_once_and_fails(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """Both calls raise RateLimitError. Error propagates."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, responses=[])
    fake = sys.modules["litellm"]
    call_count = {"n": 0}

    def always_raises(**_kwargs: Any) -> _FakeResponse:
        call_count["n"] += 1
        raise fake.RateLimitError("throttled")  # type: ignore[attr-defined]

    fake.completion = always_raises  # type: ignore[attr-defined]
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    with pytest.raises(Exception) as exc_info:
        LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
            _make_request(repo_root)
        )
    assert "throttled" in str(exc_info.value)
    assert call_count["n"] == 2  # one retry, both failed


def test_bad_request_error_does_not_retry(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """BadRequestError propagates immediately. No retry, no sleep."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(monkeypatch, responses=[])
    fake = sys.modules["litellm"]
    call_count = {"n": 0}

    def raises_bad_request(**_kwargs: Any) -> _FakeResponse:
        call_count["n"] += 1
        raise fake.BadRequestError("bad input")  # type: ignore[attr-defined]

    fake.completion = raises_bad_request  # type: ignore[attr-defined]
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(Exception) as exc_info:
        LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
            _make_request(repo_root)
        )
    assert "bad input" in str(exc_info.value)
    assert call_count["n"] == 1  # NO retry
    assert sleeps == []  # no sleep


def test_authentication_error_wraps_as_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """AuthenticationError -> BackendUnavailableError mentioning all
    three env var names."""
    from docagent.backends.litellm_backend import (
        BackendUnavailableError,
        LiteLLMBackend,
    )

    _install_fake_litellm(monkeypatch, responses=[])
    fake = sys.modules["litellm"]

    def raises_auth(**_kwargs: Any) -> _FakeResponse:
        raise fake.AuthenticationError("no key")  # type: ignore[attr-defined]

    fake.completion = raises_auth  # type: ignore[attr-defined]
    with pytest.raises(BackendUnavailableError) as exc_info:
        LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
            _make_request(repo_root)
        )
    msg = str(exc_info.value)
    assert "GEMINI_API_KEY" in msg
    assert "OPENROUTER_API_KEY" in msg
    assert "ANTHROPIC_API_KEY" in msg


# ---- tc.model_dump contract regression (Pitfall 4) -------------------------


@pytest.mark.skipif(
    "litellm" not in sys.modules
    and pytest.importorskip("litellm", reason="needed for contract pin").__name__
    is None,
    reason="litellm not installed",
)
def test_litellm_tool_call_model_dump_contract() -> None:
    """Pin LiteLLM 1.85's `model_dump()` contract on
    ChatCompletionMessageToolCall. If a future LiteLLM rev changes the
    dict shape, this test fails fast."""
    pytest.importorskip("litellm")
    from litellm.types.utils import ChatCompletionMessageToolCall, Function

    tc = ChatCompletionMessageToolCall(
        id="abc", type="function", function=Function(name="Read", arguments='{"path":"x"}')
    )
    dumped = tc.model_dump()
    assert dumped["id"] == "abc"
    assert dumped["type"] == "function"
    assert dumped["function"]["name"] == "Read"
    assert dumped["function"]["arguments"] == '{"path":"x"}'


# ---- Usage attribute (Pitfall 3) ------------------------------------------


def test_usage_attribute_object_not_dict(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """Backend uses getattr on usage -- attribute object works; a dict
    would silently return 0 via the default."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    # First case: attribute access works.
    _install_fake_litellm(
        monkeypatch,
        responses=[
            _FakeResponse(
                choices=[_FakeChoice(message=_FakeMessage(content="ok"))],
                usage=_FakeUsage(prompt_tokens=42, completion_tokens=7),
            )
        ],
    )
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    assert resp.input_tokens == 42
    assert resp.output_tokens == 7


def test_usage_none_skipped(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """usage=None on a turn: tokens for that turn contribute 0, no crash."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    _install_fake_litellm(
        monkeypatch,
        responses=[
            _FakeResponse(
                choices=[_FakeChoice(message=_FakeMessage(content="ok"))],
                usage=None,
            )
        ],
    )
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


def test_usage_missing_prompt_tokens(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """usage with only completion_tokens: prompt contribution 0, completion still added."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    @dataclass
    class _UsageMissingPrompt:
        # Only completion_tokens; no prompt_tokens attribute.
        completion_tokens: int = 11

    resp_fake = _FakeResponse(
        choices=[_FakeChoice(message=_FakeMessage(content="ok"))],
        usage=_UsageMissingPrompt(),  # type: ignore[arg-type]
    )
    _install_fake_litellm(monkeypatch, responses=[resp_fake])
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    assert resp.input_tokens == 0
    assert resp.output_tokens == 11


# ---- Sandbox escape coverage (extends 08-03) ------------------------------


def test_safe_path_refuses_dotdot_chain(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    assert _safe_path("../../../../etc/passwd", repo_root) is None


def test_safe_path_refuses_absolute_root(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    assert _safe_path("/etc/passwd", repo_root) is None


def test_safe_path_refuses_symlink_to_outside(repo_root: Path) -> None:
    from docagent.backends.litellm_backend import _safe_path

    (repo_root / "link").symlink_to("/tmp")
    assert _safe_path("link/something", repo_root) is None


# ---- Empty fn.arguments + no choices --------------------------------------


def test_fn_arguments_empty_string_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """fn.arguments == '' -> tool runs with {} args."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    tc = _FakeToolCall(function=_FakeFunction(name="Glob", arguments=""))
    state = _install_fake_litellm(
        monkeypatch, responses=[_msg(tool_calls=[tc]), _msg(content="ok")]
    )
    LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    second_msgs = state["captured"][1]["messages"]
    tool_msg = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msg, "expected tool response on second turn"


def test_response_choices_empty_skips_turn(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """First turn has choices=[], second turn returns terminating response.
    Backend continues the loop on the empty turn and uses turn 2."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    empty_resp = _FakeResponse(choices=[], usage=_FakeUsage(prompt_tokens=5))
    state = _install_fake_litellm(
        monkeypatch, responses=[empty_resp, _msg(content="ok")]
    )
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    assert resp.content == "ok"
    assert state["call_count"] == 2


# ---- tool_calls is None ---------------------------------------------------


def test_tool_calls_none_terminates(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """tool_calls=None on the message -> loop terminates same as []."""
    from docagent.backends.litellm_backend import LiteLLMBackend

    resp_fake = _FakeResponse(
        choices=[_FakeChoice(message=_FakeMessage(content="done", tool_calls=None))],
        usage=_FakeUsage(prompt_tokens=5, completion_tokens=2),
    )
    _install_fake_litellm(monkeypatch, responses=[resp_fake])
    resp = LiteLLMBackend(model="anthropic/claude-sonnet-4-6").run(
        _make_request(repo_root)
    )
    assert resp.content == "done"


# ---- BackendUnavailableError distinction ----------------------------------


def test_missing_litellm_install_error_distinct_from_missing_api_key(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path
) -> None:
    """Two distinct BackendUnavailableError flavors:
    (a) ImportError -> 'pip install docagent[multi]' hint.
    (b) AuthenticationError -> env-var-names hint.
    Both produce friendly messages; different content."""
    from docagent.backends.litellm_backend import (
        BackendUnavailableError,
        LiteLLMBackend,
    )

    # Case (a): block import.
    monkeypatch.delitem(sys.modules, "litellm", raising=False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__  # type: ignore[index]

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "litellm" or name.startswith("litellm."):
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6")
    with pytest.raises(BackendUnavailableError) as install_err:
        backend.run(_make_request(repo_root))
    install_msg = str(install_err.value)
    assert "pip install docagent[multi]" in install_msg

    # Case (b): unblock import, raise AuthenticationError on completion.
    monkeypatch.setattr("builtins.__import__", real_import)
    _install_fake_litellm(monkeypatch, responses=[])
    fake = sys.modules["litellm"]
    fake.completion = lambda **_k: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        fake.AuthenticationError("missing key")  # type: ignore[attr-defined]
    )
    with pytest.raises(BackendUnavailableError) as auth_err:
        backend.run(_make_request(repo_root))
    auth_msg = str(auth_err.value)
    assert "ANTHROPIC_API_KEY" in auth_msg
    # Messages are distinct in content.
    assert install_msg != auth_msg
