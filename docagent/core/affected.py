"""Resolve which artifacts need to refresh given a set of changed source files.

This is the core of ``update`` mode. Two signals drive the decision:

1. **Identifier-mention index** — every artifact's post-write hook records
   which symbol names it mentions in prose. When a source file changes, the
   union of (old symbols ∪ new symbols) is computed and each artifact
   mentioning any of those names is flagged.
2. **Path citations on disk** — artifacts emit ``<!-- ground: path:line -->``
   comments. When a cited file changes, the artifact's citations may have
   moved or become stale, so the artifact is flagged. We scan on-disk
   artifact content for v1 alpha; a dedicated ``path_citations`` table is a
   future optimization.

Artifact files that the user edited directly (i.e. the target path of a
registered artifact) are deliberately excluded from the changed-source set:
we never want to fight a user's hand-edit by regenerating.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docagent.artifacts.registry import Registry
from docagent.citations import cited_paths
from docagent.core.paths import try_repo_rel_posix
from docagent.index.store import Store


def _identifier_names(qn: str) -> set[str]:
    """Both the qualified name and the trailing leaf, so prose that mentions
    either form is caught."""
    names = {qn}
    tail = qn.rsplit(".", 1)[-1]
    if tail and tail != qn:
        names.add(tail)
    return names


def _split_changed_files(
    repo_root: Path,
    changed_files: Iterable[Path],
    artifact_paths: set[str],
) -> tuple[list[str], set[str]]:
    """Split changed files into (source files, artifact-target files)."""
    sources: list[str] = []
    artifact_hits: set[str] = set()
    seen: set[str] = set()
    for p in changed_files:
        rel = try_repo_rel_posix(repo_root, p)
        if rel is None or rel in seen:
            continue
        seen.add(rel)
        if rel in artifact_paths:
            artifact_hits.add(rel)
        else:
            sources.append(rel)
    return sources, artifact_hits


def compute_affected_artifacts(
    repo_root: Path,
    store: Store,
    changed_files: Iterable[Path],
    new_symbols_by_file: dict[str, set[str]],
    registry: Registry,
) -> list[str]:
    """Return artifact ids that need to refresh, in topo order.

    Args:
        repo_root: Repository root used to relativize ``changed_files``.
        store: Index store. Caller must NOT have re-indexed yet: we read the
            old symbols for diffing.
        changed_files: Files reported by ``diff.changed_files_since``.
        new_symbols_by_file: Map of relative-path → set of qualified names
            extracted from the post-change source. Empty set means the file
            still exists but has no symbols (or was deleted). Files not in
            the map are treated as unchanged.
        registry: Used to filter the result to artifacts the registry knows
            about, and to topo-sort the output.
    """
    artifact_paths = store.artifact_paths()  # rel paths → ignore as sources
    artifact_id_by_path = {row[1]: row[0] for row in store.list_artifacts()}

    source_files, _user_edited_artifacts = _split_changed_files(
        repo_root, changed_files, artifact_paths
    )

    affected: set[str] = set()

    # Signal 1: identifier-mention index
    for rel in source_files:
        old_qns = {qn for qn, _ in store.symbols_for_file(rel)}
        new_qns = new_symbols_by_file.get(rel, set())
        all_names: set[str] = set()
        for qn in old_qns | new_qns:
            all_names |= _identifier_names(qn)
        for name in all_names:
            for aid, _path in store.artifacts_mentioning(name):
                affected.add(aid)

    # Signal 2: ground-citation references to the changed source files
    changed_set = set(source_files)
    for art_rel in artifact_paths:
        absolute = repo_root / art_rel
        if not absolute.is_file():
            continue
        try:
            content = absolute.read_bytes()
        except OSError:
            continue
        cited = cited_paths(content)
        if cited & changed_set:
            aid = artifact_id_by_path.get(art_rel)
            if aid is not None:
                affected.add(aid)

    # Filter to artifacts the current registry recognizes.
    known = {a.id for a in registry.all()}
    affected &= known

    if not affected:
        return []

    order = [a.id for a in registry.topo_order(sorted(affected))]
    return order
