"""End-to-end integration tests for ``docagent verify``.

Mirrors the ``test_update_flow`` pattern: bootstrap a tiny repo with the
tinylib fixture, run ``init`` with a scripted backend so we have known
artifacts on disk, then exercise ``verify`` against those artifacts —
clean pass, blocking-gate failure (broken citation), and a missing-file
scenario.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docagent import cli as docagent_cli
from docagent.backends.base import GenerationRequest, GenerationResponse


FIXTURES_DIR = Path(__file__).parent.parent / "golden" / "fixtures"
REAL_ARTIFACTS = ["readme", "agents_md", "claude_md", "llms_txt"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURES_DIR / "tinylib", dest)
    _git(dest, "init", "-b", "main")
    _git(dest, "add", ".")
    _git(dest, "commit", "-m", "initial")
    return dest


class _ScriptedBackend:
    name = "scripted"

    def __init__(self, content_by_artifact: dict[str, str]) -> None:
        self._content = content_by_artifact
        self.calls: list[str] = []

    def run(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request.artifact_id)
        content = self._content.get(
            request.artifact_id,
            f"# {request.artifact_id}\n\n(no scripted content)\n",
        )
        return GenerationResponse(content=content)


def _patch_backend(monkeypatch, backend) -> None:
    monkeypatch.setattr("docagent.backends.agent_sdk.AgentSDKBackend", lambda *a, **kw: backend)


def _init_args(repo: Path) -> list[str]:
    args = ["init", "-C", str(repo)]
    for aid in REAL_ARTIFACTS:
        args += ["--only", aid]
    return args


def _grounded_body(aid: str) -> str:
    """Per-artifact content that cites a real, in-range line in cli.py."""
    h1 = {
        "readme": "# tinylib",
        "agents_md": "# tinylib (agents)",
        "claude_md": "# tinylib (claude)",
        "llms_txt": "# tinylib (llms)",
    }[aid]
    return (
        f"{h1}\n\n"
        f"This package exposes the `greet` command. "
        f"<!-- ground: tinylib/cli.py:1-13 -->\n"
    )


def _seed_artifacts(repo: Path, monkeypatch) -> _ScriptedBackend:
    backend = _ScriptedBackend({aid: _grounded_body(aid) for aid in REAL_ARTIFACTS})
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout
    return backend


def test_verify_passes_on_clean_artifacts(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_artifacts(repo, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo)])
    assert result.exit_code == 0, result.stdout
    # Every artifact should report ok.
    for aid in REAL_ARTIFACTS:
        assert f"ok" in result.stdout
        assert aid in result.stdout
    # The judge "skipped" finding should be visible — the gate is in the
    # default pipeline but does not silently claim to pass.
    assert "judge" in result.stdout.lower()
    assert "skipped" in result.stdout.lower()


def test_verify_fails_on_out_of_range_citation(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_artifacts(repo, monkeypatch)
    # Break README's citation to a range beyond cli.py's length.
    readme = repo / "README.md"
    readme.write_text(
        "# tinylib\n\n"
        "Broken citation. <!-- ground: tinylib/cli.py:1-9999 -->\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo)])
    assert result.exit_code == 1, result.stdout
    assert "FAIL" in result.stdout
    assert "readme" in result.stdout
    assert "exceeds file" in result.stdout


def test_verify_fails_on_missing_referenced_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_artifacts(repo, monkeypatch)
    readme = repo / "README.md"
    readme.write_text(
        "# tinylib\n\n"
        "Missing target. <!-- ground: does/not/exist.py:1-3 -->\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo)])
    assert result.exit_code == 1, result.stdout
    assert "missing file" in result.stdout


def test_verify_only_filter_skips_other_artifacts(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_artifacts(repo, monkeypatch)
    # Break AGENTS.md but only verify the readme — should still pass.
    (repo / "AGENTS.md").write_text(
        "# agents\n\n<!-- ground: nope.py:1 -->\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(
        docagent_cli.app, ["verify", "-C", str(repo), "--only", "readme"]
    )
    assert result.exit_code == 0, result.stdout
    assert "agents_md" not in result.stdout


def test_verify_no_artifacts_on_disk_is_clean_exit(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh repo with no prior ``init`` should report nothing to verify
    and exit 0 — verify is a CI gate, not a tripwire."""
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "no artifacts on disk" in result.stdout.lower()


def test_verify_discovers_artifacts_without_prior_init(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``.docagent/`` doesn't exist (fresh CI checkout) but the repo
    has a committed README.md, verify should still pick it up via the
    registry's target-path fallback. This is what makes the GitHub Action
    usable on PRs without requiring a prior ``docagent init``."""
    # Write a README.md directly — no init, no .docagent/ state.
    (repo / "README.md").write_text(
        "# tinylib\n\nFresh repo. <!-- ground: tinylib/cli.py:1-13 -->\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo), "--only", "readme"])
    assert result.exit_code == 0, result.stdout
    assert "readme" in result.stdout.lower()
    # Should NOT have hit the "no artifacts" path.
    assert "no artifacts on disk" not in result.stdout.lower()


def test_verify_discovery_catches_stale_citation_on_fresh_checkout(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CI smoke test: a PR adds a README citing a bogus line range.
    Verify must fail even though the repo has never been init'd."""
    (repo / "README.md").write_text(
        "# tinylib\n\nBad cite. <!-- ground: tinylib/cli.py:9000-9999 -->\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo)])
    assert result.exit_code == 1, result.stdout
    assert "exceeds file" in result.stdout


def test_verify_strict_fails_on_non_blocking_finding(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under ``--strict``, even the judge's "skipped" finding (which is
    emitted non-blockingly by the default pipeline) should cause a non-zero
    exit. This catches accidental "ok with warnings" CI passes."""
    _seed_artifacts(repo, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(docagent_cli.app, ["verify", "-C", str(repo), "--strict"])
    assert result.exit_code == 1, result.stdout
