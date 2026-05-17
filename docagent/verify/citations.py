"""Citation resolver.

Scans for `<!-- ground: path:line-start-line-end -->` markers and confirms
each refers to a real file and an existing line range. AST-based symbol
matching is a follow-up patch; v1 verifies existence only.

The citation grammar lives in :mod:`docagent.citations` — this gate consumes
it. Do not redefine the regex here.
"""

from __future__ import annotations

from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext
from docagent.citations import iter_citations


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    findings: list[str] = []
    ok = True
    for citation in iter_citations(patch.new_content):
        target = ctx.repo_root / citation.path
        if not target.exists():
            findings.append(f"missing file: {citation.path}")
            ok = False
            continue
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            findings.append(f"{citation.path}: {exc}")
            ok = False
            continue
        if citation.line_start < 1 or citation.line_end > len(lines):
            findings.append(
                f"{citation.path}: range {citation.line_start}-{citation.line_end} "
                f"exceeds file ({len(lines)} lines)"
            )
            ok = False
    return ok, findings
