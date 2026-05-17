"""Repository scanner — walks files, dispatches each to the right adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from docagent.adapters.base import LanguageAdapter
from docagent.adapters.fallback import EXTENSIONS as FALLBACK_EXTENSIONS, FallbackAdapter
from docagent.adapters.python import PythonAdapter
from docagent.adapters.typescript import TypeScriptAdapter
from docagent.ignore import IgnoreMatcher


@dataclass(frozen=True, slots=True)
class ScannedFile:
    path: Path
    adapter: LanguageAdapter
    sha256: str


def _build_adapter_index() -> dict[str, LanguageAdapter]:
    adapters: dict[str, LanguageAdapter] = {}
    py = PythonAdapter()
    for ext in py.file_extensions:
        adapters[ext] = py
    ts_adapter = TypeScriptAdapter()
    for ext in ts_adapter.file_extensions:
        adapters[ext] = ts_adapter
    for lang in FALLBACK_EXTENSIONS:
        adapter = FallbackAdapter(lang)
        for ext in adapter.file_extensions:
            adapters.setdefault(ext, adapter)
    return adapters


class Scanner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.ignore = IgnoreMatcher(repo_root)
        self.by_ext = _build_adapter_index()

    def walk(self) -> Iterator[ScannedFile]:
        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue
            if self.ignore.is_ignored(path):
                continue
            adapter = self.by_ext.get(path.suffix)
            if adapter is None:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            sha = hashlib.sha256(data).hexdigest()
            yield ScannedFile(path=path, adapter=adapter, sha256=sha)
