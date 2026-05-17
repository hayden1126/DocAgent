"""Canonical citation grammar shared by every gate, resolver, and tool.

Citations take the form ``<!-- ground: path:start-end -->`` (or ``path:line``)
where ``path`` is a repo-relative POSIX path. The path may not contain ``:`` or
whitespace; ``:`` is reserved as the path/line-range delimiter. This restriction
is intentional and documented in artifact prompts.

Keeping the regex in one module means the verifier gate, the affected-artifact
resolver, and any future tooling cannot drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# bytes pattern — every caller operates on raw artifact bytes to avoid
# encoding pitfalls on mixed-content inputs.
CITATION_RE: re.Pattern[bytes] = re.compile(
    rb"<!--\s*ground:\s*([^:\s]+):(\d+)(?:-(\d+))?\s*-->"
)


@dataclass(frozen=True, slots=True)
class Citation:
    path: str
    line_start: int
    line_end: int


def iter_citations(content: bytes) -> list[Citation]:
    """Return every well-formed citation found in ``content``.

    Malformed fragments (missing line number, bad path) simply don't match
    and are silently skipped — gates that care about validity check existence
    and line ranges after parsing.
    """
    out: list[Citation] = []
    for m in CITATION_RE.finditer(content):
        path = m.group(1).decode("utf-8", "replace")
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        out.append(Citation(path=path, line_start=start, line_end=end))
    return out


def cited_paths(content: bytes) -> set[str]:
    """Return the set of distinct paths cited in ``content``."""
    return {c.path for c in iter_citations(content)}
