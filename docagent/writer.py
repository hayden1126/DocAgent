"""Apply DocPatches to disk.

For new-file artifacts the patch content is written wholesale. For in-place
artifacts the patch carries already-spliced bytes (the adapter performed the
splice during `generate`). Dry-run prints a unified diff instead of writing.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from docagent.artifacts.registry import DocPatch


@dataclass(frozen=True, slots=True)
class WriteResult:
    target: Path
    written: bool
    diff: str = ""


def apply_patch(patch: DocPatch, repo_root: Path, *, dry_run: bool = False) -> WriteResult:
    target = patch.target_path
    if not target.is_absolute():
        target = repo_root / target

    new_text = patch.new_content.decode("utf-8", errors="replace")
    old_text = ""
    if target.exists():
        old_text = target.read_text(encoding="utf-8", errors="replace")

    if old_text == new_text:
        return WriteResult(target=target, written=False)

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=str(target) + " (current)",
            tofile=str(target) + " (proposed)",
            lineterm="",
        )
    )

    if dry_run:
        return WriteResult(target=target, written=False, diff=diff)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8")
    return WriteResult(target=target, written=True, diff=diff)
