"""LLMBackend protocol.

v1 ships a single backend (`AgentSDKBackend`). The protocol is here so that
artifact code never imports a concrete backend — the orchestrator wires one in.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    artifact_id: str
    prompt: str
    repo_root: Path
    max_iterations: int = 24
    extras: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    content: str
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class LLMBackend(Protocol):
    name: str

    def run(self, request: GenerationRequest) -> GenerationResponse: ...
