"""Path normalization helpers.

Every path that lands in the index database must be a repo-relative POSIX
string. Without a single chokepoint the orchestrator's post-write hook
sometimes stored absolute paths (when ``Path.relative_to`` raised
``ValueError``), the affected-artifact resolver compared those against
POSIX-normalized strings from elsewhere, and incremental update silently
mismatched.

Keep callers small: use :func:`to_repo_rel_posix` whenever you're about to
write a path into SQLite or compare against one read back out.
"""

from __future__ import annotations

from pathlib import Path


def to_repo_rel_posix(repo_root: Path, path: Path) -> str:
    """Return ``path`` as a repo-relative POSIX string.

    Accepts absolute or relative inputs. Raises :class:`ValueError` if the
    path is not under ``repo_root`` — that's a programming error, not a
    runtime condition we should paper over.
    """
    root = repo_root.resolve()
    p = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"path {path!r} is not under repo root {repo_root!r}"
        ) from exc


def try_repo_rel_posix(repo_root: Path, path: Path) -> str | None:
    """Soft variant: return ``None`` instead of raising.

    Useful at boundaries where the input set is best-effort (e.g. a list of
    files coming from ``git diff`` may include paths outside the repo if
    the user ran the command from an odd cwd).
    """
    try:
        return to_repo_rel_posix(repo_root, path)
    except ValueError:
        return None
