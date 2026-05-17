"""Zero-dependency JSONC stripper for reading TypeScript ``tsconfig.json``.

The JSONC subset this module accepts is exactly what ``tsc`` itself accepts:

* ``//`` line comments
* ``/* ... */`` block comments (single- and multi-line)
* a trailing comma before ``}`` or ``]``

Anything beyond that subset (single-quoted strings, unquoted keys, the rest
of JSON5) is intentionally NOT supported. Callers should catch
``json.JSONDecodeError`` and fall through to the next discovery signal.

Implementation note: a naive regex pass would corrupt JSON strings that
contain ``//`` (URLs) or ``/**/`` (glob patterns like ``"src/**/*"``). We
therefore walk the input once, copying string contents verbatim and only
stripping comments / trailing commas in the surrounding JSON skeleton.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments, leaving string contents intact.

    The scanner tracks whether we are currently inside a double-quoted
    string. Inside strings, every character (including escapes) is copied
    verbatim; outside strings, ``//...EOL`` and ``/*...*/`` runs are
    elided.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                # Copy the escaped character verbatim so an embedded quote
                # does not prematurely close the string.
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            out.append(ch)
            in_string = True
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                # Line comment: skip until end-of-line (but keep the newline).
                j = i + 2
                while j < n and text[j] != "\n":
                    j += 1
                i = j
                continue
            if nxt == "*":
                # Block comment: skip until the closing */.
                j = i + 2
                while j < n - 1 and not (text[j] == "*" and text[j + 1] == "/"):
                    j += 1
                i = j + 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_jsonc(text: str) -> Any:
    """Strip JSONC niceties tsc accepts, then hand off to ``json.loads``.

    Raises ``json.JSONDecodeError`` on input outside the supported subset.
    """
    text = _strip_comments(text)
    text = _TRAILING_COMMA.sub(r"\1", text)
    return json.loads(text)
