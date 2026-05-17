"""End-to-end integration tests for ``api_reference``.

The first multi-file artifact: one page per Python module under
``docs/reference/<dotted>.md``. These tests pin: page placement, deterministic
+ LLM-spliced content, per-module fingerprint persistence, idempotent second
runs, source-change re-generation, and the ``--max-modules`` cap.
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
    """Returns deterministic marker-delimited content. Tracks calls."""

    name = "scripted"
    model: str | None = None

    def __init__(self, body_by_module: dict[str, str] | None = None) -> None:
        self._content = body_by_module or {}
        self.calls: list[str] = []
        self.module_calls: list[str] = []

    def run(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request.artifact_id)
        # Extract the dotted module name from the prompt itself (the artifact
        # interpolates it on line 1 so we can dispatch per-module responses).
        line = request.prompt.splitlines()[1]
        dotted = line.split("`", 2)[1] if "`" in line else "?"
        self.module_calls.append(dotted)
        body = self._content.get(dotted, _default_body(dotted))
        return GenerationResponse(content=body)


def _default_body(dotted: str) -> str:
    """A grounded, marker-delimited response that always passes the citations
    gate when the fixture's `tinylib/cli.py` is present."""
    return (
        "<<<OPENER>>>\n"
        f"The `{dotted}` module exposes a CLI entry point. "
        "<!-- ground: tinylib/cli.py:1-13 -->\n"
        "\n"
        "<<<WORKFLOWS>>>\n"
        "```python\n"
        "from tinylib.cli import greet\n"
        'greet("world")\n'
        "```\n"
        "<!-- ground: tinylib/cli.py:10-13 -->\n"
    )


def _patch_backend(monkeypatch, backend) -> None:
    monkeypatch.setattr(
        "docagent.backends.agent_sdk.AgentSDKBackend", lambda *a, **kw: backend
    )


def _init_args(repo: Path, *only: str) -> list[str]:
    args = ["init", "-C", str(repo)]
    for aid in only:
        args += ["--only", aid]
    return args


def _query(repo: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(repo / ".docagent" / "index.db")
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


def test_init_writes_one_page_per_public_module(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _ScriptedBackend()
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()

    result = runner.invoke(
        docagent_cli.app, _init_args(repo, "api_reference")
    )
    assert result.exit_code == 0, result.stdout

    # tinylib.cli has the only public symbol (`greet`); tinylib.__init__ has
    # only `__version__` which is private and gets the whole module dropped.
    page = repo / "docs" / "reference" / "tinylib.cli.md"
    assert page.is_file()
    content = page.read_text(encoding="utf-8")
    # Deterministic infrastructure.
    assert "docagent_artifact: api_reference" in content
    assert "# `tinylib.cli`" in content
    assert "## Public surface" in content
    assert "`greet`" in content
    # LLM-supplied chunks were spliced.
    assert "module exposes a CLI" in content
    assert "from tinylib.cli import greet" in content
    # Citation grounded.
    assert "<!-- ground: tinylib/cli.py" in content


def test_init_records_fingerprint(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _ScriptedBackend()
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()
    runner.invoke(docagent_cli.app, _init_args(repo, "api_reference"))

    rows = _query(
        repo,
        "SELECT artifact_id, unit_key, fingerprint FROM artifact_unit_fingerprints",
    )
    assert len(rows) == 1
    aid, unit_key, fingerprint = rows[0]
    assert aid == "api_reference"
    assert unit_key == "tinylib.cli"
    assert len(fingerprint) == 64  # sha256 hex


def test_second_run_is_no_op_when_source_unchanged(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _ScriptedBackend()
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()

    # First run: one LLM call for tinylib.cli.
    runner.invoke(docagent_cli.app, _init_args(repo, "api_reference"))
    assert backend.module_calls == ["tinylib.cli"]

    # Second run: fingerprint matches → no LLM call.
    backend.module_calls.clear()
    result = runner.invoke(docagent_cli.app, _init_args(repo, "api_reference"))
    assert result.exit_code == 0, result.stdout
    assert backend.module_calls == []


def test_source_change_re_generates_affected_module(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _ScriptedBackend()
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()

    runner.invoke(docagent_cli.app, _init_args(repo, "api_reference"))
    assert backend.module_calls == ["tinylib.cli"]

    # Touch cli.py — its file_hash changes, so the fingerprint changes too.
    cli_file = repo / "tinylib" / "cli.py"
    cli_file.write_text(cli_file.read_text() + "\n# updated\n")

    backend.module_calls.clear()
    result = runner.invoke(docagent_cli.app, _init_args(repo, "api_reference"))
    assert result.exit_code == 0, result.stdout
    assert backend.module_calls == ["tinylib.cli"]


def test_max_modules_cap_truncates_planned_work(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Add a second documentable module, cap at 1, expect only the first
    (lexicographically) module to be planned."""
    # Add a second module with a public symbol.
    extra = repo / "tinylib" / "extra.py"
    extra.write_text(
        '"""Extra module."""\n\n'
        "def aardvark() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    backend = _ScriptedBackend()
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()

    result = runner.invoke(
        docagent_cli.app,
        [*_init_args(repo, "api_reference"), "--max-modules", "1"],
    )
    assert result.exit_code == 0, result.stdout
    # Lexicographic order: tinylib.cli sorts before tinylib.extra.
    assert backend.module_calls == ["tinylib.cli"]
    assert (repo / "docs" / "reference" / "tinylib.cli.md").is_file()
    assert not (repo / "docs" / "reference" / "tinylib.extra.md").is_file()


def test_multiple_modules_each_get_a_page(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two public modules → two pages, both with see-also referencing the
    other (which the link checker must allow via _future_paths)."""
    extra = repo / "tinylib" / "extra.py"
    extra.write_text(
        '"""Extra module."""\n\n'
        "def aardvark() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    backend = _ScriptedBackend()
    _patch_backend(monkeypatch, backend)
    runner = CliRunner()

    result = runner.invoke(docagent_cli.app, _init_args(repo, "api_reference"))
    assert result.exit_code == 0, result.stdout
    assert sorted(backend.module_calls) == ["tinylib.cli", "tinylib.extra"]

    cli_page = (repo / "docs" / "reference" / "tinylib.cli.md").read_text()
    extra_page = (repo / "docs" / "reference" / "tinylib.extra.md").read_text()

    # Each cites the other in see-also — and the verify pipeline didn't fail
    # the run even though the sibling page wasn't on disk yet at the moment
    # of generation.
    assert "tinylib.extra.md" in cli_page
    assert "tinylib.cli.md" in extra_page
