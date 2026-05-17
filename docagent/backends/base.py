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
    # Phase 8: per-call cost USD, populated by `LiteLLMBackend` via the
    # `_litellm_pricing.cost_for_response` shim. `None` means "pricing not
    # attached" (SDK path); a float (incl. 0.0) means "backend already
    # computed cost." The orchestrator threads this through `BudgetTracker.add`
    # as the `external_cost` override.
    cost_usd: float | None = None


@runtime_checkable
class LLMBackend(Protocol):
    name: str

    def run(self, request: GenerationRequest) -> GenerationResponse: ...
