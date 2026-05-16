"""Git diff helpers — computes the file set changed since `doc_version`."""

from __future__ import annotations

from pathlib import Path

try:
    import git  # GitPython
except ImportError:  # pragma: no cover
    git = None  # type: ignore[assignment]


def changed_files_since(repo_root: Path, doc_version: str | None) -> list[Path]:
    if git is None:
        raise RuntimeError("GitPython is required for diff-based update mode")
    try:
        repo = git.Repo(repo_root)
    except git.InvalidGitRepositoryError:
        return []

    if doc_version is None:
        return [Path(item.path) for item in repo.tree().traverse() if Path(item.path).is_file()]

    try:
        diff = repo.commit(doc_version).diff(repo.head.commit)
    except (git.BadName, ValueError):
        return []

    changed: list[Path] = []
    for d in diff:
        if d.a_path:
            changed.append(repo_root / d.a_path)
        if d.b_path and d.b_path != d.a_path:
            changed.append(repo_root / d.b_path)
    return list(dict.fromkeys(changed))


def current_head(repo_root: Path) -> str | None:
    if git is None:
        return None
    try:
        repo = git.Repo(repo_root)
        return repo.head.commit.hexsha
    except Exception:
        return None
