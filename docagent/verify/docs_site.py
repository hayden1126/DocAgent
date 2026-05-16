"""Docs-site dry-run stub. Detects Sphinx/mkdocs and (eventually) runs a
build to catch broken cross-refs."""

from __future__ import annotations

from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    return True, ()
