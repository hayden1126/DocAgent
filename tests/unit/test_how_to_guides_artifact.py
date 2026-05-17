"""Unit tests for docagent.artifacts.how_to_guides (Phase 6, Plan 05)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from docagent.artifacts.how_to_guides import HowToGuidesArtifact
from docagent.artifacts.registry import GenerationContext
from docagent.backends.base import GenerationRequest, GenerationResponse
from docagent.index.store import open_store

# ---- Test doubles ---------------------------------------------------------------


@dataclass
class _QueueBackend:
    """Backend that pops a canned response off `responses` per call."""

    responses: list[str] = field(default_factory=list)
    name: str = "queue"
    model: str | None = "claude-sonnet-4-6"
    calls: int = 0

    def run(self, request: GenerationRequest) -> GenerationResponse:
        self.calls += 1
        if not self.responses:
            raise RuntimeError("queue exhausted")
        content = self.responses.pop(0)
        return GenerationResponse(
            content=content, tool_calls=0, input_tokens=100, output_tokens=50
        )


def _make_ctx(tmp_path: Path, store, backend, *, max_howtos: int = 15) -> GenerationContext:
    return GenerationContext(
        repo_root=tmp_path,
        store=store,
        backend=backend,
        config={"max_howtos": max_howtos},
    )


def _write_readme(repo: Path, body: str = "# Repo\n\nSome content.\n") -> None:
    (repo / "README.md").write_text(body, encoding="utf-8")


def _discovery_json(*topics: tuple[str, list[str]]) -> str:
    return json.dumps(
        [{"title": title, "sources": list(sources)} for title, sources in topics]
    )


_DEFAULT_PAGE_BODY = (
    "<<<HOWTO_PAGE_BEGIN>>>\n"
    "# Run docagent in CI\n\n"
    "## Goal\nDo the thing. <!-- ground: README.md:1-5 -->\n\n"
    "## Steps\n1. Do step one. <!-- ground: README.md:1-5 -->\n\n"
    "## Verify\nIt worked. <!-- ground: README.md:1-5 -->\n"
    "<<<HOWTO_PAGE_END>>>\n"
)


# ---- plan() coverage -------------------------------------------------------------


def test_plan_returns_one_task_per_discovered_topic(tmp_path: Path) -> None:
    _write_readme(tmp_path)
    store = open_store(tmp_path)
    backend = _QueueBackend(
        responses=[
            _discovery_json(
                ("Run docagent in CI", ["README.md:1-5"]),
                ("Extend docagent with a new artifact", ["README.md:1-5"]),
                ("Configure max cost", ["README.md:1-5"]),
            )
        ]
    )
    art = HowToGuidesArtifact()
    ctx = _make_ctx(tmp_path, store, backend)
    tasks = art.plan(ctx)
    assert len(tasks) == 3
    slugs = sorted(t.payload["slug"] for t in tasks)
    assert slugs == sorted(
        ["run-docagent-in-ci", "extend-docagent-with-a-new-artifact", "configure-max-cost"]
    )
    # Discovery call invoked the backend exactly once.
    assert backend.calls == 1
    store.close()


def test_plan_caps_at_max_howtos(tmp_path: Path) -> None:
    _write_readme(tmp_path)
    store = open_store(tmp_path)
    backend = _QueueBackend(
        responses=[
            _discovery_json(
                ("Topic one", ["README.md:1-5"]),
                ("Topic two", ["README.md:1-5"]),
                ("Topic three", ["README.md:1-5"]),
                ("Topic four", ["README.md:1-5"]),
                ("Topic five", ["README.md:1-5"]),
            )
        ]
    )
    art = HowToGuidesArtifact()
    ctx = _make_ctx(tmp_path, store, backend, max_howtos=2)
    tasks = art.plan(ctx)
    assert len(tasks) == 2
    store.close()


def test_plan_max_howtos_zero_is_unlimited(tmp_path: Path) -> None:
    _write_readme(tmp_path)
    store = open_store(tmp_path)
    backend = _QueueBackend(
        responses=[
            _discovery_json(
                ("Topic one", ["README.md:1-5"]),
                ("Topic two", ["README.md:1-5"]),
                ("Topic three", ["README.md:1-5"]),
            )
        ]
    )
    art = HowToGuidesArtifact()
    ctx = _make_ctx(tmp_path, store, backend, max_howtos=0)
    tasks = art.plan(ctx)
    assert len(tasks) == 3
    store.close()


def test_plan_skips_cache_hit(tmp_path: Path) -> None:
    """A topic whose fingerprint matches the stored value (and file exists) is not re-emitted."""
    _write_readme(tmp_path)
    store = open_store(tmp_path)

    # First run: discover one topic, write the page file, persist fingerprint.
    backend1 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art1 = HowToGuidesArtifact()
    ctx1 = _make_ctx(tmp_path, store, backend1)
    tasks1 = art1.plan(ctx1)
    assert len(tasks1) == 1
    # Simulate the post_write side: persist the fingerprint AND ensure the
    # target file exists (api_reference's plan() conditions on both).
    target = tmp_path / "docs/how-to" / "run-docagent-in-ci.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("page", encoding="utf-8")
    _, fp = art1._planned["run-docagent-in-ci"]
    store.set_unit_fingerprint(
        "how_to_guides", "run-docagent-in-ci", fp, datetime.now(UTC).isoformat()
    )

    # Second run: same topic, sources unchanged → cache hit → zero tasks emitted.
    backend2 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art2 = HowToGuidesArtifact()
    ctx2 = _make_ctx(tmp_path, store, backend2)
    tasks2 = art2.plan(ctx2)
    assert len(tasks2) == 0
    # _slugs_to_write still populated for orphan-check correctness.
    assert art2._slugs_to_write == ["run-docagent-in-ci"]
    store.close()


def test_plan_slug_collision_warns_and_keeps_first(tmp_path: Path) -> None:
    """Two topics whose slugs collide → first wins, warn surfaces into ctx.config."""
    _write_readme(tmp_path)
    store = open_store(tmp_path)
    backend = _QueueBackend(
        responses=[
            _discovery_json(
                ("Run docagent in CI", ["README.md:1-5"]),
                # Same title (case-different) → same slug.
                ("How to Run docagent in CI", ["README.md:6-10"]),
            )
        ]
    )
    art = HowToGuidesArtifact()
    ctx = _make_ctx(tmp_path, store, backend)
    tasks = art.plan(ctx)
    assert len(tasks) == 1
    warnings = ctx.config.get("how_to_warnings", [])
    assert any("slug collision" in w for w in warnings), warnings
    store.close()


def test_plan_per_page_fingerprint_changes_on_source_hash_change(tmp_path: Path) -> None:
    """Per-page fingerprint must differ when a source file's content hash changes."""
    _write_readme(tmp_path)
    store = open_store(tmp_path)

    # Seed file_hashes for README.md = hash_v1.
    now = datetime.now(UTC).isoformat()
    store.upsert_file_hash("README.md", "hash_v1", "markdown", now)
    backend1 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art1 = HowToGuidesArtifact()
    ctx1 = _make_ctx(tmp_path, store, backend1)
    art1.plan(ctx1)
    fp_v1 = art1._planned["run-docagent-in-ci"][1]

    # Bump file_hash and re-plan.
    store.upsert_file_hash("README.md", "hash_v2", "markdown", now)
    backend2 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art2 = HowToGuidesArtifact()
    ctx2 = _make_ctx(tmp_path, store, backend2)
    art2.plan(ctx2)
    fp_v2 = art2._planned["run-docagent-in-ci"][1]

    assert fp_v1 != fp_v2
    store.close()


