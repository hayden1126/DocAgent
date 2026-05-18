"""Regeneration benchmark - scoring phase.

For each `results/<name>-<sha>/` directory produced by run.py, run four
LLM-judge passes over (original, regenerated) and write metrics.json +
divergences.jsonl.

This module is a SCAFFOLD. The judge invocations are marked `TODO`. Wire
them to `docagent.backends.litellm_backend.LiteLLMBackend` when ready -
do NOT invent a parallel HTTP client; reuse the project's existing
backend so cost tracking, model-allowlist, and retry behavior carry
over for free.

Prompts live in `prompts/`. Each prompt expects two inputs:
  - {original_doc}
  - {regenerated_doc}
And for `divergence_resolution.md`, also:
  - {source_excerpt}  - the cited span DocAgent grounded its claim in
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PROMPTS = HERE / "prompts"


@dataclass
class Divergence:
    subject: str           # what the two docs are talking about
    original_claim: str
    docagent_claim: str
    docagent_citation: str | None  # ground: path:l-l (None if uncited)
    resolution: str        # "docagent" | "original" | "both_wrong" | "unverifiable"
    reasoning: str


@dataclass
class RepoMetrics:
    name: str
    sha: str
    topic_coverage_jaccard: float | None = None
    factual_divergence_count: int = 0
    divergence_resolution: dict[str, int] = field(default_factory=dict)
    unique_facts_docagent: int = 0
    unique_facts_original: int = 0
    judge_model: str | None = None
    notes: list[str] = field(default_factory=list)


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def call_judge(prompt: str, model: str) -> str:
    """Single judge call.

    TODO: wire to docagent.backends.litellm_backend.LiteLLMBackend so we
    get budget tracking, tested-model allowlist, and the same auth path
    as the main CLI. Do not re-implement HTTP here.

    For now this raises so a partial scaffold cannot accidentally produce
    fake numbers.
    """
    raise NotImplementedError(
        "judge LLM call not wired yet - see TODO in score.py:call_judge"
    )


def score_topic_coverage(original: str, regenerated: str, model: str) -> float:
    prompt = load_prompt("topic_coverage").format(
        original_doc=original, regenerated_doc=regenerated,
    )
    raw = call_judge(prompt, model)
    payload = json.loads(raw)
    return float(payload["jaccard"])


def score_factual_divergence(
    original: str, regenerated: str, model: str,
) -> list[Divergence]:
    prompt = load_prompt("factual_divergence").format(
        original_doc=original, regenerated_doc=regenerated,
    )
    raw = call_judge(prompt, model)
    payload = json.loads(raw)
    return [Divergence(**d) for d in payload["divergences"]]


def resolve_divergence(
    divergence: Divergence, repo_root: Path, model: str,
) -> Divergence:
    """For a single divergence, fetch the cited span (if any) and ask the
    judge which side the source supports."""
    source_excerpt = ""
    if divergence.docagent_citation:
        # citation form: path:start-end
        try:
            path_part, _, span = divergence.docagent_citation.partition(":")
            start_s, _, end_s = span.partition("-")
            start, end = int(start_s), int(end_s)
            lines = (repo_root / path_part).read_text().splitlines()
            source_excerpt = "\n".join(lines[max(0, start - 1):end])
        except (ValueError, OSError, FileNotFoundError):
            source_excerpt = "<citation could not be resolved>"

    prompt = load_prompt("divergence_resolution").format(
        original_claim=divergence.original_claim,
        docagent_claim=divergence.docagent_claim,
        source_excerpt=source_excerpt or "<no citation>",
    )
    raw = call_judge(prompt, model)
    payload = json.loads(raw)
    divergence.resolution = payload["resolution"]
    divergence.reasoning = payload["reasoning"]
    return divergence


def score_unique_facts(
    original: str, regenerated: str, model: str,
) -> tuple[int, int]:
    prompt = load_prompt("unique_facts").format(
        original_doc=original, regenerated_doc=regenerated,
    )
    raw = call_judge(prompt, model)
    payload = json.loads(raw)
    return payload["unique_to_docagent"], payload["unique_to_original"]


def score_one(result_dir: Path, judge_model: str, repo_root: Path) -> RepoMetrics:
    run_meta = json.loads((result_dir / "run.json").read_text())
    metrics = RepoMetrics(
        name=run_meta["name"], sha=run_meta["sha"], judge_model=judge_model,
    )

    # README is the primary comparison surface; expand to other artifacts
    # in a follow-up. Skip silently if either side is missing.
    orig_readme = result_dir / "original" / "README.md"
    regen_readme = result_dir / "regenerated" / "README.md"
    if not (orig_readme.exists() and regen_readme.exists()):
        metrics.notes.append("README missing on one side; skipped scoring")
        return metrics

    original = orig_readme.read_text()
    regenerated = regen_readme.read_text()

    metrics.topic_coverage_jaccard = score_topic_coverage(
        original, regenerated, judge_model
    )
    divergences = score_factual_divergence(original, regenerated, judge_model)
    metrics.factual_divergence_count = len(divergences)

    resolved: list[Divergence] = []
    for d in divergences:
        resolved.append(resolve_divergence(d, repo_root, judge_model))
    bucket: dict[str, int] = {}
    for d in resolved:
        bucket[d.resolution] = bucket.get(d.resolution, 0) + 1
    metrics.divergence_resolution = bucket

    metrics.unique_facts_docagent, metrics.unique_facts_original = score_unique_facts(
        original, regenerated, judge_model,
    )

    (result_dir / "metrics.json").write_text(json.dumps(asdict(metrics), indent=2))
    with (result_dir / "divergences.jsonl").open("w") as fh:
        for d in resolved:
            fh.write(json.dumps(asdict(d)) + "\n")
    return metrics


def aggregate() -> None:
    rows: list[dict] = []
    for metrics_path in RESULTS.glob("*/metrics.json"):
        rows.append(json.loads(metrics_path.read_text()))
    if not rows:
        print("No metrics.json files found; run score.py without --aggregate first.")
        return
    out = RESULTS / "aggregate.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"Wrote aggregate: {out} ({len(rows)} repos)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-model", default="anthropic/claude-opus-4-7",
                        help="LiteLLM model string for the judge.")
    parser.add_argument("--only", action="append", default=[],
                        help="Score only these repo names (repeatable).")
    parser.add_argument("--aggregate", action="store_true",
                        help="Roll up existing metrics.json files only; do not re-score.")
    args = parser.parse_args()

    if args.aggregate:
        aggregate()
        return 0

    clones_dir = HERE / "clones"
    targets = sorted(RESULTS.glob("*-*"))
    if args.only:
        targets = [t for t in targets if any(t.name.startswith(n + "-") for n in args.only)]

    for result_dir in targets:
        if not result_dir.is_dir():
            continue
        name = result_dir.name.rsplit("-", 1)[0]
        repo_root = clones_dir / name
        if not repo_root.exists():
            print(f"[{name}] WARNING: clone missing at {repo_root}; "
                  f"citation resolution will fail. Re-run run.py first.")
        score_one(result_dir, args.judge_model, repo_root)

    aggregate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
