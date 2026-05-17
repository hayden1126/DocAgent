"""Golden snapshot test for ``api_reference`` on a TypeScript repo.

Exercises the Phase-7 end-to-end path: enriched ``tinylib_ts`` fixture with
a ``package.json#exports`` map (3 subpaths), one private-only module
(``src/_internal.ts``), one barrel file (``src/barrel.ts``), and a
JSDoc-bearing function (``src/cli.ts::greet``). Asserts:

* Three pages render — one for each ``exports`` entry (``cli``, ``index``,
  ``types``); no pages for the private or barrel modules.
* The JSDoc brief shows up in the rendered page (Plan 07-01 wiring +
  Plan 07-05 renderer extension).
* The merged ``--max-modules`` cap surfaces only the alphabetically-first N.
* The TS fixture's recorded-backend state is committed under
  ``tests/golden/fixtures/tinylib_ts/.docagent`` (per CLAUDE.md "fixture
  state directories are intentionally committed" gotcha).
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docagent.adapters.typescript import TypeScriptAdapter
from docagent.artifacts.api_reference import ApiReferenceArtifact
from docagent.artifacts.registry import GenerationContext, Task
from docagent.index.store import open_store
from tests.golden._harness import (
    FIXTURES_DIR,
    RecordedBackend,
    assert_or_update_snapshot,
)

# Canned LLM response with both markers and a single grounded citation.
# Repeated for every per-module call (the RecordedBackend replays the
# single recording_path on each invocation when ``responses`` is empty;
# for this test we use ``responses`` so each call is fresh).
_RECORDED_RESPONSE_TEMPLATE = (
    "<<<OPENER>>>\n"
    "This module is part of the tinylib-ts fixture. "
    "<!-- ground: src/{file}:1-5 -->\n"
    "<<<WORKFLOWS>>>\n"
    "```typescript\n"
    "// example placeholder\n"
    "```\n"
    "<!-- ground: src/{file}:1-5 -->\n"
)


def _make_response(file_basename: str) -> str:
    return _RECORDED_RESPONSE_TEMPLATE.format(file=file_basename)


def _seed_ts_symbols(store: object, repo: Path) -> None:
    """Walk the fixture's .ts files, parse each, and seed the symbols +
    file_hashes tables with the same rows the real scanner would produce.

    Skips ``barrel.ts`` (no original definitions — extract_symbols returns
    [], and seeding zero rows for a file is a no-op).
    """
    adapter = TypeScriptAdapter()
    now = datetime.now(UTC).isoformat()
    for ts_file in sorted(repo.rglob("*.ts")):
        if "/.docagent/" in ts_file.as_posix():
            continue
        rel = ts_file.relative_to(repo).as_posix()
        src = ts_file.read_bytes()
        parsed = adapter.parse(ts_file, src)
        symbols = adapter.extract_symbols(parsed)
        rows = [
            (
                s.qualified_name,
                s.kind,
                rel,
                s.byte_start,
                s.byte_end,
                s.line_start,
                s.line_end,
                s.signature,
                s.existing_doc,
                "typescript",
                f"h_{rel}",
            )
            for s in symbols
        ]
        if rows:
            store.replace_symbols_for_file(rel, rows)  # type: ignore[attr-defined]
        store.upsert_file_hash(rel, f"h_{rel}", "typescript", now)  # type: ignore[attr-defined]


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    src = FIXTURES_DIR / "tinylib_ts"
    dest = tmp_path / "tinylib_ts"
    shutil.copytree(src, dest)
    return dest


def _orchestrate(
    repo: Path, *, max_modules: int = 25
) -> tuple[list[Task], dict[str, str]]:
    """Drive plan → generate end-to-end against the recorded backend.

    Returns (tasks, page_contents) where page_contents maps dotted_name to
    the rendered Markdown body (utf-8 string).
    """
    store = open_store(repo)
    try:
        _seed_ts_symbols(store, repo)

        # Three responses for three modules; the actual order is sorted by
        # dotted_name (cli, index, types) so the response list aligns.
        backend = RecordedBackend(
            responses=[
                _make_response("cli.ts"),
                _make_response("index.ts"),
                _make_response("types.ts"),
            ]
        )
        art = ApiReferenceArtifact()
        ctx = GenerationContext(
            repo_root=repo,
            store=store,
            backend=backend,
            config={"max_modules": max_modules},
        )
        tasks = art.plan(ctx)
        page_contents: dict[str, str] = {}
        for task in tasks:
            patch = art.generate(task, ctx)
            page_contents[str(task.payload["dotted_name"])] = patch.new_content.decode(
                "utf-8"
            )
        return tasks, page_contents
    finally:
        store.close()


def test_api_reference_ts_renders_three_pages(fixture_repo: Path) -> None:
    """The enriched fixture surfaces exactly three modules: cli, index, types.

    The private module (``_internal``) and the pure-barrel module
    (``barrel``) are dropped by the discovery cascade — neither should
    appear in the task set.
    """
    tasks, pages = _orchestrate(fixture_repo)
    dotted = sorted(str(t.payload["dotted_name"]) for t in tasks)
    assert dotted == ["cli", "index", "types"], dotted
    # _internal and barrel must be filtered out.
    assert "_internal" not in pages
    assert "barrel" not in pages


def test_api_reference_ts_page_has_jsdoc_summary(fixture_repo: Path) -> None:
    """The JSDoc brief on ``cli.greet`` flows through to the rendered page.

    Plan 07-01 stores the brief in ``Symbol.existing_doc``; Plan 07-05's
    renderer surfaces it after a ``" — "`` separator in the Signature
    column.
    """
    _, pages = _orchestrate(fixture_repo)
    cli_page = pages["cli"]
    assert "Greet the user with their name." in cli_page


def test_api_reference_ts_max_modules_cap_combined(fixture_repo: Path) -> None:
    """``--max-modules 2`` slices to the alphabetically-first 2 modules
    (cli, index) — the cap applies to the merged, sorted list."""
    tasks, pages = _orchestrate(fixture_repo, max_modules=2)
    dotted = sorted(str(t.payload["dotted_name"]) for t in tasks)
    assert dotted == ["cli", "index"], dotted
    # types is held out by the cap.
    assert "types" not in pages


def test_api_reference_ts_snapshot_cli_page(fixture_repo: Path) -> None:
    """Byte-equal snapshot for the cli.md page — the most interesting one
    (has JSDoc-derived brief in the table)."""
    _, pages = _orchestrate(fixture_repo)
    assert_or_update_snapshot("api_reference_ts/cli.md", pages["cli"])


def test_api_reference_ts_snapshot_types_page(fixture_repo: Path) -> None:
    """Byte-equal snapshot for the types.md page — exercises type_alias rows
    and a single-from-exports module."""
    _, pages = _orchestrate(fixture_repo)
    assert_or_update_snapshot("api_reference_ts/types.md", pages["types"])
