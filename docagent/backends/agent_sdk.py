"""Claude Agent SDK backend — the canonical v1 backend.

Lazy-imports the SDK so unit tests and `--help` work without it installed.
The actual tool-use loop wiring is intentionally TODO: the SDK's surface has
moved in recent releases and the integration deserves a dedicated patch with
prompt caching enabled.
"""

from __future__ import annotations

from docagent.backends.base import GenerationRequest, GenerationResponse


class AgentSDKBackend:
    name = "claude-agent-sdk"

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        system_prompt: str | None = None,
        enable_cache: bool = True,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt or (
            "You are DocAgent, an autonomous repository documentation agent. "
            "Read the repo using the available tools and produce accurate, "
            "grounded documentation. Every non-trivial claim must carry a "
            "<!-- ground: path:line-range --> citation."
        )
        self.enable_cache = enable_cache

    def run(self, request: GenerationRequest) -> GenerationResponse:
        # TODO: wire claude_agent_sdk.ClaudeAgent with Read/Grep/Glob/Edit tools
        # scoped to request.repo_root, run the loop up to max_iterations, and
        # return the final assistant message. Enable cache_control on the
        # system prompt when self.enable_cache is True.
        raise NotImplementedError(
            "AgentSDKBackend.run is not yet wired. See docagent/backends/agent_sdk.py."
        )
