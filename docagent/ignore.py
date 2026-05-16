"""`.docagentignore` parser — gitignore-style, defaults baked in."""

from __future__ import annotations

from pathlib import Path

import pathspec

DEFAULT_PATTERNS: tuple[str, ...] = (
    "__pycache__/",
    "*.pyc",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "vendor/",
    "third_party/",
    "node_modules/",
    "build/",
    "dist/",
    ".venv/",
    "venv/",
    "env/",
    ".tox/",
    ".eggs/",
    "*.egg-info/",
    "target/",  # Rust
    "out/",
    ".gradle/",
    ".docagent/",
    ".git/",
    ".github/workflows/",  # often noisy; opt-in via override
)


class IgnoreMatcher:
    def __init__(self, repo_root: Path) -> None:
        patterns: list[str] = list(DEFAULT_PATTERNS)
        ignore_file = repo_root / ".docagentignore"
        if ignore_file.is_file():
            for raw in ignore_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)
        self._spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        self._root = repo_root

    def is_ignored(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self._root)
        except ValueError:
            return False
        return self._spec.match_file(str(rel))
