"""Deterministic-first verifier pipeline.

Order matters — cheap deterministic gates short-circuit before the expensive
LLM judge. Each gate returns a (passed, findings) tuple; a failing gate may
optionally hard-stop the pipeline (controlled per-gate via the `blocking`
flag).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext, VerifyResult


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    run: Callable[[DocPatch, GenerationContext], tuple[bool, Sequence[str]]]
    blocking: bool = True


@dataclass
class VerifierPipeline:
    gates: list[Gate] = field(default_factory=list)

    def add(self, gate: Gate) -> "VerifierPipeline":
        self.gates.append(gate)
        return self

    def run(self, patch: DocPatch, ctx: GenerationContext) -> VerifyResult:
        findings: list[str] = []
        ok = True
        for gate in self.gates:
            passed, msgs = gate.run(patch, ctx)
            for m in msgs:
                findings.append(f"[{gate.name}] {m}")
            if not passed:
                ok = False
                if gate.blocking:
                    break
        return VerifyResult(ok=ok, findings=tuple(findings))


def default_pipeline() -> VerifierPipeline:
    from docagent.verify import citations, docs_site, judge, links, markdownlint, secrets

    return (
        VerifierPipeline()
        .add(Gate("markdownlint", markdownlint.check))
        .add(Gate("links", links.check))
        .add(Gate("citations", citations.check))
        .add(Gate("docs_site", docs_site.check, blocking=False))
        .add(Gate("secrets", secrets.check))
        .add(Gate("judge", judge.check, blocking=False))
    )
