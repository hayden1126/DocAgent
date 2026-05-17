"""Claude Agent SDK backend.

Wraps the async `claude_agent_sdk.query()` in a synchronous interface. The
SDK speaks to the local `claude` CLI, so prompt caching, tool scoping, and
sandboxing are all delegated to it.

For read-only artifact generation (README, AGENTS.md, llms.txt, CLAUDE.md,
docs/) we pass `permission_mode="bypassPermissions"` and restrict tools to
Read/Glob/Grep. In-place artifacts that mutate source (python_docstrings)
will use a separate, narrower configuration when wired.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field

from docagent._logging import get_logger
from docagent.backends.base import GenerationRequest, GenerationResponse

_log = get_logger("backend.agent_sdk")


class BackendUnavailableError(RuntimeError):
    """Raised when the backend's runtime dependencies are missing.

    Carries an actionable install/setup hint suitable for direct CLI display.
    """


_CLAUDE_INSTALL_HINT = (
    "DocAgent's Claude Agent SDK backend requires the `claude` CLI on PATH.\n"
    "Install Claude Code: https://docs.claude.com/en/docs/claude-code/setup\n"
    "Or set DOCAGENT_BACKEND=<other> once additional backends are supported."
)


@dataclass
class AgentSDKBackend:
    name: str = "claude-agent-sdk"
    model: str | None = None  # None ⇒ SDK default
    system_prompt: str = (
        "You are DocAgent, an autonomous repository documentation agent. "
        "Use the Read, Glob, and Grep tools to inspect the repository at the "
        "current working directory. Produce accurate, concise documentation "
        "grounded in real code. Every non-trivial factual claim must carry a "
        "`<!-- ground: path:line-start-line-end -->` HTML comment immediately "
        "after the sentence it grounds; paths are relative to the repo root. "
        "Do not invent files, symbols, commands, or behavior you have not "
        "verified by reading the source."
    )
    tools: tuple[str, ...] = ("Read", "Glob", "Grep")
    max_turns: int = 24
    permission_mode: str = "bypassPermissions"

    extras: dict[str, object] = field(default_factory=dict)

    def run(self, request: GenerationRequest) -> GenerationResponse:
        self._preflight()
        try:
            return asyncio.run(self._run_async(request))
        except FileNotFoundError as exc:
            # The SDK shells out to `claude`; FileNotFoundError surfaces if
            # the CLI is missing or its dependencies aren't on PATH.
            raise BackendUnavailableError(_CLAUDE_INSTALL_HINT) from exc

    def _preflight(self) -> None:
        if shutil.which("claude") is None:
            raise BackendUnavailableError(_CLAUDE_INSTALL_HINT)

    async def _run_async(self, request: GenerationRequest) -> GenerationResponse:
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                TextBlock,
                query,
            )
        except ImportError as exc:
            raise BackendUnavailableError(
                "The `claude-agent-sdk` package is not installed. "
                "Install it with `pip install claude-agent-sdk` "
                "(already a DocAgent dependency — re-install with `pip install -e .`)."
            ) from exc

        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            tools=list(self.tools),
            allowed_tools=list(self.tools),
            permission_mode=self.permission_mode,  # type: ignore[arg-type]
            cwd=str(request.repo_root),
            max_turns=self.max_turns,
            model=self.model,
        )

        chunks: list[str] = []
        tool_calls = 0
        input_tokens = 0
        output_tokens = 0

        async for msg in query(prompt=request.prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
                    else:
                        # ToolUseBlock, ThinkingBlock, etc. — count tool calls
                        if type(block).__name__ == "ToolUseBlock":
                            tool_calls += 1
            elif isinstance(msg, ResultMessage):
                usage = getattr(msg, "usage", None)
                if usage:
                    # `usage` is `dict[str, Any] | None` per claude_agent_sdk
                    # types.py; the previous `getattr` form silently returned 0.
                    # `or 0` defends against the value itself being None.
                    input_tokens = usage.get("input_tokens", 0) or 0
                    output_tokens = usage.get("output_tokens", 0) or 0

        content = "\n".join(chunks).strip()
        _log.debug(
            "agent_sdk %s: %d tool_calls, %d in, %d out tokens, %d chars",
            request.artifact_id, tool_calls, input_tokens, output_tokens, len(content),
        )
        return GenerationResponse(
            content=content,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
