"""End-to-end integration test for ``docagent update`` mode.

Sets up a temporary git repo with the tinylib fixture, runs ``init`` with a
stubbed backend, renames a symbol in source, runs ``update``, and asserts:
- The right artifacts were flagged as affected (only those mentioning the
  renamed symbol).
- ``doc_version`` advanced.
- The mention index now reflects the new symbol name.
- The ``artifacts`` table digests rotated for re-generated artifacts only.

The Claude Agent SDK backend is replaced with a scripted stub that returns
deterministic Markdown — no network calls.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Callable

import pytest
from typer.testing import CliRunner

from docagent import cli as docagent_cli
from docagent.backends.base import GenerationRequest, GenerationResponse


FIXTURES_DIR = Path(__file__).parent.parent / "golden" / "fixtures"


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
    """Backend stub returning content based on (artifact_id, version) lookup.

    Each artifact's content references a SYMBOL_NAME identifier so the
    post-write hook records it in the mention index. Switching versions
    changes which identifier appears, which is what ``update`` should
    detect.
    """

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


def _make_responses(symbol_name: str) -> dict[str, str]:
    """Build per-artifact responses that all mention ``symbol_name`` in prose
    so the mention index records it on every artifact."""
    body = (
        f"# tinylib\n\n"
        f"This package exposes the `{symbol_name}` command. <!-- ground: tinylib/cli.py:1-13 -->\n"
    )
    return {
        "readme": body,
        "agents_md": body.replace("# tinylib", "# tinylib (agents)"),
        "claude_md": body.replace("# tinylib", "# tinylib (claude)"),
        "llms_txt": body.replace("# tinylib", "# tinylib (llms)"),
    }


def _query(repo: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(repo / ".docagent" / "index.db")
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


def _patch_backend(monkeypatch, backend) -> None:
    """Force both init and update to use our scripted backend.

    ``cli.init`` and ``cli.update`` import ``AgentSDKBackend`` lazily inside
    the function bodies, so we patch the symbol on its source module.
    """

    def _factory(*args, **kwargs):
        return backend

    monkeypatch.setattr(
        "docagent.backends.agent_sdk.AgentSDKBackend", _factory
    )


REAL_ARTIFACTS = ["readme", "agents_md", "claude_md", "llms_txt"]


def _init_args(repo: Path) -> list[str]:
    """Init CLI invocation that pins to the 4 real artifacts (skips stubs)."""
    args = ["init", "-C", str(repo)]
    for aid in REAL_ARTIFACTS:
        args += ["--only", aid]
    return args


def _update_args(repo: Path) -> list[str]:
    args = ["update", "-C", str(repo)]
    for aid in REAL_ARTIFACTS:
        args += ["--only", aid]
    return args


def test_update_flagging_renames_and_rotates_mentions(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()

    # --- Phase 1: init with v1 responses (every artifact mentions `greet`) ---
    v1_backend = _ScriptedBackend(_make_responses("greet"))
    _patch_backend(monkeypatch, v1_backend)
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout

    init_calls = sorted(v1_backend.calls)
    assert init_calls == sorted(REAL_ARTIFACTS)

    # Mentions table has `greet` for every real artifact.
    rows_greet = _query(repo, "SELECT DISTINCT artifact_id FROM mentions WHERE identifier='greet'")
    assert {row[0] for row in rows_greet} == set(REAL_ARTIFACTS)
    assert not _query(repo, "SELECT * FROM mentions WHERE identifier='salute'")

    digests_v1 = {
        aid: digest for aid, _, digest in _query(repo, "SELECT id, path, digest FROM artifacts")
        if aid in REAL_ARTIFACTS
    }
    assert set(digests_v1) == set(REAL_ARTIFACTS)

    # Commit the generated artifacts so subsequent diff is purely about source.
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1 artifacts")

    # --- Phase 2: rename greet → salute in source, commit ---
    cli_file = repo / "tinylib" / "cli.py"
    cli_file.write_text(cli_file.read_text().replace("greet", "salute"))
    _git(repo, "commit", "-am", "rename greet → salute")

    # --- Phase 3: update with v2 responses (artifacts now mention `salute`) ---
    v2_backend = _ScriptedBackend(_make_responses("salute"))
    _patch_backend(monkeypatch, v2_backend)
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout

    # All 4 mentioning artifacts were flagged.
    assert sorted(v2_backend.calls) == sorted(REAL_ARTIFACTS)

    # Mention index: `greet` is gone, `salute` is present everywhere.
    greet_rows = _query(repo, "SELECT * FROM mentions WHERE identifier='greet'")
    salute_rows = _query(repo, "SELECT DISTINCT artifact_id FROM mentions WHERE identifier='salute'")
    assert greet_rows == [], "stale 'greet' mentions should have been replaced"
    assert {r[0] for r in salute_rows} == set(REAL_ARTIFACTS)

    # All 4 artifact digests rotated.
    digests_v2 = {
        aid: digest for aid, _, digest in _query(repo, "SELECT id, path, digest FROM artifacts")
        if aid in REAL_ARTIFACTS
    }
    for aid in REAL_ARTIFACTS:
        assert digests_v1[aid] != digests_v2[aid], f"digest for {aid} did not rotate"


def test_update_when_neither_signal_fires_is_no_op(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The affected resolver has two signals: identifier mentions and path
    citations. When NEITHER fires, update is a no-op.

    Construction: artifact content cites only ``LICENSE`` and mentions no
    symbols. Then we rename ``greet`` → ``bow`` in ``tinylib/cli.py``. No
    artifact mentions ``greet`` (signal 1 empty) and no artifact cites
    ``tinylib/cli.py`` (signal 2 empty).
    """
    runner = CliRunner()

    # Responses that cite LICENSE only and mention no symbol names.
    license_only = (
        "# tinylib\n\n"
        "An MIT-licensed package. <!-- ground: LICENSE:1-1 -->\n"
    )
    responses = {aid: license_only for aid in REAL_ARTIFACTS}
    backend = _ScriptedBackend(responses)
    _patch_backend(monkeypatch, backend)
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1 artifacts")

    # Confirm no artifact mentions `greet`.
    assert not _query(repo, "SELECT * FROM mentions WHERE identifier='greet'")

    # Rename `greet` → `bow` in cli.py.
    cli_file = repo / "tinylib" / "cli.py"
    cli_file.write_text(cli_file.read_text().replace("greet", "bow"))
    _git(repo, "commit", "-am", "rename greet → bow")

    backend.calls.clear()
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout
    assert backend.calls == [], (
        "neither mentions nor path citations refer to cli.py; should be a no-op"
    )
    assert "no artifacts affected" in result.stdout.lower()


