"""CLI tests for --max-cost + DOCAGENT_MAX_COST + _render_summary parity."""

from __future__ import annotations

import io
import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

from docagent.cli import _render_summary, app
from docagent.core.budget import BudgetTracker
from docagent.core.orchestrator import ArtifactRun


@pytest.fixture(autouse=True)
def _restore_logger_propagation() -> Generator[None, None, None]:
    logger = logging.getLogger("docagent")
    prior = logger.propagate
    logger.propagate = True
    try:
        yield
    finally:
        logger.propagate = prior


# ---- Fakes ----------------------------------------------------------------------


class _FakeBackend:
    name = "fake"
    model: str | None = "claude-sonnet-4-6"

    def _preflight(self) -> None:
        return

    def run(self, request: Any) -> Any:  # not used; orchestrator is also faked
        raise AssertionError("not called")


class _FakeOrchestrator:
    """Stub orchestrator. Configured via class attrs because Typer constructs
    it inside `init`/`update` and we can't pass kwargs through directly."""

    cost_per_artifact: float = 0.10
    artifacts_expected: int = 3
    cap_hit: bool = False  # set True to simulate cap abort

    def __init__(self, **kwargs: Any) -> None:
        self.max_cost: float = kwargs.get("max_cost", 0.0)
        self.dry_run: bool = kwargs.get("dry_run", False)
        self.only = kwargs.get("only", ())
        self.tracker = BudgetTracker(cap=self.max_cost)

    def run(self) -> list[ArtifactRun]:
        if self.dry_run:
            return [
                ArtifactRun(artifact_id=f"a{i}")
                for i in range(self.artifacts_expected)
            ]

        # Simulate running artifacts and accumulating cost.
        runs: list[ArtifactRun] = []
        for i in range(self.artifacts_expected):
            # Post-fact cap check: abort BEFORE running if already over cap.
            if self.tracker.would_exceed():
                self.tracker.mark_aborted()
                break
            cost = type(self).cost_per_artifact
            self.tracker.add(
                "claude-sonnet-4-6",
                int(cost * 1_000_000 / 3.0),  # input_tokens that produce ~cost
                0,
                0,
            )
            runs.append(
                ArtifactRun(
                    artifact_id=f"a{i}",
                    input_tokens=int(cost * 1_000_000 / 3.0),
                    output_tokens=0,
                    tool_calls=0,
                    cost_usd=cost,
                )
            )
        return runs


@pytest.fixture
def stub_orchestrator(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOrchestrator]:
    """Monkeypatch the Orchestrator class imported lazily inside `init`/`update`."""
    monkeypatch.setattr(
        "docagent.core.orchestrator.Orchestrator",
        _FakeOrchestrator,
    )
    monkeypatch.setattr(
        "docagent.backends.agent_sdk.AgentSDKBackend",
        _FakeBackend,
    )
    # Reset class attrs to defaults for each test.
    _FakeOrchestrator.cost_per_artifact = 0.10
    _FakeOrchestrator.artifacts_expected = 3
    return _FakeOrchestrator


@pytest.fixture
def seed_repo(tmp_path: Path) -> Path:
    """Minimal indexable repo: one .py file."""
    (tmp_path / "x.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


# ---- Tests --------------------------------------------------------------------


def test_exit_code_3_on_cap_hit(
    stub_orchestrator: type[_FakeOrchestrator], seed_repo: Path
) -> None:
    stub_orchestrator.cost_per_artifact = 0.10
    stub_orchestrator.artifacts_expected = 5
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--repo", str(seed_repo), "--max-cost", "0.15", "--skip-index"],
    )
    assert result.exit_code == 3, result.output
    assert "aborted at" in result.output
    assert "of $0.150 cap" in result.output  # adaptive format under $1


def test_max_cost_zero_runs_to_completion(
    stub_orchestrator: type[_FakeOrchestrator], seed_repo: Path
) -> None:
    stub_orchestrator.cost_per_artifact = 0.10
    stub_orchestrator.artifacts_expected = 3
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--repo", str(seed_repo), "--max-cost", "0", "--skip-index"],
    )
    assert result.exit_code == 0, result.output
    # Summary footer present.
    assert "in=" in result.output
    assert "out=" in result.output
    assert "tool_calls=" in result.output
    assert "cost=$" in result.output
    assert "wall=" in result.output


def test_negative_flag_rejected(
    stub_orchestrator: type[_FakeOrchestrator], seed_repo: Path
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--repo", str(seed_repo), "--max-cost", "-1", "--skip-index"],
    )
    # typer.BadParameter from callback → exit code 2.
    assert result.exit_code == 2, result.output


def test_env_var_honored_when_flag_absent(
    stub_orchestrator: type[_FakeOrchestrator],
    monkeypatch: pytest.MonkeyPatch,
    seed_repo: Path,
) -> None:
    stub_orchestrator.cost_per_artifact = 0.10
    stub_orchestrator.artifacts_expected = 5
    monkeypatch.setenv("DOCAGENT_MAX_COST", "0.15")
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--repo", str(seed_repo), "--skip-index"])
    assert result.exit_code == 3, result.output
    assert "aborted at" in result.output


