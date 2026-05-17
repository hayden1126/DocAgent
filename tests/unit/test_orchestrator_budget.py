"""Integration tests for Orchestrator <-> BudgetTracker plumbing (Phase 5).

Covers:
  - Token / cost accumulation per ArtifactRun and on orchestrator.tracker
  - run() return signature unchanged (still list[ArtifactRun])
  - max_cost=0 disables the cap
  - Cap aborts between artifacts post-fact (Decision Log §4)
  - Per-call progress lines only for multi-task artifacts
  - dry_run skips tracker.add() and per-call lines
  - orchestrator.tracker non-None even when run() never called
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from rich.console import Console

from docagent.artifacts.registry import DocPatch, GenerationContext, Registry, Task, VerifyResult
from docagent.backends.base import GenerationRequest, GenerationResponse
from docagent.core.budget import BudgetTracker
from docagent.core.orchestrator import Orchestrator
from docagent.index.store import open_store

# ---- Fake backend ----------------------------------------------------------------


@dataclass
class _FakeBackend:
    name: str = "fake"
    model: str | None = "claude-sonnet-4-6"
    # Tokens emitted per call.
    input_tokens: int = 1000
    output_tokens: int = 500
    tool_calls: int = 1

    def run(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            content="generated body",
            tool_calls=self.tool_calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


# ---- Stub artifacts --------------------------------------------------------------


@dataclass
class _SingleTaskArtifact:
    id: str = "single"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / f"{self.id}.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        resp = ctx.backend.run(  # type: ignore[attr-defined]
            GenerationRequest(artifact_id=self.id, prompt="x", repo_root=ctx.repo_root)
        )
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=resp.content.encode("utf-8"),
            prompt_version="t1",
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


@dataclass
class _MultiTaskArtifact:
    """Plans N tasks, each calling backend.run() once."""

    n_tasks: int = 3
    id: str = "multi"
    audience: str = "human"
    depends_on: tuple[str, ...] = ()

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [
            Task(
                artifact_id=self.id,
                target_path=ctx.repo_root / f"mod_{i}.md",
            )
            for i in range(self.n_tasks)
        ]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        resp = ctx.backend.run(  # type: ignore[attr-defined]
            GenerationRequest(artifact_id=self.id, prompt="x", repo_root=ctx.repo_root)
        )
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=resp.content.encode("utf-8"),
            prompt_version="t1",
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


@dataclass
class _SingleTaskArtifactWithCost:
    """Single-task artifact whose backend produces a configured token count."""

    id: str
    cost_each_input: int
    cost_each_output: int
    audience: str = "human"
    depends_on: tuple[str, ...] = field(default_factory=tuple)

    def plan(self, ctx: GenerationContext) -> list[Task]:
        return [Task(artifact_id=self.id, target_path=ctx.repo_root / f"{self.id}.md")]

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        resp = ctx.backend.run(  # type: ignore[attr-defined]
            GenerationRequest(artifact_id=self.id, prompt="x", repo_root=ctx.repo_root)
        )
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=resp.content.encode("utf-8"),
            prompt_version="t1",
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        return VerifyResult(ok=True)


# ---- Tests ------------------------------------------------------------------------


def test_tracker_accumulates_across_artifacts(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_SingleTaskArtifact(id="a1"))
    reg.register(_SingleTaskArtifact(id="a2"))

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(),
        store=store,
    )
    runs = orch.run()

    assert isinstance(runs, list)  # return type unchanged
    assert len(runs) == 2
    for r in runs:
        assert r.input_tokens == 1000
        assert r.output_tokens == 500
        assert r.tool_calls == 1
        assert r.cost_usd > 0.0

    # Cumulative cost on the tracker matches the sum of per-artifact costs.
    expected_cum = sum(r.cost_usd for r in runs)
    assert orch.tracker.cumulative_cost() == pytest.approx(expected_cum)
    assert orch.tracker.aborted is False
    store.close()


def test_post_write_test_still_passes_orch_indexing_unchanged(tmp_path: Path) -> None:
    """Regression: `runs[0]` still returns the first ArtifactRun (not a tuple)."""
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_SingleTaskArtifact())
    orch = Orchestrator(repo_root=tmp_path, registry=reg, backend=_FakeBackend(), store=store)
    runs = orch.run()
    first = runs[0]
    assert first.artifact_id == "single"
    store.close()


def test_max_cost_zero_runs_to_completion(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    for i in range(3):
        reg.register(_SingleTaskArtifact(id=f"a{i}"))
    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=1_000_000, output_tokens=1_000_000),
        store=store,
        max_cost=0.0,
    )
    runs = orch.run()
    assert len(runs) == 3
    assert orch.tracker.aborted is False
    store.close()


def test_cap_aborts_between_artifacts_post_fact(tmp_path: Path) -> None:
    """5 artifacts each cost ~$0.50; cap=$1.00 → run 3, abort at 4th iteration.

    Cost arithmetic: 100k input + 0 output on Sonnet = $0.30 per call. So we
    pick 100k/100k Sonnet → $0.30+$1.50 = ... let's just use clear numbers.
    100_000 input + 100_000 output on Sonnet (3.0 / 15.0): cost = 0.3 + 1.5 = 1.8 → too high.
    Use 100_000 input + 0 output → $0.30 per call. cap=$0.65 → run 1 ($0.30 not > 0.65),
    run 2 ($0.60 not > 0.65), run 3 ($0.90 > 0.65 → abort BEFORE 4th).
    """
    store = open_store(tmp_path)
    reg = Registry()
    for i in range(5):
        reg.register(_SingleTaskArtifact(id=f"a{i}"))

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=100_000, output_tokens=0, tool_calls=0),
        store=store,
        max_cost=0.65,
    )
    runs = orch.run()
    # After 2 artifacts: cum=$0.60 (not > 0.65). After 3rd: cum=$0.90 (> 0.65).
    # The 4th iteration's check fires → abort. So 3 runs are returned.
    assert len(runs) == 3
    assert orch.tracker.aborted is True
    assert orch.tracker.cumulative_cost() == pytest.approx(0.90)
    store.close()


def test_per_call_lines_only_for_multi_task(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_SingleTaskArtifact(id="single"))
    reg.register(_MultiTaskArtifact(n_tasks=3, id="multi"))
    sio = io.StringIO()
    console = Console(file=sio, force_terminal=False, no_color=True, width=200)

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=100, output_tokens=50),
        store=store,
        console=console,
    )
    orch.run()

    output = sio.getvalue()
    # Single-task artifact should NOT produce any progress lines.
    assert "single.md" not in output  # no per-call line for single-task
    # Multi-task artifact: exactly 3 progress lines, one per task.
    multi_lines = [
        ln for ln in output.splitlines()
        if ln.startswith("[") and "in=" in ln and "out=" in ln
    ]
    assert len(multi_lines) == 3
    store.close()


def test_per_call_line_matches_locked_spec(tmp_path: Path) -> None:
    """Per-call line format: `[n/N] <mod>  in=X out=Y  call=$A  cum=$B`."""
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_MultiTaskArtifact(n_tasks=3, id="multi"))
    sio = io.StringIO()
    console = Console(file=sio, force_terminal=False, no_color=True, width=200)

    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=842, output_tokens=129),
        store=store,
        console=console,
    )
    orch.run()

    pattern = re.compile(
        r"^\[\d+/\d+\] \S+  in=\d+ out=\d+  call=\$\d+\.\d{2,3}  cum=\$\d+\.\d{2,3}$"
    )
    lines = [ln for ln in sio.getvalue().splitlines() if ln.startswith("[")]
    assert lines, "expected at least one per-call line"
    for ln in lines:
        assert pattern.match(ln), f"line did not match locked spec: {ln!r}"
    store.close()


def test_dry_run_skips_tracker_add(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_SingleTaskArtifact())
    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=1000, output_tokens=500),
        store=store,
        dry_run=True,
    )
    orch.run()
    assert orch.tracker.cumulative_cost() == 0.0
    store.close()


def test_dry_run_no_per_call_lines(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_MultiTaskArtifact(n_tasks=3))
    sio = io.StringIO()
    console = Console(file=sio, force_terminal=False, no_color=True, width=200)
    orch = Orchestrator(
        repo_root=tmp_path,
        registry=reg,
        backend=_FakeBackend(input_tokens=100, output_tokens=50),
        store=store,
        dry_run=True,
        console=console,
    )
    orch.run()
    progress_lines = [
        ln for ln in sio.getvalue().splitlines()
        if ln.startswith("[") and "in=" in ln
    ]
    assert progress_lines == []
    store.close()


def test_tracker_non_none_before_run(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    reg = Registry()
    reg.register(_SingleTaskArtifact())
    orch = Orchestrator(repo_root=tmp_path, registry=reg, backend=_FakeBackend(), store=store)
    # Tracker exists immediately, even before run().
    assert isinstance(orch.tracker, BudgetTracker)
    assert orch.tracker.cumulative_cost() == 0.0
    store.close()
