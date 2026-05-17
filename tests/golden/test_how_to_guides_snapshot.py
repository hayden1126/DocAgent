"""Golden snapshot test for `how_to_guides` (Phase 6, Plan 06).

Exercises the multi-call path: one canned discovery JSON + two canned
per-page markdown bodies. Asserts both pages render byte-identically to
committed snapshots, and that the orphan-flag variant correctly surfaces
a pre-existing page whose slug no longer appears in discovery.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docagent.artifacts.how_to_guides import HowToGuidesArtifact
from docagent.artifacts.registry import GenerationContext
from docagent.index.store import open_store
from tests.golden._harness import (
    FIXTURES_DIR,
    RECORDINGS_DIR,
    RecordedBackend,
    assert_or_update_snapshot,
)

_HOWTO_RECORDINGS = RECORDINGS_DIR / "how_to_guides"


def _build_fixture(tmp_path: Path) -> Path:
    """Copy the tinylib fixture into tmp_path and seed README + docs/reference."""
    src = FIXTURES_DIR / "tinylib"
    dest = tmp_path / "tinylib"
    shutil.copytree(src, dest)
    # Seed a minimal README so README.md:1-40 citations resolve.
    readme_lines = [f"# tinylib  ({i})" if i == 1 else f"line {i}" for i in range(1, 50)]
    (dest / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    # Seed a docs/reference/ entry so the discovery prompt sees it AND so
    # tinylib.cli.md:1-30 citations resolve.
    ref_dir = dest / "docs" / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_lines = [f"reference line {i}" for i in range(1, 40)]
    (ref_dir / "tinylib.cli.md").write_text(
        "\n".join(ref_lines) + "\n", encoding="utf-8"
    )
    return dest


def _load_recordings() -> list[str]:
    return [
        (_HOWTO_RECORDINGS / "discovery.json").read_text(encoding="utf-8"),
        (_HOWTO_RECORDINGS / "page_run-docagent-in-ci.md").read_text(encoding="utf-8"),
        (
            _HOWTO_RECORDINGS / "page_extend-docagent-with-a-new-artifact.md"
        ).read_text(encoding="utf-8"),
    ]


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    return _build_fixture(tmp_path)


def test_how_to_guides_snapshot(fixture_repo: Path) -> None:
    """End-to-end: discovery + two per-page calls produce stable snapshots."""
    store = open_store(fixture_repo)
    # Seed file hashes so the per-page fingerprint is deterministic.
    now = datetime.now(UTC).isoformat()
    store.upsert_file_hash("README.md", "h_readme", "markdown", now)
    store.upsert_file_hash("docs/reference/tinylib.cli.md", "h_ref", "markdown", now)

    backend = RecordedBackend(responses=_load_recordings())
    art = HowToGuidesArtifact()
    ctx = GenerationContext(
        repo_root=fixture_repo,
        store=store,
        backend=backend,
        config={"max_howtos": 15},
    )
    tasks = art.plan(ctx)
    assert len(tasks) == 2
    # Topics are emitted in discovery order — assert deterministic ordering.
    slugs = [t.payload["slug"] for t in tasks]
    assert slugs == [
        "run-docagent-in-ci",
        "extend-docagent-with-a-new-artifact",
    ], f"unexpected slug order: {slugs}"

    for task in tasks:
        patch = art.generate(task, ctx)
        slug = task.payload["slug"]
        actual = patch.new_content.decode("utf-8")
        assert_or_update_snapshot(f"how_to_guides/{slug}.md", actual)

    # No prior on-disk pages → no orphans.
    assert ctx.config.get("how_to_orphans", []) == []
    store.close()


def test_how_to_guides_snapshot_flags_orphan(fixture_repo: Path) -> None:
    """A pre-existing page absent from discovery is flagged as orphan after the last task."""
    # Pre-populate an out-of-date page in the fixture's docs/how-to/.
    howto_dir = fixture_repo / "docs" / "how-to"
    howto_dir.mkdir(parents=True)
    (howto_dir / "legacy-flow.md").write_text("legacy", encoding="utf-8")

    store = open_store(fixture_repo)
    now = datetime.now(UTC).isoformat()
    store.upsert_file_hash("README.md", "h_readme", "markdown", now)
    store.upsert_file_hash("docs/reference/tinylib.cli.md", "h_ref", "markdown", now)

    backend = RecordedBackend(responses=_load_recordings())
    art = HowToGuidesArtifact()
    ctx = GenerationContext(
        repo_root=fixture_repo,
        store=store,
        backend=backend,
        config={"max_howtos": 15},
    )
    tasks = art.plan(ctx)
    assert len(tasks) == 2

    # Simulate the orchestrator: generate, then post_write on each. The
    # orphan flag fires on the LAST post_write.
    for i, task in enumerate(tasks):
        patch = art.generate(task, ctx)
        # Write the page to disk so post_write's fingerprint persist works.
        task.target_path.parent.mkdir(parents=True, exist_ok=True)
        task.target_path.write_bytes(patch.new_content)
        art.post_write(patch, ctx)
        if i < len(tasks) - 1:
            assert "how_to_orphans" not in ctx.config or not ctx.config["how_to_orphans"]

    orphans = ctx.config.get("how_to_orphans", [])
    assert any("legacy-flow.md" in o for o in orphans), orphans
    store.close()
