"""``api_reference`` — curated per-module landing pages.

This is the first multi-file artifact in DocAgent. Each Python module the
scanner indexed produces one page at ``docs/reference/<dotted>.md``. The
artifact's plan/generate cycle is:

1. ``plan`` queries the symbol index, discovers modules, computes a
   per-module fingerprint, and emits one :class:`Task` per module whose
   fingerprint differs from the last run (or whose target file is missing).
2. ``generate`` formats the prompt, calls the backend, splits the response
   on ``<<<OPENER>>>`` / ``<<<WORKFLOWS>>>`` markers, splices the LLM-written
   parts into the deterministic template, and returns a :class:`DocPatch`.
3. ``verify`` runs the default pipeline against the page.
4. ``post_write`` persists the fingerprint after the orchestrator's
   apply_patch succeeds — so a verifier failure does not poison the cache.

What we deliberately don't do here:
- No per-symbol pages (mkdocstrings/pdoc do that well).
- No JSDoc/TS support yet; Python only in v1.
- No cross-file symbol resolution beyond leaf-name matching.
- No autodoc-style member dump; the public-surface table is the substitute.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from docagent._logging import get_logger
from docagent.adapters.typescript import ExportEntry
from docagent.artifacts._api_reference_render import assemble_page
from docagent.artifacts._module_discovery import (
    DiscoveredModule,
    discover_python_modules,
    parent_module,
    sibling_modules,
)
from docagent.artifacts._ts_module_discovery import discover_ts_modules
from docagent.artifacts.registry import (
    Audience,
    DocPatch,
    GenerationContext,
    Task,
    VerifyResult,
)
from docagent.backends.base import GenerationRequest
from docagent.prompts.api_reference import (
    OPENER_MARKER,
    PROMPT_VERSION,
    WORKFLOWS_MARKER,
    format_prompt,
)

_log = get_logger("artifacts.api_reference")

_DEFAULT_MAX_MODULES = 25


def _fingerprint(
    module: DiscoveredModule,
    file_hash: str | None,
    prompt_version: str,
    model: str,
) -> str:
    h = hashlib.sha256()
    h.update(prompt_version.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update((file_hash or "").encode("utf-8"))
    h.update(b"\x00")
    for sym in module.public_symbols:
        h.update(sym.qualified_name.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def _symbol_table_block(module: DiscoveredModule) -> str:
    if not module.public_symbols:
        return "(none — all symbols are private)"
    lines = []
    for sym in module.public_symbols:
        sig = sym.signature.split("\n", 1)[0]
        lines.append(f"- `{sym.qualified_name}`  ({sym.kind}) — {sig}")
    return "\n".join(lines)


def _siblings_block(siblings: list[str], parent: str | None) -> str:
    if not siblings and parent is None:
        return "(none — this is a top-level module with no siblings)"
    parts: list[str] = []
    if parent:
        parts.append(f"- parent: `{parent}`")
    for s in siblings:
        parts.append(f"- sibling: `{s}`")
    return "\n".join(parts)


def _split_marker_output(text: str) -> tuple[str, str]:
    """Split LLM output at the OPENER and WORKFLOWS markers.

    Returns ``(opener_md, workflows_md)``; either may be empty. We accept
    minor variations: any whitespace around the markers, any text before
    the first OPENER marker (treated as preamble and discarded).
    """
    opener_idx = text.find(OPENER_MARKER)
    workflows_idx = text.find(WORKFLOWS_MARKER)
    if opener_idx == -1:
        return "", ""
    opener_start = opener_idx + len(OPENER_MARKER)
    if workflows_idx == -1 or workflows_idx < opener_idx:
        return text[opener_start:].strip(), ""
    opener_text = text[opener_start:workflows_idx].strip()
    workflows_text = text[workflows_idx + len(WORKFLOWS_MARKER) :].strip()
    return opener_text, workflows_text


@dataclass
class ApiReferenceArtifact:
    id: str = "api_reference"
    audience: Audience = "both"
    depends_on: tuple[str, ...] = ()
    # Where pages land. Relative to repo_root.
    out_dir: Path = field(default_factory=lambda: Path("docs/reference"))
    prompt_version: str = PROMPT_VERSION

    # Per-run state: dotted_name -> (DiscoveredModule, fingerprint, language).
    # Populated by plan(); read by generate() and post_write().
    _planned: dict[str, tuple[DiscoveredModule, str, str]] = field(default_factory=dict)
    _all_modules: list[str] = field(default_factory=list)
    _export_edges: dict[str, list[ExportEntry]] = field(default_factory=dict)
    _existing_docs: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def target(self) -> Path:
        # The directory the artifact owns. Used by the verify CLI's
        # discovery fallback — the index.is_file() check fails on a dir, so
        # discovery skips us correctly.
        return self.out_dir

    def plan(self, ctx: GenerationContext) -> list[Task]:
        store = ctx.store  # type: ignore[assignment]

        # Per-language discovery → merge → deterministic sort by dotted_name
        # → combined cap. The cap is intentionally NOT per-language: a mixed
        # Python+TS repo with --max-modules=5 should see five modules total,
        # not five per language, and ordering must be stable (RESEARCH.md
        # Pitfall 5).
        py_rows = self._fetch_symbol_rows_for(store, "python")
        ts_rows = self._fetch_symbol_rows_for(store, "typescript")
        ts_file_hashes = self._fetch_file_hashes_for(store, "typescript")
        py_file_hashes = self._fetch_file_hashes_for(store, "python")

        py_modules = discover_python_modules(py_rows)
        ts_modules, ts_export_edges = discover_ts_modules(
            ctx.repo_root, ts_rows, ts_file_hashes
        )

        merged: list[tuple[DiscoveredModule, str]] = [
            *((m, "python") for m in py_modules),
            *((m, "typescript") for m in ts_modules),
        ]
        merged.sort(key=lambda pair: pair[0].dotted_name)

        max_modules = int(ctx.config.get("max_modules", _DEFAULT_MAX_MODULES))
        if max_modules and max_modules > 0 and len(merged) > max_modules:
            _log.info(
                "api_reference: capping at %d modules (%d discovered; "
                "raise --max-modules to expand)",
                max_modules, len(merged),
            )
            merged = merged[:max_modules]

        self._all_modules = [m.dotted_name for m, _ in merged]
        self._planned.clear()
        self._export_edges.clear()
        self._existing_docs.clear()

        model = self._model_id(ctx.backend)

        tasks: list[Task] = []
        for mod, lang in merged:
            file_hash = (
                ts_file_hashes.get(mod.file_rel)
                if lang == "typescript"
                else py_file_hashes.get(mod.file_rel)
            )
            fp = _fingerprint(mod, file_hash, self.prompt_version, model)
            target = ctx.repo_root / self.out_dir / f"{mod.dotted_name}.md"
            prior = self._get_fingerprint(store, mod.dotted_name)
            if prior == fp and target.is_file():
                _log.debug(
                    "api_reference: skipping %s (fingerprint match, file present)",
                    mod.dotted_name,
                )
                continue
            self._planned[mod.dotted_name] = (mod, fp, lang)
            if lang == "typescript":
                self._export_edges[mod.dotted_name] = list(
                    ts_export_edges.get(mod.dotted_name, [])
                )
                self._existing_docs[mod.dotted_name] = {
                    sym.qualified_name: sym.existing_doc or ""
                    for sym in mod.public_symbols
                    if sym.existing_doc
                }
            tasks.append(
                Task(
                    artifact_id=self.id,
                    target_path=target,
                    payload={"dotted_name": mod.dotted_name, "language": lang},
                )
            )
        return tasks

    def generate(self, task: Task, ctx: GenerationContext) -> DocPatch:
        dotted_name = task.payload["dotted_name"]
        if not isinstance(dotted_name, str):
            raise TypeError(
                f"api_reference task payload['dotted_name'] must be str, "
                f"got {type(dotted_name).__name__}"
            )
        module, _, language = self._planned[dotted_name]

        siblings = sibling_modules(dotted_name, self._all_modules)
        # Only link to a parent module that's also being generated. Many
        # ``__init__.py`` files carry only ``__version__`` and similar private
        # symbols, so their dotted name is filtered out of ``_all_modules``
        # by the discovery rules. Linking to a page that doesn't exist would
        # fail the ``links`` gate.
        parent_candidate = parent_module(dotted_name)
        parent = parent_candidate if parent_candidate in self._all_modules else None

        prompt = format_prompt(
            dotted_name=dotted_name,
            file_rel=module.file_rel,
            symbol_table=_symbol_table_block(module),
            siblings_block=_siblings_block(siblings, parent),
            language=language,
        )

        backend = ctx.backend  # type: ignore[assignment]
        response = backend.run(
            GenerationRequest(
                artifact_id=self.id,
                prompt=prompt,
                repo_root=ctx.repo_root,
            )
        )

        opener_md, workflows_md = _split_marker_output(response.content)
        page = assemble_page(
            dotted_name=dotted_name,
            symbols=module.public_symbols,
            siblings=siblings,
            parent=parent,
            opener_md=opener_md,
            workflows_md=workflows_md,
            export_edges=self._export_edges.get(dotted_name),
            existing_docs=self._existing_docs.get(dotted_name),
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

        # Expose the full set of pages this run will produce so the links gate
        # accepts intra-artifact sibling references during init, before all
        # pages are on disk.
        future_paths = [
            ctx.repo_root / self.out_dir / f"{dotted}.md"
            for dotted in self._planned
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
        """Persist the per-module fingerprint after a successful write.

        Called by the orchestrator after ``apply_patch`` succeeds and the
        post-write mention-index hook has run. A fingerprint hit on the
        next ``init`` short-circuits the LLM call entirely.
        """
        store = ctx.store  # type: ignore[assignment]
        # Reverse-lookup the dotted name from the target path. This relies
        # on the invariant: ``plan`` emits exactly one file per dotted name,
        # named ``<dotted>.md``. ``Path.stem`` strips only the LAST suffix,
        # so ``pkg.sub.mod.md`` correctly yields ``pkg.sub.mod``. If a
        # future change writes additional suffixed pages (e.g.
        # ``pkg.mod.types.md``), this reverse-lookup must move to a
        # mapping that ``plan`` populates explicitly.
        stem = patch.target_path.stem
        if stem not in self._planned:
            return
        _, fingerprint, _ = self._planned[stem]
        now = datetime.now(timezone.utc).isoformat()
        store.set_unit_fingerprint(  # type: ignore[attr-defined]
            self.id, stem, fingerprint, now
        )

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _fetch_symbol_rows_for(store: object, language_id: str) -> list[tuple]:
        cur = store.conn.execute(  # type: ignore[attr-defined]
            "SELECT qualified_name, kind, file, line_start, line_end, signature, "
            "existing_doc FROM symbols WHERE language_id = ?",
            (language_id,),
        )
        return list(cur.fetchall())

    @staticmethod
    def _fetch_file_hashes_for(store: object, language_id: str) -> dict[str, str]:
        cur = store.conn.execute(  # type: ignore[attr-defined]
            "SELECT file, sha256 FROM file_hashes WHERE language_id = ?",
            (language_id,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    # Back-compat wrappers — some tests and callers reference the old names
    # without a language argument; preserve them as Python shims.
    @classmethod
    def _fetch_symbol_rows(cls, store: object) -> list[tuple]:
        return cls._fetch_symbol_rows_for(store, "python")

    @classmethod
    def _fetch_file_hashes(cls, store: object) -> dict[str, str]:
        return cls._fetch_file_hashes_for(store, "python")

    @staticmethod
    def _model_id(backend: object) -> str:
        # Treat None as a stable "sdk-default" so the SDK silently bumping
        # Sonnet doesn't invalidate every fingerprint.
        model = getattr(backend, "model", None)
        return model or "sdk-default"

    def _get_fingerprint(self, store: object, dotted_name: str) -> str | None:
        return store.get_unit_fingerprint(self.id, dotted_name)  # type: ignore[attr-defined]
