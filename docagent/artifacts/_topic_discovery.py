"""Topic dataclass + slug generation for `how_to_guides`.

Pure-Python helpers. No LLM, no I/O. Slug rules and collision policy are
documented in `.planning/phases/06-how-to-guides-artifact/06-CONTEXT.md`.

DO NOT reuse `docagent.verify.links._slugify` — that's a GitHub-anchor
slugger, not a filename slugger. They have different cap/charset rules.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_HOW_TO_PREFIX = re.compile(r"^how to ", re.IGNORECASE)
_SLUG_MAX = 60


@dataclass(frozen=True)
class Topic:
    """One LLM-discovered user-task topic.

    `slug` is the kebab-case filename stem (≤60 chars, `[a-z0-9-]+`).
    `title` is the original imperative title for the page H1.
    `sources` are repo-relative `path:start-end` citation strings the
    discovery LLM proposed as grounding evidence.
    """

    slug: str
    title: str
    sources: list[str]


def topic_slug(title: str) -> str:
    """Derive a filename-safe slug from an imperative topic title.

    Rules (locked in CONTEXT.md):
    1. Strip a leading "How to " (case-insensitive) prefix.
    2. Lowercase.
    3. Replace runs of non-`[a-z0-9]` with single `-`.
    4. Strip leading/trailing `-`.
    5. Cap at 60 chars (slice + re-strip trailing `-`).
    6. If empty after the above, fall back to `howto-<sha1[:8]>`.
    """
    stripped = _HOW_TO_PREFIX.sub("", title, count=1).lower()
    slug = _NON_ALNUM.sub("-", stripped).strip("-")
    if len(slug) > _SLUG_MAX:
        slug = slug[:_SLUG_MAX].rstrip("-")
    if not slug:
        return f"howto-{hashlib.sha1(title.encode('utf-8')).hexdigest()[:8]}"
    return slug


def dedupe_topics(
    topics: list[Topic], *, warn: Callable[[str], None]
) -> list[Topic]:
    """First-write-wins dedupe on slug, with ONE warn per collision pair.

    Walks `topics` in input order. The first occurrence of each slug is
    kept; subsequent occurrences are dropped and produce one `warn(...)`
    call apiece (so three colliding topics produce TWO warns, not ONE).
    """
    seen: dict[str, Topic] = {}
    out: list[Topic] = []
    for t in topics:
        existing = seen.get(t.slug)
        if existing is not None:
            warn(
                f"slug collision: dropping '{t.title}' "
                f"(collides with kept '{existing.title}', slug={t.slug})"
            )
            continue
        seen[t.slug] = t
        out.append(t)
    return out
