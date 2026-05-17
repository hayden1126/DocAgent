"""Backend preflight behavior.

When the local ``claude`` CLI is missing, the AgentSDKBackend should raise a
``BackendUnavailableError`` with an actionable install hint — not a deep
``FileNotFoundError`` stack trace from inside the SDK.
"""

from __future__ import annotations

import pytest

from docagent.backends.agent_sdk import AgentSDKBackend, BackendUnavailableError


def test_preflight_passes_when_claude_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "docagent.backends.agent_sdk.shutil.which", lambda name: "/usr/local/bin/claude"
    )
    AgentSDKBackend()._preflight()  # no raise


def test_preflight_raises_when_claude_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("docagent.backends.agent_sdk.shutil.which", lambda name: None)
    with pytest.raises(BackendUnavailableError) as exc_info:
        AgentSDKBackend()._preflight()
    msg = str(exc_info.value)
    assert "claude" in msg.lower()
    assert "path" in msg.lower()


def test_run_surfaces_preflight_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run()`` should also gate on preflight so callers that bypass the CLI
    don't see a deep SDK stack trace."""
    from docagent.backends.base import GenerationRequest

    monkeypatch.setattr("docagent.backends.agent_sdk.shutil.which", lambda name: None)
    with pytest.raises(BackendUnavailableError):
        AgentSDKBackend().run(GenerationRequest(artifact_id="readme", prompt="x", repo_root="/tmp"))  # type: ignore[arg-type]
