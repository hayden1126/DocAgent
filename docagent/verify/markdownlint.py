"""Markdown structural sanity. v1 stub: defers to an external `markdownlint`
binary when present; passes silently otherwise."""

from __future__ import annotations

import shutil
import subprocess
from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    if not str(patch.target_path).endswith(".md"):
        return True, ()
    binary = shutil.which("markdownlint")
    if binary is None:
        return True, ("markdownlint not installed; skipping",)
    try:
        result = subprocess.run(
            [binary, "--stdin"],
            input=patch.new_content,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, (f"markdownlint failed to run: {exc}",)
    if result.returncode != 0:
        return False, (result.stdout.decode("utf-8", "replace"),)
    return True, ()
