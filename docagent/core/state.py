"""`.docagent/state.json` — small run header. The heavy state lives in SQLite."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RunState:
    doc_version: str | None = None  # last successful git commit SHA
    last_run: str | None = None
    artifact_versions: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, repo_root: Path) -> "RunState":
        path = repo_root / ".docagent" / "state.json"
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            doc_version=raw.get("doc_version"),
            last_run=raw.get("last_run"),
            artifact_versions=dict(raw.get("artifact_versions", {})),
        )

    def save(self, repo_root: Path) -> None:
        path = repo_root / ".docagent" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8")
