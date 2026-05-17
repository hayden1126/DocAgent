"""LLM-as-judge gate. Last in the pipeline; reasons about accuracy and
grounding against the cited source ranges. Non-blocking by default.

The gate is not yet implemented — it reports a single ``skipped`` finding so
that ``verify_ok=True`` does not implicitly claim the judge passed. Wiring
needs a single-turn call against ``ctx.backend`` plus a small prompt that
quotes the patch and asks for grounded inconsistencies.
"""

from __future__ import annotations

from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    return True, ("skipped: judge not yet implemented",)
