"""Identifier-mention extraction.

For each generated artifact, record which symbol identifiers appear in its
prose so `update` mode can revisit artifacts when a referenced symbol is
renamed or removed.
"""

from __future__ import annotations

import re
from pathlib import Path

# Conservative identifier matcher — letters/digits/underscore, ≥2 chars, must
# contain a letter. Tightens later when we have real artifact content to test.
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{1,}\b")


def extract_mentions(content: bytes) -> set[str]:
    text = content.decode("utf-8", errors="replace")
    return {m.group(0) for m in IDENTIFIER_RE.finditer(text)}


def index_artifact(
    store: object,  # docagent.index.store.Store
    artifact_id: str,
    target_path: Path,
    content: bytes,
    known_identifiers: set[str],
) -> int:
    """Persist mentions intersected with the symbol-name set, return count."""
    mentions = extract_mentions(content) & known_identifiers
    rows = [(ident, artifact_id, str(target_path)) for ident in sorted(mentions)]
    store.replace_mentions_for_artifact(artifact_id, rows)  # type: ignore[attr-defined]
    return len(rows)
