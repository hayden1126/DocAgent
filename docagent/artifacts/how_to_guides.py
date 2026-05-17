"""``how_to_guides`` — Diátaxis how-to pages discovered by LLM.

Multi-file artifact. ``plan()`` issues ONE discovery LLM call to enumerate
user-task topics from the README + ``docs/reference/*.md`` set; each topic
becomes one task. ``generate()`` issues one LLM call per topic, splits the
marker-delimited body, and composes the page (deterministic frontmatter +
LLM body + deterministic ``## See also``). ``post_write()`` persists the
per-page fingerprint and — on the LAST task only — flags orphan pages
whose sources no longer appear in discovery.

Topics → slugs → filenames live at ``docs/how-to/<slug>.md``. The
fingerprint cache reuses Phase 4's ``artifact_unit_fingerprints`` table
with ``unit_key = slug``.

What we deliberately don't do here:
- No automatic deletion of orphan pages (flag-only in v1; users may have
  manually polished a page the LLM later stopped suggesting).
- No per-page ``--only how_to_guides:<slug>`` filtering (v2).
- No user-editable topic list (no ``docs/how-to/_topics.yaml``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from docagent._logging import get_logger
from docagent.artifacts._how_to_render import (
    assemble_page,
    render_frontmatter,
    render_see_also,
)
from docagent.artifacts._topic_discovery import (
    Topic,
    dedupe_topics,
    topic_slug,
)
from docagent.artifacts.registry import (
    Audience,
    DocPatch,
    GenerationContext,
    Task,
    VerifyResult,
)
from docagent.backends.base import GenerationRequest
from docagent.prompts.how_to_guides import (
    FOOTER_MARKER,
    HEADER_MARKER,
    PROMPT_VERSION,
    build_discovery_prompt,
    build_page_prompt,
)

_log = get_logger("artifacts.how_to_guides")

_DEFAULT_MAX_HOWTOS = 15


def _source_file_path(source: str) -> str:
    """Strip the ``:start-end`` line range from a citation, leaving the path."""
    return source.split(":", 1)[0]


def _split_marker_output(text: str) -> str:
    """Extract the page body between HEADER_MARKER and FOOTER_MARKER.

    On missing markers, returns the whole text stripped — defensive against
    a model that emits a clean body without markers.
    """
    h = text.find(HEADER_MARKER)
    f = text.find(FOOTER_MARKER)
    if h == -1:
        return text.strip()
    body_start = h + len(HEADER_MARKER)
    if f == -1 or f < h:
        return text[body_start:].strip()
    return text[body_start:f].strip()


def _per_page_fingerprint(
    *,
    prompt_version: str,
    model: str,
    slug: str,
    sources: list[str],
    file_hashes: dict[str, str],
) -> str:
    """Per-page fingerprint = sha256(prompt_version|model|slug|sorted(path@hash)).

    Sources are deduped on file path before being paired with their content
    hashes (a single source may carry multiple line ranges for the same file).
    """
    paths_seen: set[str] = set()
    pairs: list[str] = []
    for src in sources:
        path = _source_file_path(src)
        if path in paths_seen:
            continue
        paths_seen.add(path)
        pairs.append(f"{path}@{file_hashes.get(path, '')}")
    h = hashlib.sha256()
    h.update(prompt_version.encode("utf-8"))
    h.update(b"|")
    h.update(model.encode("utf-8"))
    h.update(b"|")
    h.update(slug.encode("utf-8"))
    h.update(b"|")
    h.update(";".join(sorted(pairs)).encode("utf-8"))
    return h.hexdigest()


def _parse_discovery_response(content: str) -> list[Topic]:
    """Parse the LLM's JSON-array response into Topic objects.

    Tolerant of common drift: leading/trailing whitespace, a leading
    ``json`` fence (stripped), or a code-block fence. Strict on shape:
    each element must be an object with string ``title`` and a list of
    string ``sources``. Malformed elements are skipped (logged at DEBUG)
    rather than aborting the whole run.
    """
    text = content.strip()
    # Strip markdown code fence if present.
    if text.startswith("```"):
        # Remove the first ```[lang]\n and the trailing ```
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        _log.warning("how_to_guides: discovery JSON parse failed: %s", exc)
        return []
    if not isinstance(raw, list):
        _log.warning("how_to_guides: discovery output not a JSON array")
        return []
    topics: list[Topic] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        sources = item.get("sources")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(sources, list):
            continue
        clean_sources: list[str] = [s for s in sources if isinstance(s, str) and s]
        if not clean_sources:
            continue
        topics.append(
            Topic(slug=topic_slug(title), title=title, sources=clean_sources)
        )
    return topics


def _readme_excerpt_paths(repo_root: Path) -> list[str]:
    if (repo_root / "README.md").is_file():
        return ["README.md"]
    return []


def _reference_paths(repo_root: Path) -> list[str]:
    ref_dir = repo_root / "docs" / "reference"
    if not ref_dir.is_dir():
        return []
    return sorted(
        f"docs/reference/{p.name}" for p in ref_dir.glob("*.md") if p.is_file()
    )


def _existing_howto_slugs(repo_root: Path, out_dir: Path) -> set[str]:
    target = repo_root / out_dir
    if not target.is_dir():
        return set()
    return {p.stem for p in target.glob("*.md") if p.is_file()}


def _file_hashes(store: object) -> dict[str, str]:
    """Best-effort: pull file_hashes table. Empty dict if column/table missing."""
    try:
        cur = store.conn.execute(  # type: ignore[attr-defined]
            "SELECT file, sha256 FROM file_hashes"
        )
    except Exception:  # pragma: no cover - defensive
        return {}
    return {row[0]: row[1] for row in cur.fetchall()}


def _flag_orphans(
    repo_root: Path, out_dir: Path, intended: set[str], ctx: GenerationContext
) -> None:
    """Append orphan-flag findings to ``ctx.config['how_to_orphans']``."""
    existing = _existing_howto_slugs(repo_root, out_dir)
    orphans = sorted(existing - intended)
    if not orphans:
        return
    bucket = ctx.config.setdefault("how_to_orphans", [])
    assert isinstance(bucket, list)
    for slug in orphans:
        bucket.append(f"orphan: {out_dir.as_posix()}/{slug}.md (source removed)")


@dataclass
class HowToGuidesArtifact:
    id: str = "how_to_guides"
    audience: Audience = "human"
    depends_on: tuple[str, ...] = ("readme", "api_reference")
    out_dir: Path = field(default_factory=lambda: Path("docs/how-to"))
    prompt_version: str = PROMPT_VERSION

    # Per-run state. slug -> (Topic, fingerprint). Populated by plan(),
    # read by generate() and post_write().
    _planned: dict[str, tuple[Topic, str]] = field(default_factory=dict)
    _slugs_to_write: list[str] = field(default_factory=list)
    _slugs_written: int = 0

    @property
    def target(self) -> Path:
        return self.out_dir

    def plan(self, ctx: GenerationContext) -> list[Task]:
        # Reset per-run state.
        self._planned.clear()
        self._slugs_to_write = []
        self._slugs_written = 0

        max_howtos_raw = ctx.config.get("max_howtos", _DEFAULT_MAX_HOWTOS)
        if isinstance(max_howtos_raw, int):
            max_howtos = max_howtos_raw
        elif isinstance(max_howtos_raw, str) and max_howtos_raw.isdigit():
            max_howtos = int(max_howtos_raw)
        else:
            max_howtos = _DEFAULT_MAX_HOWTOS

        readme_paths = _readme_excerpt_paths(ctx.repo_root)
        ref_paths = _reference_paths(ctx.repo_root)
        prompt = build_discovery_prompt(
            repo_root=ctx.repo_root.as_posix(),
            readme_excerpt_paths=readme_paths,
            reference_paths=ref_paths,
            max_topics=max_howtos if max_howtos > 0 else 50,
        )

        backend = ctx.backend
        response = backend.run(  # type: ignore[attr-defined]
            GenerationRequest(
                artifact_id=self.id,
                prompt=prompt,
                repo_root=ctx.repo_root,
            )
        )
        topics = _parse_discovery_response(response.content)

        def _warn(msg: str) -> None:
            # Surface collisions into the run's findings via ctx.config so
            # the orchestrator picks them up on the FIRST task. We can't
            # access ArtifactRun directly from here.
            bucket = ctx.config.setdefault("how_to_warnings", [])
            assert isinstance(bucket, list)
            bucket.append(msg)
            _log.info("how_to_guides: %s", msg)

        topics = dedupe_topics(topics, warn=_warn)

        # Apply cap (0 = unlimited).
        if max_howtos and max_howtos > 0 and len(topics) > max_howtos:
            _log.info(
                "how_to_guides: capping at %d topics (%d discovered; "
                "raise --max-howtos to expand)",
                max_howtos, len(topics),
            )
            topics = topics[:max_howtos]

        model = self._model_id(ctx.backend)
        file_hashes = _file_hashes(ctx.store)
        store = ctx.store

        tasks: list[Task] = []
        for topic in topics:
            fp = _per_page_fingerprint(
                prompt_version=self.prompt_version,
                model=model,
                slug=topic.slug,
                sources=topic.sources,
                file_hashes=file_hashes,
            )
            self._planned[topic.slug] = (topic, fp)
            self._slugs_to_write.append(topic.slug)
            target = ctx.repo_root / self.out_dir / f"{topic.slug}.md"
            prior = self._get_fingerprint(store, topic.slug)
            if prior == fp and target.is_file():
                _log.debug(
                    "how_to_guides: skipping %s (fingerprint match, file present)",
                    topic.slug,
                )
                continue
            tasks.append(
                Task(
                    artifact_id=self.id,
                    target_path=target,
                    payload={"slug": topic.slug},
                )
            )

        # Edge case: zero tasks emitted because every page is a cache-hit.
        # The orphan check still has to fire — handle it from here.
        if not tasks and self._slugs_to_write:
            _flag_orphans(
                ctx.repo_root, self.out_dir, set(self._slugs_to_write), ctx
            )

        return tasks

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        slug = task.payload["slug"]
        if not isinstance(slug, str):
            raise TypeError(
                f"how_to_guides task payload['slug'] must be str, "
                f"got {type(slug).__name__}"
            )
        topic, _ = self._planned[slug]

        # Resolve related slugs (siblings = other planned topics).
        related_slugs = [s for s in self._slugs_to_write if s != slug]
        # Resolve related modules by parsing topic.sources for docs/reference/
        # citations and recovering the dotted name.
        related_modules: list[str] = []
        for src in topic.sources:
            path = _source_file_path(src)
            if path.startswith("docs/reference/") and path.endswith(".md"):
                related_modules.append(path[len("docs/reference/") : -len(".md")])

        prompt = build_page_prompt(
            topic_title=topic.title,
            topic_sources=topic.sources,
            related_modules=related_modules,
        )

        backend = ctx.backend
        response = backend.run(  # type: ignore[attr-defined]
            GenerationRequest(
                artifact_id=self.id,
                prompt=prompt,
                repo_root=ctx.repo_root,
            )
        )

        body = _split_marker_output(response.content)
        page = assemble_page(
            frontmatter=render_frontmatter(title=topic.title, slug=topic.slug),
            body=body,
            see_also=render_see_also(
                related_modules=related_modules,
                related_slugs=related_slugs,
            ),
        )
        return DocPatch(
            artifact_id=self.id,
            target_path=task.target_path,
            new_content=page.encode("utf-8"),
            in_place=False,
            prompt_version=self.prompt_version,
        )

    def verify(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        from docagent.verify.pipeline import default_pipeline

        # Expose all this-run pages so the links gate accepts sibling
        # references during init, before all pages are on disk.
        future_paths = [
            ctx.repo_root / self.out_dir / f"{slug}.md"
            for slug in self._slugs_to_write
        ]
        prior_future = ctx.config.get("_future_paths") if hasattr(ctx, "config") else None
        if hasattr(ctx, "config"):
            ctx.config["_future_paths"] = future_paths
        try:
            return default_pipeline().run(patch, ctx)
        finally:
            if hasattr(ctx, "config"):
                if prior_future is None:
                    ctx.config.pop("_future_paths", None)
                else:
                    ctx.config["_future_paths"] = prior_future

    def post_write(self, patch: DocPatch, ctx: GenerationContext) -> None:
        """Persist the per-page fingerprint; on LAST task, flag orphans."""
        store = ctx.store
        stem = patch.target_path.stem
        if stem in self._planned:
            _, fingerprint = self._planned[stem]
            now = datetime.now(UTC).isoformat()
            store.set_unit_fingerprint(  # type: ignore[attr-defined]
                self.id, stem, fingerprint, now
            )

        self._slugs_written += 1
        # Sentinel: orphan check fires exactly once, on the LAST task.
        # `==` (not `>=`) per VERIFICATION.md W1 — defends against bugs that
        # would otherwise re-fire if post_write were called more than
        # len(_slugs_to_write) times.
        if self._slugs_written == len(self._slugs_to_write):
            _flag_orphans(
                ctx.repo_root, self.out_dir, set(self._slugs_to_write), ctx
            )

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _model_id(backend: object) -> str:
        model = getattr(backend, "model", None)
        return model or "sdk-default"

    def _get_fingerprint(self, store: object, slug: str) -> str | None:
        return store.get_unit_fingerprint(self.id, slug)  # type: ignore[attr-defined]
