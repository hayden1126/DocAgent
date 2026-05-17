"""Unit tests for ``ApiReferenceArtifact``'s internal contracts.

These cover behaviors that don't need a full CLI invocation: the marker-
parsing helper, the type guard on task payloads, the ``post_write`` early
return when state is missing, and the ``--max-modules 0`` "unlimited" case.

Full plan→generate→write flow is covered in
``tests/integration/test_api_reference_flow.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from docagent.artifacts._module_discovery import DiscoveredModule, ModuleSymbol
from docagent.artifacts.api_reference import (
    ApiReferenceArtifact,
    _DEFAULT_MAX_MODULES,
    _split_marker_output,
)
from docagent.artifacts.registry import DocPatch, GenerationContext, Task
from docagent.index.store import open_store


# ---- _split_marker_output --------------------------------------------------


def test_split_no_markers_yields_empty_tuple() -> None:
    """If the LLM returns prose without markers, both sections are empty so
    the artifact falls back to its placeholder text."""
    assert _split_marker_output("Just some narrative prose, no markers.") == ("", "")


def test_split_opener_only_returns_opener_with_empty_workflows() -> None:
    text = (
        "<<<OPENER>>>\n"
        "The module does things. <!-- ground: foo.py:1-5 -->\n"
    )
    opener, workflows = _split_marker_output(text)
    assert "module does things" in opener
    assert workflows == ""


def test_split_workflows_before_opener_treated_as_opener_only() -> None:
    """If the LLM emits WORKFLOWS before OPENER, the splitter still finds
    OPENER and treats the remainder as opener text. Workflows is empty —
    the assemble_page fallback fills it with a placeholder."""
    text = (
        "<<<WORKFLOWS>>>\nstray\n<<<OPENER>>>\nThe opener body.\n"
    )
    opener, workflows = _split_marker_output(text)
    # The OPENER marker is found, everything after it is the opener.
    assert "opener body" in opener
    assert workflows == ""


def test_split_strips_whitespace_around_section_content() -> None:
    text = (
        "preamble that gets discarded\n"
        "<<<OPENER>>>\n\n   opener text   \n\n"
        "<<<WORKFLOWS>>>\n\n   workflow block   \n"
    )
    opener, workflows = _split_marker_output(text)
    assert opener == "opener text"
    assert workflows == "workflow block"


def test_split_preamble_before_opener_is_discarded() -> None:
    text = "ignored prelude\n<<<OPENER>>>\nreal\n<<<WORKFLOWS>>>\nblock\n"
    opener, workflows = _split_marker_output(text)
    assert opener == "real"
    assert workflows == "block"


def test_split_empty_between_markers_returns_empty_strings() -> None:
    text = "<<<OPENER>>>\n<<<WORKFLOWS>>>\n"
    opener, workflows = _split_marker_output(text)
    assert opener == ""
    assert workflows == ""


# ---- type guard on payload -------------------------------------------------


class _StubStoreBackend:
    """Minimal stand-ins for the ``generate`` type-guard test."""

    def __init__(self) -> None:
        self.model = None


def test_generate_raises_typeerror_when_payload_dotted_name_is_not_str(
    tmp_path: Path,
) -> None:
    """The payload key must be a ``str``. ``assert`` would silently strip
    under ``python -O``; the guard is a real raise instead."""
    art = ApiReferenceArtifact()
    store = open_store(tmp_path)
    ctx = GenerationContext(
        repo_root=tmp_path,
        store=store,
        backend=_StubStoreBackend(),  # type: ignore[arg-type]
    )
    task = Task(
        artifact_id=art.id,
        target_path=tmp_path / "docs" / "reference" / "x.md",
        payload={"dotted_name": 42},  # wrong type
    )
    with pytest.raises(TypeError, match="dotted_name"):
        art.generate(task, ctx)
    store.close()


# ---- post_write early return -----------------------------------------------


def test_post_write_returns_silently_when_stem_not_planned(tmp_path: Path) -> None:
    """If ``post_write`` is invoked with a patch the artifact didn't plan
    (e.g. a stale call after state was cleared), it must not write a stale
    fingerprint and must not raise."""
    art = ApiReferenceArtifact()
    # _planned is empty by default.
    store = open_store(tmp_path)
    ctx = GenerationContext(repo_root=tmp_path, store=store, backend=None)  # type: ignore[arg-type]
    patch = DocPatch(
        artifact_id=art.id,
        target_path=tmp_path / "docs" / "reference" / "unknown.md",
        new_content=b"",
    )

    # Should not raise; should not write a row.
    art.post_write(patch, ctx)

    conn = sqlite3.connect(tmp_path / ".docagent" / "index.db")
    try:
        rows = conn.execute(
            "SELECT * FROM artifact_unit_fingerprints WHERE artifact_id = ?",
            (art.id,),
        ).fetchall()
    finally:
        conn.close()
    assert rows == []
    store.close()


# ---- --max-modules 0 means unlimited ---------------------------------------


def _seed_python_symbols(store, files: dict[str, list[str]]) -> None:
    """Seed the symbols table with public functions for each file."""
    for file, names in files.items():
        rows = [
            (name, "function", file, 0, 0, 1, 1, f"def {name}()", None, "python", "h")
            for name in names
        ]
        store.replace_symbols_for_file(file, rows)
        store.upsert_file_hash(file, "h", "python", "2026-01-01T00:00:00Z")


def test_max_modules_zero_means_unlimited(tmp_path: Path) -> None:
    """``--max-modules 0`` disables the cap entirely. Otherwise large repos
    with more than the default modules would silently truncate."""
    art = ApiReferenceArtifact()
    store = open_store(tmp_path)
    # Seed many modules — more than the default cap.
    files = {f"pkg/mod{i:02d}.py": [f"public_{i}"] for i in range(_DEFAULT_MAX_MODULES + 5)}
    _seed_python_symbols(store, files)

    ctx = GenerationContext(
        repo_root=tmp_path,
        store=store,
        backend=_StubStoreBackend(),  # type: ignore[arg-type]
        config={"max_modules": 0},
    )
    tasks = art.plan(ctx)
    assert len(tasks) == _DEFAULT_MAX_MODULES + 5
    store.close()


def test_max_modules_default_applies_when_unset(tmp_path: Path) -> None:
    """Without a config override, the default cap kicks in."""
    art = ApiReferenceArtifact()
    store = open_store(tmp_path)
    files = {f"pkg/mod{i:02d}.py": [f"public_{i}"] for i in range(_DEFAULT_MAX_MODULES + 3)}
    _seed_python_symbols(store, files)

    ctx = GenerationContext(
        repo_root=tmp_path,
        store=store,
        backend=_StubStoreBackend(),  # type: ignore[arg-type]
        # No max_modules key — defaults apply.
    )
    tasks = art.plan(ctx)
    assert len(tasks) == _DEFAULT_MAX_MODULES
    store.close()
