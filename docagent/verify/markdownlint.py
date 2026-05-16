"""Markdown structural sanity gate.

Uses ``pymarkdown`` (PyPI: ``pymarkdownlnt``) when present — a pure-Python
CommonMark linter that covers the same MD### ruleset as markdownlint-cli2
without forcing a Node.js dependency on a Python project. If the binary is
not on PATH, the gate skips silently and reports a single advisory finding.

This gate is non-blocking by default (see ``default_pipeline``): style
violations should never prevent the citations / links / secrets gates from
running, much less prevent a write. We surface findings so the user can fix
them, but we do not gate on them.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path as _Path
from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext


def _find_binary() -> str | None:
    # PATH lookup first.
    found = shutil.which("pymarkdown")
    if found:
        return found
    # Fall back to a sibling of the running Python (typical for venv installs
    # invoked via ``.venv/bin/python`` without venv activation).
    sibling = _Path(sys.executable).with_name("pymarkdown")
    if sibling.is_file():
        return str(sibling)
    return None


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    target = str(patch.target_path)
    if not target.endswith((".md", ".markdown")):
        return True, ()

    binary = _find_binary()
    if binary is None:
        return True, ("pymarkdown not installed; skipping",)

    try:
        # MD013 (line-length) is disabled by default because LLM-generated
        # prose with `<!-- ground: path:N-M -->` citation tags fundamentally
        # exceeds 80 columns and reflowing breaks citation attachment to the
        # sentence. Override via DOCAGENT_MD_RULES_DISABLE env var if needed.
        import os as _os

        disable = _os.environ.get("DOCAGENT_MD_RULES_DISABLE", "MD013")
        cmd = [binary, "--return-code-scheme", "default"]
        if disable:
            cmd += ["--disable-rules", disable]
        cmd += ["scan-stdin"]
        result = subprocess.run(
            cmd,
            input=patch.new_content,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return True, (f"pymarkdown failed to run: {exc}; skipping",)

    # Exit codes (default scheme): 0=clean, 1=lint findings, 2=tool error.
    if result.returncode == 0:
        return True, ()
    if result.returncode == 2:
        return True, (
            f"pymarkdown tool error: {result.stderr.decode('utf-8', 'replace')[:400]}; skipping",
        )

    raw = result.stdout.decode("utf-8", "replace").strip()
    findings = [line for line in raw.splitlines() if line.strip()]
    # Trim to the first 25 findings so a thousand-line MD013 spam doesn't
    # dominate run output.
    if len(findings) > 25:
        extra = len(findings) - 25
        findings = findings[:25] + [f"(+ {extra} more findings)"]
    return False, findings
