"""Internal link checker.

Extracts every Markdown inline link and image from the patch content and
verifies them deterministically:

- Relative paths (``./foo.py``, ``docs/x.md``) must exist under the repo root.
- In-document anchors (``#section-name``) must match a GitHub-style slug of
  one of the headings in the same patch.
- External URLs (``http://``, ``https://``, ``mailto:``, ``tel:``, ``ftp:``,
  ``ws[s]:``) are silently skipped in v1 — HEAD-checking adds I/O cost and
  flakiness that does not belong in a blocking gate.

This is a blocking gate. The signal-to-noise ratio of broken-link findings is
high, and the cost of running them is tiny.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext

# Match Markdown inline links/images: `[text](url)` and `![text](url)`.
# Permissive on text to handle nested brackets in description; permissive on
# the URL to handle paths with spaces (unusual but legal).
_LINK_RE = re.compile(
    r"""
    !?              # optional image marker
    \[(?P<text>[^\]]*)\]      # [text]
    \((?P<url>[^)\s]+(?:\s+"[^"]*")?)\)  # (url) or (url "title")
    """,
    re.VERBOSE,
)

# Match Markdown reference-style link definitions: ``[id]: url``.
_REF_DEF_RE = re.compile(
    r"^\s*\[(?P<id>[^\]]+)\]:\s+(?P<url>\S+)",
    re.MULTILINE,
)

# ATX heading: ``# Title``, ``## Subtitle``. Setext headings are ignored —
# rare in generated content.
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)

# Schemes we treat as external and don't verify.
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp:", "ws://", "wss://")


def _slugify(heading: str) -> str:
    """GitHub-flavored heading slug.

    Lowercase, drop most punctuation, collapse whitespace to ``-``. This
    matches the slug GitHub renders inside ``<h1 id="...">``.
    """
    s = heading.lower()
    s = re.sub(r"[^\w\s\-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s


def _own_anchors(text: str) -> set[str]:
    return {_slugify(m.group("title")) for m in _HEADING_RE.finditer(text)}


def _strip_title(url: str) -> str:
    """Strip an optional ``"title"`` suffix from inside ``(...)``."""
    return url.split(" ", 1)[0]


def _is_external(url: str) -> bool:
    lowered = url.lower()
    return any(lowered.startswith(scheme) for scheme in _EXTERNAL_SCHEMES)


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    text = patch.new_content.decode("utf-8", errors="replace")

    findings: list[str] = []
    ok = True

    own_anchors = _own_anchors(text)
    repo_root = ctx.repo_root

    seen_inline: set[str] = set()
    for m in _LINK_RE.finditer(text):
        url = _strip_title(m.group("url"))
        if url in seen_inline:
            continue
        seen_inline.add(url)
        if not _validate_url(url, own_anchors, repo_root):
            findings.append(f"broken link: {url}")
            ok = False

    for m in _REF_DEF_RE.finditer(text):
        url = _strip_title(m.group("url"))
        if not _validate_url(url, own_anchors, repo_root):
            findings.append(f"broken reference link [{m.group('id')}]: {url}")
            ok = False

    return ok, findings


def _validate_url(url: str, own_anchors: set[str], repo_root: Path) -> bool:
    if not url:
        return False
    if _is_external(url):
        return True
    if url.startswith("#"):
        return url[1:] in own_anchors
    # Relative path, possibly with ``#anchor``. We verify the file exists; v1
    # does not validate cross-file anchors (those move when the target file
    # is regenerated and would need re-resolution against an artifact graph).
    path_part = url.split("#", 1)[0]
    candidate = (repo_root / path_part).resolve()
    try:
        # Don't allow escaping the repo root via ``../../..``.
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return False
    return candidate.exists()
