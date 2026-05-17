"""Unit tests for docagent.artifacts._how_to_render (Phase 6, Plan 03)."""

from __future__ import annotations

from docagent.artifacts._how_to_render import (
    assemble_page,
    render_frontmatter,
    render_see_also,
)

# ---- render_see_also ------------------------------------------------------------


def test_see_also_empty_inputs_returns_empty() -> None:
    assert render_see_also(related_modules=[], related_slugs=[]) == ""


def test_see_also_one_module() -> None:
    out = render_see_also(related_modules=["docagent.cli"], related_slugs=[])
    assert "## See also" in out
    assert "- [docagent.cli](../reference/docagent.cli.md)" in out
    assert out.endswith("\n")


def test_see_also_modules_sorted() -> None:
    out = render_see_also(
        related_modules=["docagent.cli", "docagent.artifacts"], related_slugs=[]
    )
    lines = out.splitlines()
    idx_artifacts = next(
        i for i, ln in enumerate(lines) if "docagent.artifacts" in ln
    )
    idx_cli = next(i for i, ln in enumerate(lines) if "docagent.cli" in ln)
    assert idx_artifacts < idx_cli, f"modules not alphabetically sorted: {lines!r}"


def test_see_also_siblings_use_relative_md_form() -> None:
    out = render_see_also(related_modules=[], related_slugs=["other-flow"])
    assert "- [other-flow](./other-flow.md)" in out


def test_see_also_modules_first_then_siblings_both_sorted() -> None:
    out = render_see_also(
        related_modules=["docagent.cli", "docagent.artifacts"],
        related_slugs=["zeta-flow", "alpha-flow"],
    )
    lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    # modules first (sorted), siblings second (sorted)
    assert "docagent.artifacts" in lines[0]
    assert "docagent.cli" in lines[1]
    assert "alpha-flow" in lines[2]
    assert "zeta-flow" in lines[3]


def test_see_also_determinism() -> None:
    out1 = render_see_also(
        related_modules=["docagent.cli"], related_slugs=["other"]
    )
    out2 = render_see_also(
        related_modules=["docagent.cli"], related_slugs=["other"]
    )
    assert out1 == out2


# ---- render_frontmatter ---------------------------------------------------------


def test_frontmatter_starts_and_ends_with_marker() -> None:
    out = render_frontmatter(title="Run docagent in CI", slug="run-docagent-in-ci")
    assert out.startswith("---\n")
    assert out.endswith("---\n")
    assert "Run docagent in CI" in out
    assert "run-docagent-in-ci" in out


def test_frontmatter_determinism() -> None:
    a = render_frontmatter(title="Foo", slug="foo")
    b = render_frontmatter(title="Foo", slug="foo")
    assert a == b


# ---- assemble_page --------------------------------------------------------------


def test_assemble_all_three_non_empty() -> None:
    fm = "---\ntitle: x\n---\n"
    body = "# X\n\nBody."
    see_also = "## See also\n\n- [y](./y.md)\n"
    out = assemble_page(frontmatter=fm, body=body, see_also=see_also)
    # All sections present, single blank line between non-empty sections.
    assert fm.rstrip("\n") in out
    assert "# X" in out
    assert "## See also" in out
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_assemble_empty_frontmatter_no_leading_blank_line() -> None:
    out = assemble_page(
        frontmatter="",
        body="# X\n\nBody.",
        see_also="## See also\n\n- [y](./y.md)\n",
    )
    assert not out.startswith("\n")


def test_assemble_empty_see_also_ends_clean() -> None:
    out = assemble_page(frontmatter="", body="# X\n\nBody.", see_also="")
    # Output ends with exactly one trailing \n.
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_assemble_always_one_trailing_newline() -> None:
    for fm, body, sa in [
        ("---\nx: 1\n---\n", "# X", "## See also\n- z\n"),
        ("", "# X", ""),
        ("---\nx: 1\n---\n", "# X", ""),
        ("", "# X", "## See also\n- z\n"),
    ]:
        out = assemble_page(frontmatter=fm, body=body, see_also=sa)
        assert out.endswith("\n")
        assert not out.endswith("\n\n")
