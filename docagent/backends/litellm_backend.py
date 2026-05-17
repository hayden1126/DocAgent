"""LiteLLM backend — multi-provider routing.

Drives a tool-use loop via `litellm.completion(..., tools=[...])` for any
provider LiteLLM speaks (`gemini/<model>`, `openrouter/<provider>/<model>`,
`anthropic/<model>`, etc.). Exposes the same `LLMBackend` protocol as
`AgentSDKBackend`. Gated behind `pip install docagent[multi]`.

Tool surface: Read, Glob, Grep — same as `AgentSDKBackend`, but invoked
as plain Python functions (no MCP server). Sandboxed to `request.repo_root`
to match the `permission_mode="bypassPermissions"` ergonomics without
exposing the wider filesystem.

See: `.planning/decisions/0001-phase-8-multi-provider-backend.md`.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docagent._logging import get_logger
from docagent.backends.base import GenerationRequest, GenerationResponse

# Silence LiteLLM's Bedrock/SageMaker pre-load WARN lines that fire when the
# `litellm` package is imported. Set at module-load time so the silencer is
# active BEFORE any `import litellm` inside `run()`. Cosmetic — no PII in
# the warnings. (Pitfall 6 in RESEARCH.md.)
logging.getLogger("LiteLLM").setLevel(logging.ERROR)

_log = get_logger("litellm_backend")

_SYSTEM_PROMPT = (
    "You are DocAgent, an autonomous repository documentation agent. "
    "Use the Read, Glob, and Grep tools to inspect the repository at the "
    "current working directory. Produce accurate, concise documentation "
    "grounded in real code. Every non-trivial factual claim must carry a "
    "`<!-- ground: path:line-start-line-end -->` HTML comment immediately "
    "after the sentence it grounds; paths are relative to the repo root. "
    "Do not invent files, symbols, commands, or behavior you have not "
    "verified by reading the source."
)

_TOOLS_SPEC: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read a file from the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative POSIX path."},
                    "offset": {"type": "integer", "description": "Optional 1-based line start."},
                    "limit": {"type": "integer", "description": "Optional max lines to read."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": "List files matching a glob pattern, repo-relative.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py'."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": "Search file contents with a regex; returns matching path:line lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python regex."},
                    "path_glob": {
                        "type": "string",
                        "description": "Optional file glob to restrict the search.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


class BackendUnavailableError(RuntimeError):
    """LiteLLM not installed or model rejected by provider."""


@dataclass
class LiteLLMBackend:
    """Multi-provider backend via LiteLLM. Routes to Gemini, OpenRouter,
    Anthropic-direct, and any other provider LiteLLM speaks; gated behind
    `pip install docagent[multi]`."""

    name: str = "litellm"
    model: str = "anthropic/claude-sonnet-4-6"
    max_turns: int = 24

    extras: dict[str, object] = field(default_factory=dict)

    def run(self, request: GenerationRequest) -> GenerationResponse:
        try:
            import litellm
            from litellm import completion
        except ImportError as exc:
            raise BackendUnavailableError(
                "The `litellm` package is not installed. "
                "Install it with `pip install docagent[multi]`."
            ) from exc

        litellm.drop_params = True

        repo_root = request.repo_root.resolve()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": request.prompt},
        ]

        input_tokens = 0
        output_tokens = 0
        tool_calls_total = 0
        chunks: list[str] = []

        for _turn in range(self.max_turns):
            try:
                response = completion(
                    model=self.model,
                    messages=messages,
                    tools=_TOOLS_SPEC,
                    tool_choice="auto",
                )
            except litellm.AuthenticationError as exc:  # type: ignore[attr-defined]
                raise BackendUnavailableError(
                    f"LiteLLM authentication failed for model {self.model!r}. "
                    f"Ensure the appropriate API key env var is set (GEMINI_API_KEY, "
                    f"OPENROUTER_API_KEY, or ANTHROPIC_API_KEY)."
                ) from exc
            usage = getattr(response, "usage", None)
            if usage is not None:
                input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                output_tokens += getattr(usage, "completion_tokens", 0) or 0

            if not response.choices:
                continue

            choice = response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if msg.content:
                chunks.append(msg.content)

            if not tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in tool_calls],
                }
            )

            for tc in tool_calls:
                tool_calls_total += 1
                fn = tc.function
                try:
                    args = json.loads(fn.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _dispatch_tool(fn.name, args, repo_root)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )
        else:
            _log.warning(
                "litellm_backend %s: max_turns=%d exhausted without terminating turn",
                request.artifact_id, self.max_turns,
            )

        content = "\n".join(chunks).strip()
        _log.debug(
            "litellm_backend %s: %d tool_calls, %d in, %d out tokens, %d chars",
            request.artifact_id, tool_calls_total, input_tokens, output_tokens, len(content),
        )
        return GenerationResponse(
            content=content,
            tool_calls=tool_calls_total,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---- Tool dispatch ---------------------------------------------------------


def _dispatch_tool(name: str, args: dict[str, Any], repo_root: Path) -> str:
    if name == "Read":
        return _read(args, repo_root)
    if name == "Glob":
        return _glob(args, repo_root)
    if name == "Grep":
        return _grep(args, repo_root)
    return f"unknown tool: {name}"


def _safe_path(rel: str, repo_root: Path) -> Path | None:
    """Resolve `rel` under `repo_root`, refusing escapes."""
    target = (repo_root / rel).resolve()
    try:
        target.relative_to(repo_root)
    except ValueError:
        return None
    return target


def _read(args: dict[str, Any], repo_root: Path) -> str:
    rel = str(args.get("path", ""))
    target = _safe_path(rel, repo_root)
    if target is None or not target.is_file():
        return f"error: not a file: {rel}"
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    offset = int(args.get("offset", 1)) - 1
    limit = int(args.get("limit", len(lines)))
    sliced = lines[max(0, offset) : max(0, offset) + max(0, limit)]
    numbered = [f"{i + offset + 1}\t{ln}" for i, ln in enumerate(sliced)]
    return "\n".join(numbered)


def _glob(args: dict[str, Any], repo_root: Path) -> str:
    pattern = str(args.get("pattern", ""))
    if not pattern:
        return "error: empty pattern"
    matches: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
            matches.append(rel)
    matches.sort()
    return "\n".join(matches[:500]) or "(no matches)"


def _grep(args: dict[str, Any], repo_root: Path) -> str:
    pattern = str(args.get("pattern", ""))
    path_glob = str(args.get("path_glob", "**/*"))
    if not pattern:
        return "error: empty pattern"
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"error: bad regex: {exc}"
    hits: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if not (fnmatch.fnmatch(rel, path_glob) or fnmatch.fnmatch(path.name, path_glob)):
            continue
        try:
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                if regex.search(line):
                    hits.append(f"{rel}:{lineno}:{line}")
                    if len(hits) >= 500:
                        return "\n".join(hits)
        except OSError:
            continue
    return "\n".join(hits) or "(no matches)"
