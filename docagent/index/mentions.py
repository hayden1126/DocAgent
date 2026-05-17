"""Identifier-mention extraction.

For each generated artifact, record which symbol identifiers appear in its
prose so ``update`` mode can revisit artifacts when a referenced symbol is
renamed or removed.

The matcher is deliberately tight: a bare ``run`` or ``init`` in English
prose is *not* a mention. To count, a token must either:

1. Sit inside a backtick code span (the markdown convention for code), OR
2. Look unambiguously code-shaped — contains an underscore, dotted, has
   internal case transition (camelCase / multi-hump PascalCase).

The earlier matcher accepted any 2+ char word; that produced false positives
on common English words that happened to share names with real symbols
(``init``, ``run``, ``check``), and silently over-fanned-out ``update`` mode.
The final intersection against ``store.known_symbol_names()`` would mask the
issue *until* a project shipped a symbol named after a stopword — which is
common — at which point updates fired on every doc.
"""

from __future__ import annotations

import re

# Anything fenced by backticks counts as "the author meant code here." Inside
# the fence we accept any identifier-shaped token (including the dotted form
# plus its leaf, so a `Foo.bar` reference is queryable by either name).
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]+\b")
_DOTTED_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)+\b")

# Outside backticks, require an unambiguous code shape so English prose
# doesn't get mined for stopwords.
_PROGRAMMER_RE = re.compile(
    r"\b(?:"
    r"[A-Za-z_]\w*_\w+"                        # snake_case (has an underscore)
    r"|"
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)+"         # dotted form (foo.bar)
    r"|"
    r"[a-z][a-z0-9]+[A-Z]\w*"                  # camelCase
    r"|"
    r"[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+"          # PascalCase, 2+ humps
    r")\b"
)


def _harvest_backtick_chunk(chunk: str, out: set[str]) -> None:
    for m in _DOTTED_RE.finditer(chunk):
        out.add(m.group(0))
        out.add(m.group(0).rsplit(".", 1)[-1])
    for m in _IDENT_RE.finditer(chunk):
        out.add(m.group(0))


def extract_mentions(content: bytes) -> set[str]:
    text = content.decode("utf-8", errors="replace")
    out: set[str] = set()
    spans: list[tuple[int, int]] = []
    for m in _BACKTICK_RE.finditer(text):
        _harvest_backtick_chunk(m.group(1), out)
        spans.append(m.span())

    if spans:
        pieces: list[str] = []
        cursor = 0
        for start, end in spans:
            pieces.append(text[cursor:start])
            cursor = end
        pieces.append(text[cursor:])
        outside = "\n".join(pieces)
    else:
        outside = text

    for m in _PROGRAMMER_RE.finditer(outside):
        token = m.group(0)
        out.add(token)
        if "." in token:
            out.add(token.rsplit(".", 1)[-1])
    return out


def index_artifact(
    store: object,  # docagent.index.store.Store
    artifact_id: str,
    target_path: str,
    content: bytes,
    known_identifiers: set[str],
) -> int:
    """Persist mentions intersected with the symbol-name set, return count.

    ``target_path`` must already be normalized to a repo-relative POSIX
    string (see :func:`docagent.core.paths.to_repo_rel_posix`). Storing a
    mix of relative/absolute or backslash/POSIX paths here is the silent
    failure mode that breaks ``update``.
    """
    mentions = extract_mentions(content) & known_identifiers
    rows = [(ident, artifact_id, target_path) for ident in sorted(mentions)]
    store.replace_mentions_for_artifact(artifact_id, rows)  # type: ignore[attr-defined]
    return len(rows)