def test_plan_fingerprint_stable_on_unrelated_file_edit(tmp_path: Path) -> None:
    _write_readme(tmp_path)
    store = open_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    store.upsert_file_hash("README.md", "hash_v1", "markdown", now)
    store.upsert_file_hash("unrelated.py", "u_v1", "python", now)

    backend1 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art1 = HowToGuidesArtifact()
    art1.plan(_make_ctx(tmp_path, store, backend1))
    fp_v1 = art1._planned["run-docagent-in-ci"][1]

    # Change a file not cited by this topic.
    store.upsert_file_hash("unrelated.py", "u_v2", "python", now)
    backend2 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art2 = HowToGuidesArtifact()
    art2.plan(_make_ctx(tmp_path, store, backend2))
    fp_v2 = art2._planned["run-docagent-in-ci"][1]

    assert fp_v1 == fp_v2
    store.close()


# ---- generate() coverage --------------------------------------------------------


def test_generate_composes_full_page(tmp_path: Path) -> None:
    _write_readme(tmp_path)
    store = open_store(tmp_path)
    backend = _QueueBackend(
        responses=[
            _discovery_json(("Run docagent in CI", ["README.md:1-5"])),
            _DEFAULT_PAGE_BODY,
        ]
    )
    art = HowToGuidesArtifact()
    ctx = _make_ctx(tmp_path, store, backend)
    tasks = art.plan(ctx)
    assert len(tasks) == 1
    patch = art.generate(tasks[0], ctx)
    text = patch.new_content.decode("utf-8")
    # Frontmatter present.
    assert text.startswith("---\n")
    assert 'title: "Run docagent in CI"' in text
    assert "slug: run-docagent-in-ci" in text
    # LLM body present.
    assert "# Run docagent in CI" in text
    assert "## Goal" in text
    assert "## Steps" in text
    assert "## Verify" in text
    # Single trailing newline.
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    store.close()


