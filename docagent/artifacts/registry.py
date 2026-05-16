"""Doc-artifact protocol and DAG-aware registry.

Artifacts declare `depends_on` edges so that dependents (e.g. AGENTS.md citing
the README) are generated after their dependencies. The registry topologically
sorts artifacts and detects cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

Audience = Literal["human", "agent", "both"]


@dataclass(frozen=True, slots=True)
class Task:
    artifact_id: str
    target_path: Path
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocPatch:
    artifact_id: str
    target_path: Path
    new_content: bytes
    in_place: bool = False
    citations: tuple[tuple[Path, int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    findings: tuple[str, ...] = ()


@runtime_checkable
class DocArtifact(Protocol):
    id: str
    audience: Audience
    depends_on: tuple[str, ...]

    def plan(self, ctx: "GenerationContext") -> list[Task]: ...
    def generate(self, task: Task, ctx: "GenerationContext") -> DocPatch: ...
    def verify(self, patch: DocPatch, ctx: "GenerationContext") -> VerifyResult: ...


@dataclass
class GenerationContext:
    repo_root: Path
    store: object  # docagent.index.store.Store; loose-typed to avoid circular import
    backend: object  # LLMBackend protocol; defined alongside backends/
    changed_files: tuple[Path, ...] = ()
    config: dict[str, object] = field(default_factory=dict)


class Registry:
    def __init__(self) -> None:
        self._artifacts: dict[str, DocArtifact] = {}

    def register(self, artifact: DocArtifact) -> None:
        if artifact.id in self._artifacts:
            raise ValueError(f"Artifact id already registered: {artifact.id}")
        self._artifacts[artifact.id] = artifact

    def get(self, artifact_id: str) -> DocArtifact:
        return self._artifacts[artifact_id]

    def all(self) -> list[DocArtifact]:
        return list(self._artifacts.values())

    def topo_order(self, subset: list[str] | None = None) -> list[DocArtifact]:
        """Kahn's algorithm. Raises on cycle or unknown dependency."""
        ids = set(subset) if subset is not None else set(self._artifacts)
        for aid in ids:
            if aid not in self._artifacts:
                raise KeyError(f"Unknown artifact: {aid}")

        in_degree: dict[str, int] = {aid: 0 for aid in ids}
        edges: dict[str, list[str]] = {aid: [] for aid in ids}
        for aid in ids:
            for dep in self._artifacts[aid].depends_on:
                if dep not in ids:
                    raise KeyError(f"Artifact {aid!r} depends on unknown {dep!r}")
                edges[dep].append(aid)
                in_degree[aid] += 1

        ready = [aid for aid, deg in in_degree.items() if deg == 0]
        order: list[str] = []
        while ready:
            ready.sort()  # stable, deterministic
            current = ready.pop(0)
            order.append(current)
            for nxt in edges[current]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    ready.append(nxt)

        if len(order) != len(ids):
            cycle = [aid for aid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Cycle detected among artifacts: {cycle}")

        return [self._artifacts[aid] for aid in order]
