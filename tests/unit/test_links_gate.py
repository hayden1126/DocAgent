"""Tests for the internal link checker gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from docagent.artifacts.registry import DocPatch, GenerationContext
from docagent.verify import links


def _patch(content: str, target: str = "out.md") -> DocPatch:
    return DocPatch(
        artifact_id="t", target_path=Path(target), new_content=content.encode("utf-8")
    )


def _ctx(repo_root: Path) -> GenerationContext:
    return GenerationContext(repo_root=repo_root, store=None, backend=None)


def test_relative_path_exists_passes(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("hi")
    ok, findings = links.check(_patch("See [docs](real.md)."), _ctx(tmp_path))
    assert ok
    assert list(findings) == []


def test_relative_path_missing_fails(tmp_path: Path) -> None:
    ok, findings = links.check(_patch("See [docs](missing.md)."), _ctx(tmp_path))
    assert not ok
    assert any("missing.md" in f for f in findings)


def test_external_url_skipped(tmp_path: Path) -> None:
    body = "[a](https://example.com) and [b](http://foo) and [c](mailto:x@y)"
    ok, findings = links.check(_patch(body), _ctx(tmp_path))
    assert ok, findings


def test_in_doc_anchor_resolves_to_heading(tmp_path: Path) -> None:
    body = "# Project\n\n## Install steps\n\nSee [install](#install-steps)."
    ok, findings = links.check(_patch(body), _ctx(tmp_path))
    assert ok, findings


def test_in_doc_anchor_missing_fails(tmp_path: Path) -> None:
    body = "# Project\n\nSee [missing](#nonexistent)."
    ok, findings = links.check(_patch(body), _ctx(tmp_path))
    assert not ok
    assert any("#nonexistent" in f for f in findings)


def test_image_links_validated(tmp_path: Path) -> None:
    ok, findings = links.check(_patch("![alt](missing.png)"), _ctx(tmp_path))
    assert not ok
    assert any("missing.png" in f for f in findings)


def test_reference_style_definitions_validated(tmp_path: Path) -> None:
    body = "[ref]: missing.md\n\nSee [the docs][ref]."
    ok, findings = links.check(_patch(body), _ctx(tmp_path))
    assert not ok


def test_path_with_anchor_validates_file_only(tmp_path: Path) -> None:
    """v1 only checks the file part of ``path.md#anchor``, not the anchor."""
    (tmp_path / "guide.md").write_text("# Guide\n## Step 1\n")
    body = "See [step 1](guide.md#anywhere)."
    ok, _ = links.check(_patch(body), _ctx(tmp_path))
    assert ok


def test_path_traversal_outside_repo_rejected(tmp_path: Path) -> None:
    inner = tmp_path / "inner"
    inner.mkdir()
    # Pretend repo_root is `inner`; the link tries to escape via ../
    body = "[secret](../passwords.txt)"
    ok, findings = links.check(_patch(body), _ctx(inner))
    assert not ok


def test_slug_drops_punctuation_lowercases_collapses_spaces() -> None:
    body = "# Why DocAgent?\n\nSee [why](#why-docagent)."
    ok, _ = links.check(_patch(body), _ctx(Path("/tmp")))
    assert ok


def test_anchors_handle_unicode_in_heading() -> None:
    body = "# Café\n\nSee [café](#café)."
    ok, _ = links.check(_patch(body), _ctx(Path("/tmp")))
    assert ok


def test_duplicate_inline_links_only_checked_once(tmp_path: Path) -> None:
    # Same broken url repeated — we report one finding, not many.
    body = "[a](missing.md) and again [a](missing.md) and [a](missing.md)"
    ok, findings = links.check(_patch(body), _ctx(tmp_path))
    assert not ok
    missing_findings = [f for f in findings if "missing.md" in f]
    assert len(missing_findings) == 1