# ---- post_write / orphan-flag coverage ------------------------------------------


def _persist_fingerprint(store, slug: str, fp: str) -> None:
    store.set_unit_fingerprint(
        "how_to_guides", slug, fp, datetime.now(UTC).isoformat()
    )


def test_orphan_check_only_on_last_task(tmp_path: Path) -> None:
    """For a 3-task run, post_write on tasks 0 + 1 does not flag; task 2 does."""
    _write_readme(tmp_path)
    (tmp_path / "docs/how-to").mkdir(parents=True)
    # Pre-existing on-disk pages: an obsolete one that should orphan.
    (tmp_path / "docs/how-to" / "stale-flow.md").write_text("old", encoding="utf-8")

    store = open_store(tmp_path)
    backend = _QueueBackend(
        responses=[
            _discovery_json(
                ("Run docagent in CI", ["README.md:1-5"]),
                ("Extend docagent with a new artifact", ["README.md:1-5"]),
                ("Configure max cost", ["README.md:1-5"]),
            )
        ]
    )
    art = HowToGuidesArtifact()
    ctx = _make_ctx(tmp_path, store, backend)
    tasks = art.plan(ctx)
    assert len(tasks) == 3

    # Fake the writer: just create the target file so post_write can persist
    # the fingerprint correctly.
    from docagent.artifacts.registry import DocPatch

    def _patch_for(slug: str) -> DocPatch:
        target = tmp_path / "docs/how-to" / f"{slug}.md"
        target.write_text("body", encoding="utf-8")
        return DocPatch(
            artifact_id="how_to_guides",
            target_path=target,
            new_content=b"body",
            prompt_version="1",
        )

    # post_write task 0 + 1: orphans must NOT be present yet.
    art.post_write(_patch_for("run-docagent-in-ci"), ctx)
    assert "how_to_orphans" not in ctx.config or not ctx.config["how_to_orphans"]
    art.post_write(_patch_for("extend-docagent-with-a-new-artifact"), ctx)
    assert "how_to_orphans" not in ctx.config or not ctx.config["how_to_orphans"]

    # post_write task 2 (the LAST): orphans now flagged.
    art.post_write(_patch_for("configure-max-cost"), ctx)
    orphans = ctx.config["how_to_orphans"]
    assert any("stale-flow.md" in o for o in orphans), orphans
    store.close()


def test_orphan_check_on_zero_task_run(tmp_path: Path) -> None:
    """When every page is a cache-hit (zero tasks emitted), the orphan check still fires from plan()."""
    _write_readme(tmp_path)
    (tmp_path / "docs/how-to").mkdir(parents=True)
    (tmp_path / "docs/how-to" / "stale-flow.md").write_text("old", encoding="utf-8")
    target_kept = tmp_path / "docs/how-to" / "run-docagent-in-ci.md"
    target_kept.write_text("kept", encoding="utf-8")

    store = open_store(tmp_path)

    # First run to populate the fingerprint cache.
    backend1 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art1 = HowToGuidesArtifact()
    ctx1 = _make_ctx(tmp_path, store, backend1)
    art1.plan(ctx1)
    _, fp = art1._planned["run-docagent-in-ci"]
    _persist_fingerprint(store, "run-docagent-in-ci", fp)

    # Second run: same topic, cache-hit → zero tasks, orphan-check still fires.
    backend2 = _QueueBackend(
        responses=[_discovery_json(("Run docagent in CI", ["README.md:1-5"]))]
    )
    art2 = HowToGuidesArtifact()
    ctx2 = _make_ctx(tmp_path, store, backend2)
    tasks2 = art2.plan(ctx2)
    assert tasks2 == []
    orphans = ctx2.config.get("how_to_orphans", [])
    assert any("stale-flow.md" in o for o in orphans), orphans
    store.close()


# ---- builtins/registry coverage -------------------------------------------------


def test_builtins_register_how_to_guides() -> None:
    from docagent.artifacts.builtins import register_v1_builtins
    from docagent.artifacts.registry import Registry

    reg = Registry()
    register_v1_builtins(reg)
    artifact_ids = [a.id for a in reg.all()]
    assert "how_to_guides" in artifact_ids
    how_to = reg.get("how_to_guides")
    assert how_to.depends_on == ("readme", "api_reference")


# ---- CLI flag coverage ----------------------------------------------------------


def test_cli_max_howtos_flag_appears_in_init_help() -> None:
    from typer.testing import CliRunner

    from docagent.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "--max-howtos" in result.stdout


def test_cli_max_howtos_flag_appears_in_update_help() -> None:
    from typer.testing import CliRunner

    from docagent.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "--max-howtos" in result.stdout