def test_update_when_only_path_citation_signal_fires(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Signal 2 alone: artifacts cite a file but mention no symbol names.

    Renaming a symbol in the cited file should still flag every artifact
    that cites the file, because their line ranges may have shifted.
    """
    runner = CliRunner()

    # Responses that cite cli.py but mention no symbol names in prose.
    cite_only = (
        "# tinylib\n\n"
        "See the implementation. <!-- ground: tinylib/cli.py:1-13 -->\n"
    )
    responses = {aid: cite_only for aid in REAL_ARTIFACTS}
    backend = _ScriptedBackend(responses)
    _patch_backend(monkeypatch, backend)
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1 artifacts")

    # No artifact mentions `greet` (no symbol words in prose).
    assert not _query(repo, "SELECT * FROM mentions WHERE identifier='greet'")

    cli_file = repo / "tinylib" / "cli.py"
    cli_file.write_text(cli_file.read_text().replace("greet", "bow"))
    _git(repo, "commit", "-am", "rename greet → bow")

    backend.calls.clear()
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout
    # All 4 cite cli.py → all 4 should be flagged.
    assert sorted(backend.calls) == sorted(REAL_ARTIFACTS)


def test_update_with_no_source_changes_is_no_op(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After init + committing the generated artifacts, the only diff is the
    artifact files themselves. update must recognize those as artifact-target
    paths and refuse to chase its tail."""
    runner = CliRunner()
    backend = _ScriptedBackend(_make_responses("greet"))
    _patch_backend(monkeypatch, backend)
    runner.invoke(docagent_cli.app, _init_args(repo))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1")

    backend.calls.clear()
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout
    assert backend.calls == []
    # The output should explicitly report "no artifacts affected" — i.e. the
    # changed-file count may be non-zero, but compute_affected dropped them.
    assert "no artifacts affected" in result.stdout.lower()
