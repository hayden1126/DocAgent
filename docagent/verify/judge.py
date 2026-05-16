"""LLM-as-judge gate. Last in the pipeline; reasons about accuracy and
grounding against the cited source ranges. Non-blocking by default."""

from __future__ import annotations

from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    return True, ()  # TODO: wire a single-turn judge call against ctx.backend
