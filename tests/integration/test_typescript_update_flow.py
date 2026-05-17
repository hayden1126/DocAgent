"""End-to-end ``docagent update`` integration tests on a TypeScript repo.

Twin of ``test_update_flow.py`` for the Python ``tinylib`` fixture, ported to
``tinylib_ts``. Verifies that the new ``TypeScriptAdapter`` plumbs through
the orchestrator + affected-artifact resolver end-to-end:

- Renaming a TS symbol in source flags every artifact that mentions it.
- Mention rows for the old name are removed and the new name is inserted.
- Re-running with no signal change (no mentioning artifact AND no
  path-citation pointing at the changed file) is a no-op.
- Artifact-file edits (a user touching README.md) do not chase their own
  tail.
"""

from __future__ import annotations

import shutil
import sqlite3
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
    shutil.copytree(FIXTURES_DIR / "tinylib_ts", dest)
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


def _make_responses(symbol_name: str) -> dict[str, str]:
    """Per-artifact bodies that all mention ``symbol_name`` in a backtick
    code span (so the tightened mention extractor records it) and ground a
    citation against the real ``src/cli.ts``."""
    body = (
        f"# tinylib-ts\n\n"
        f"This package exposes the `{symbol_name}` command. "
        f"<!-- ground: src/cli.ts:1-6 -->\n"
    )
    return {
        "readme": body,
        "agents_md": body.replace("# tinylib-ts", "# tinylib-ts (agents)"),
        "claude_md": body.replace("# tinylib-ts", "# tinylib-ts (claude)"),
        "llms_txt": body.replace("# tinylib-ts", "# tinylib-ts (llms)"),
    }


def _query(repo: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(repo / ".docagent" / "index.db")
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


def _patch_backend(monkeypatch, backend) -> None:
    monkeypatch.setattr(
        "docagent.backends.agent_sdk.AgentSDKBackend", lambda *a, **kw: backend
    )


def _init_args(repo: Path) -> list[str]:
    args = ["init", "-C", str(repo)]
    for aid in REAL_ARTIFACTS:
        args += ["--only", aid]
    return args


def _update_args(repo: Path) -> list[str]:
    args = ["update", "-C", str(repo)]
    for aid in REAL_ARTIFACTS:
        args += ["--only", aid]
    return args


def test_ts_update_renames_flag_mentioning_artifacts(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()

    # --- Phase 1: init with v1 responses (every artifact mentions `greet`) ---
    v1 = _ScriptedBackend(_make_responses("greet"))
    _patch_backend(monkeypatch, v1)
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout
    assert sorted(v1.calls) == sorted(REAL_ARTIFACTS)

    # `greet` should appear in mentions for every real artifact.
    rows_greet = _query(
        repo, "SELECT DISTINCT artifact_id FROM mentions WHERE identifier='greet'"
    )
    assert {row[0] for row in rows_greet} == set(REAL_ARTIFACTS)
    assert not _query(repo, "SELECT * FROM mentions WHERE identifier='salute'")

    digests_v1 = {
        aid: digest
        for aid, _, digest in _query(repo, "SELECT artifact_id, path, digest FROM artifacts")
        if aid in REAL_ARTIFACTS
    }
    assert set(digests_v1) == set(REAL_ARTIFACTS)

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1 artifacts")

    # --- Phase 2: rename greet → salute in cli.ts ---
    cli_file = repo / "src" / "cli.ts"
    cli_file.write_text(cli_file.read_text().replace("greet", "salute"))
    _git(repo, "commit", "-am", "rename greet → salute")

    # --- Phase 3: update with v2 responses (artifacts now mention `salute`) ---
    v2 = _ScriptedBackend(_make_responses("salute"))
    _patch_backend(monkeypatch, v2)
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout
    assert sorted(v2.calls) == sorted(REAL_ARTIFACTS)

    # Mention index rotated.
    assert _query(repo, "SELECT * FROM mentions WHERE identifier='greet'") == []
    salute_rows = _query(
        repo, "SELECT DISTINCT artifact_id FROM mentions WHERE identifier='salute'"
    )
    assert {r[0] for r in salute_rows} == set(REAL_ARTIFACTS)

    # All 4 digests rotated.
    digests_v2 = {
        aid: digest
        for aid, _, digest in _query(repo, "SELECT artifact_id, path, digest FROM artifacts")
        if aid in REAL_ARTIFACTS
    }
    for aid in REAL_ARTIFACTS:
        assert digests_v1[aid] != digests_v2[aid], f"digest for {aid} did not rotate"


def test_ts_update_when_neither_signal_fires_is_no_op(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No artifact mentions ``greet``, no artifact cites ``src/cli.ts``.
    Renaming the symbol must not trigger anything."""
    runner = CliRunner()

    license_only = (
        "# tinylib-ts\n\nAn MIT-licensed package. <!-- ground: LICENSE:1-1 -->\n"
    )
    responses = {aid: license_only for aid in REAL_ARTIFACTS}
    backend = _ScriptedBackend(responses)
    _patch_backend(monkeypatch, backend)
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1 artifacts")

    # Sanity: no mention of `greet` was recorded.
    assert not _query(repo, "SELECT * FROM mentions WHERE identifier='greet'")

    cli_file = repo / "src" / "cli.ts"
    cli_file.write_text(cli_file.read_text().replace("greet", "bow"))
    _git(repo, "commit", "-am", "rename greet → bow")

    backend.calls.clear()
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout
    assert backend.calls == []
    assert "no artifacts affected" in result.stdout.lower()


def test_ts_update_when_only_path_citation_signal_fires(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Artifacts cite ``src/cli.ts`` but mention no symbol names. A rename
    in cli.ts must still flag every artifact that cites the file because the
    line ranges may have shifted."""
    runner = CliRunner()

    cite_only = (
        "# tinylib-ts\n\nSee the implementation. <!-- ground: src/cli.ts:1-6 -->\n"
    )
    responses = {aid: cite_only for aid in REAL_ARTIFACTS}
    backend = _ScriptedBackend(responses)
    _patch_backend(monkeypatch, backend)
    result = runner.invoke(docagent_cli.app, _init_args(repo))
    assert result.exit_code == 0, result.stdout
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v1 artifacts")

    assert not _query(repo, "SELECT * FROM mentions WHERE identifier='greet'")

    cli_file = repo / "src" / "cli.ts"
    cli_file.write_text(cli_file.read_text().replace("greet", "bow"))
    _git(repo, "commit", "-am", "rename greet → bow")

    backend.calls.clear()
    result = runner.invoke(docagent_cli.app, _update_args(repo))
    assert result.exit_code == 0, result.stdout
    assert sorted(backend.calls) == sorted(REAL_ARTIFACTS)


def test_ts_update_with_no_source_changes_is_no_op(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert "no artifacts affected" in result.stdout.lower()
