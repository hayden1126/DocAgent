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
        """Run gates in order, returning aggregate ok + findings.

        ``ok`` is False only when a *blocking* gate fails. Non-blocking gate
        failures contribute findings but never flip the result — that's what
        ``blocking=False`` means. The CLI's ``--strict`` flag is what
        tightens "fail on any finding" back on, surfaced as a separate
        decision at the call site (see ``docagent.cli.verify``).
        """
        findings: list[str] = []
        ok = True
        for gate in self.gates:
            passed, msgs = gate.run(patch, ctx)
            for m in msgs:
                findings.append(f"[{gate.name}] {m}")
            if not passed and gate.blocking:
                ok = False
                break
        return VerifyResult(ok=ok, findings=tuple(findings))


def default_pipeline() -> VerifierPipeline:
    """The canonical v1 verifier order.

    Stylistic gates (``markdownlint``, ``docs_site``) are non-blocking so a
    single MD013 line-length nit can't nuke a run before citations check.
    Truth-checking gates (``citations``, ``links``, ``secrets``) are blocking.
    The LLM judge is last and non-blocking — it's a tiebreaker, not a gate.
    """
    from docagent.verify import citations, docs_site, judge, links, markdownlint, secrets

    return (
        VerifierPipeline()
        .add(Gate("markdownlint", markdownlint.check, blocking=False))
        .add(Gate("links", links.check, blocking=True))
        .add(Gate("citations", citations.check, blocking=True))
        .add(Gate("docs_site", docs_site.check, blocking=False))
        .add(Gate("secrets", secrets.check, blocking=True))
        .add(Gate("judge", judge.check, blocking=False))
    )
