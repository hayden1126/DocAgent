"""Tests for verifier-pipeline gate ordering and blocking semantics.

The single most important invariant: a stylistic gate (markdownlint) finding
problems must NOT prevent the citations gate from running. Without this, one
MD013 line-length nit would nuke an otherwise-valid artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext
from docagent.verify.pipeline import Gate, VerifierPipeline, default_pipeline


@dataclass
class _Calls:
    seen: list[str]


def test_stylistic_failure_does_not_block_truth_gates() -> None:
    calls = _Calls(seen=[])

    def style_fail(patch, ctx):
        calls.seen.append("style")
        return False, ("stylistic nit",)

    def truth_check(patch, ctx):
        calls.seen.append("truth")
        return True, ()

    pipeline = (
        VerifierPipeline()
        .add(Gate("style", style_fail, blocking=False))
        .add(Gate("truth", truth_check, blocking=True))
    )
    result = pipeline.run(
        DocPatch("x", Path("/tmp/x"), b""),
        GenerationContext(repo_root=Path("/tmp"), store=None, backend=None),
    )
    assert calls.seen == ["style", "truth"]
    # Non-blocking failures count as ok=False overall (findings still surface).
    assert result.ok is False
    assert any("stylistic nit" in f for f in result.findings)


def test_blocking_failure_short_circuits_pipeline() -> None:
    calls = _Calls(seen=[])

    def truth_fail(patch, ctx):
        calls.seen.append("truth")
        return False, ("citation broken",)

    def later(patch, ctx):
        calls.seen.append("later")
        return True, ()

    pipeline = (
        VerifierPipeline()
        .add(Gate("truth", truth_fail, blocking=True))
        .add(Gate("later", later, blocking=False))
    )
    pipeline.run(
        DocPatch("x", Path("/tmp/x"), b""),
        GenerationContext(repo_root=Path("/tmp"), store=None, backend=None),
    )
    assert calls.seen == ["truth"]


def test_default_pipeline_has_correct_blocking_flags() -> None:
    """Pin the v1 alpha gate ordering and blocking semantics."""
    pipeline = default_pipeline()
    by_name = {g.name: g for g in pipeline.gates}
    assert by_name["markdownlint"].blocking is False
    assert by_name["links"].blocking is True
    assert by_name["citations"].blocking is True
    assert by_name["docs_site"].blocking is False
    assert by_name["secrets"].blocking is True
    assert by_name["judge"].blocking is False
    # And the order: markdownlint runs before citations runs before judge.
    names = [g.name for g in pipeline.gates]
    assert names.index("markdownlint") < names.index("citations")
    assert names.index("citations") < names.index("judge")
