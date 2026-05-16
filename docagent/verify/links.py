"""Link checker stub. Real impl will validate internal anchors and HEAD-check
external URLs with a local cache."""

from __future__ import annotations

from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    return True, ()
