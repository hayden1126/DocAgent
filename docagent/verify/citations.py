"""Citation resolver.

Scans for `<!-- ground: path:line-start-line-end -->` markers and confirms
each refers to a real file and an existing line range. AST-based symbol
matching is a follow-up patch; v1 verifies existence only.
"""

from __future__ import annotations

import re
from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext

CITATION_RE = re.compile(rb"<!--\s*ground:\s*([^:\s]+):(\d+)(?:-(\d+))?\s*-->")


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    findings: list[str] = []
    ok = True
    for match in CITATION_RE.finditer(patch.new_content):
        rel = match.group(1).decode("utf-8")
        line_start = int(match.group(2))
        line_end = int(match.group(3) or match.group(2))
        target = ctx.repo_root / rel
        if not target.exists():
            findings.append(f"missing file: {rel}")
            ok = False
            continue
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            findings.append(f"{rel}: {exc}")
            ok = False
            continue
        if line_start < 1 or line_end > len(lines):
            findings.append(f"{rel}: range {line_start}-{line_end} exceeds file ({len(lines)} lines)")
            ok = False
    return ok, findings