def test_flag_overrides_env(
    stub_orchestrator: type[_FakeOrchestrator],
    monkeypatch: pytest.MonkeyPatch,
    seed_repo: Path,
) -> None:
    stub_orchestrator.cost_per_artifact = 0.10
    stub_orchestrator.artifacts_expected = 5
    monkeypatch.setenv("DOCAGENT_MAX_COST", "10.0")  # would allow run to completion
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--repo", str(seed_repo), "--max-cost", "0.15", "--skip-index"],
    )
    # Explicit flag wins → cap = 0.15 → abort.
    assert result.exit_code == 3, result.output


def test_dry_run_shows_na_tokens(
    stub_orchestrator: type[_FakeOrchestrator], seed_repo: Path
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["init", "--repo", str(seed_repo), "--dry-run", "--skip-index"]
    )
    assert result.exit_code == 0, result.output
    assert "tokens: n/a (dry-run)" in result.output
    # cost line not present in dry-run mode
    assert "cost=$" not in result.output


def test_update_honors_max_cost(
    stub_orchestrator: type[_FakeOrchestrator],
    monkeypatch: pytest.MonkeyPatch,
    seed_repo: Path,
) -> None:
    """`update` mode should honor `--max-cost` identically to `init`."""
    # Seed state.json with a doc_version so update doesn't early-exit.
    from docagent.core.state import RunState

    (seed_repo / ".docagent").mkdir(parents=True, exist_ok=True)
    rs = RunState(doc_version="deadbeef", last_run="2026-05-17T00:00:00Z")
    rs.save(seed_repo)

    # Stub diff.changed_files_since to return a non-empty list.
    monkeypatch.setattr(
        "docagent.core.diff.changed_files_since",
        lambda repo, sha: [seed_repo / "x.py"],
    )
    # Stub compute_affected_artifacts so we have artifacts to run.
    monkeypatch.setattr(
        "docagent.core.affected.compute_affected_artifacts",
        lambda *args, **kwargs: ["a0", "a1", "a2"],
    )

    stub_orchestrator.cost_per_artifact = 0.10
    stub_orchestrator.artifacts_expected = 5
    runner = CliRunner()
    result = runner.invoke(
        app, ["update", "--repo", str(seed_repo), "--max-cost", "0.15"]
    )
    assert result.exit_code == 3, result.output


def test_update_early_return_skips_summary(
    stub_orchestrator: type[_FakeOrchestrator],
    monkeypatch: pytest.MonkeyPatch,
    seed_repo: Path,
) -> None:
    """When `update` returns early ('no changes'), no summary footer."""
    from docagent.core.state import RunState

    (seed_repo / ".docagent").mkdir(parents=True, exist_ok=True)
    rs = RunState(doc_version="deadbeef", last_run="2026-05-17T00:00:00Z")
    rs.save(seed_repo)
    monkeypatch.setattr(
        "docagent.core.diff.changed_files_since",
        lambda repo, sha: [],  # no changes
    )
    runner = CliRunner()
    result = runner.invoke(app, ["update", "--repo", str(seed_repo)])
    assert result.exit_code == 0, result.output
    assert "no changes since last run" in result.output
    # No summary footer when nothing ran.
    assert "tool_calls=" not in result.output
    assert "tokens: n/a" not in result.output


def test_malformed_env_var_ignored(
    stub_orchestrator: type[_FakeOrchestrator],
    monkeypatch: pytest.MonkeyPatch,
    seed_repo: Path,
) -> None:
    monkeypatch.setenv("DOCAGENT_MAX_COST", "not-a-number")
    stub_orchestrator.cost_per_artifact = 0.10
    stub_orchestrator.artifacts_expected = 3
    runner = CliRunner()
    result = runner.invoke(
        app, ["init", "--repo", str(seed_repo), "--skip-index"]
    )
    # Malformed env var ignored → no cap → run completes normally.
    assert result.exit_code == 0, result.output


def test_render_summary_parity_between_invocations() -> None:
    """The shared `_render_summary` helper must produce byte-identical output
    for identical tracker state. This is the W4 parity check."""
    sio1 = io.StringIO()
    sio2 = io.StringIO()
    console1 = Console(file=sio1, force_terminal=False, no_color=True, width=200)
    console2 = Console(file=sio2, force_terminal=False, no_color=True, width=200)

    # Two trackers with identical state.
    t1 = BudgetTracker(cap=1.0)
    t1.add("claude-sonnet-4-6", 100_000, 50_000, 2)
    t2 = BudgetTracker(cap=1.0)
    t2.add("claude-sonnet-4-6", 100_000, 50_000, 2)

    _render_summary(
        console1, t1, dry_run=False, effective_cap=1.0,
        runs_count=2, expected_total=5, wall=0.42,
    )
    _render_summary(
        console2, t2, dry_run=False, effective_cap=1.0,
        runs_count=2, expected_total=5, wall=0.42,
    )

    assert sio1.getvalue() == sio2.getvalue()
    assert sio1.getvalue() != ""
