"""Regeneration benchmark - scoring phase.

For each `results/<name>-<sha>/` directory produced by run.py, run the
LLM-judge passes over (original, regenerated) and write metrics.json +
claims.jsonl + divergences.jsonl.

Pipeline (per repo):
  1. Atomic FActScore decomposition (prompts/factual_divergence.md)
     produces per-claim supported/unsupported/contradicted verdicts.
  2. Topic-coverage Jaccard (prompts/topic_coverage.md).
  3. Divergence resolution against cited source spans
     (prompts/divergence_resolution.md).
  4. Three-axis rubric: completeness, helpfulness, truthfulness
     (prompts/rubric_*.md). Truthfulness consumes the FActScore JSON
     from step 1 to avoid re-paying for the same claim verification.
  5. Length normalization: claims_per_1000_tokens computed from the
     FActScore claim count and a ~4 chars/token approximation.
  6. Optionally: cross-family judge panel. Pass --judge-model multiple
     times; each model scores every metric and inter-judge
     disagreement is logged.

Judge calls go through `docagent.backends.litellm_backend.LiteLLMBackend`
so cost tracking, retries, and the model allowlist match the main CLI.
Set the appropriate env var for whichever model(s) you pass:
  ANTHROPIC_API_KEY   for anthropic/*
  GEMINI_API_KEY      for gemini/*
  OPENAI_API_KEY      for openai/*
  OPENROUTER_API_KEY  for openrouter/*
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PROMPTS = HERE / "prompts"

# Approximate chars-per-token for length normalization. Cheap and good
# enough for relative comparison; do not use for billing math.
_CHARS_PER_TOKEN = 4


@dataclass
class Claim:
    id: str
    text: str
    doc_excerpt: str
    doc_citation: str | None
    verdict: str  # "supported" | "unsupported" | "contradicted"
    evidence_path: str | None
    reasoning: str


@dataclass
class Divergence:
    subject: str
    original_claim: str
    docagent_claim: str
    docagent_citation: str | None
    resolution: str   # "docagent" | "original" | "both_wrong" | "unverifiable"
    reasoning: str


@dataclass
class AxisScore:
    score: int                  # 0..5
    rationale: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class JudgePassMetrics:
    judge_model: str
    factscore: float | None = None
    supported_count: int = 0
    unsupported_count: int = 0
    contradicted_count: int = 0
    total_claims: int = 0
    claims_per_1000_tokens: float | None = None
    topic_coverage_jaccard: float | None = None
    divergence_resolution: dict[str, int] = field(default_factory=dict)
    completeness: AxisScore | None = None
    helpfulness: AxisScore | None = None
    truthfulness: AxisScore | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class RepoMetrics:
    name: str
    sha: str
    passes: list[JudgePassMetrics] = field(default_factory=list)
    inter_judge_axis_disagreement: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ---- Judge facade (LiteLLM-backed) -------------------------------------

_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _env_key_for(model: str) -> str | None:
    provider = model.split("/", 1)[0]
    return _ENV_KEYS.get(provider)


def _ensure_judge_credentials(model: str) -> None:
    env_var = _env_key_for(model)
    if env_var is None:
        return  # unknown provider; LiteLLM will surface its own error
    if not os.environ.get(env_var):
        raise SystemExit(
            f"Judge model {model!r} needs {env_var} in the environment. "
            f"Export it before running score.py. (See KNOWN-GAPS.md §2 for the "
            f"cross-family judge motivation.)"
        )


def call_judge(prompt: str, model: str) -> str:
    """Single judge call via `litellm.completion()`.

    The benchmark judge is a one-shot prompt→text call — no repo tools,
    no agent loop — so we use `litellm.completion()` directly rather than
    `LiteLLMBackend.run()` (which expects a `GenerationRequest` with
    repo context). The model-string convention (`provider/model`) and
    env-var keys match the main CLI's LiteLLM backend, so cross-family
    judges work out of the box once `pip install docagent[multi]` is
    done.

    Returns the raw text content; the caller parses JSON.
    """
    _ensure_judge_credentials(model)
    # Import lazily so `--aggregate` and dry-imports work without the
    # multi extra installed.
    try:
        import litellm
    except ImportError as exc:
        raise SystemExit(
            "The `litellm` package is not installed. "
            "Install it with `pip install docagent[multi]`."
        ) from exc

    litellm.drop_params = True
    litellm.suppress_debug_info = True
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["choices"][0]["message"]["content"]


# ---- Prompt loading ----------------------------------------------------

def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def _parse_json_response(raw: str) -> Any:
    """LLMs sometimes wrap JSON in ``` fences despite instructions.

    Strip a single outer ```json ... ``` fence if present, then parse.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```") and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
    return json.loads(text)


# ---- Length normalization ---------------------------------------------

def _approx_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _claims_per_1000_tokens(claim_count: int, doc_text: str) -> float:
    return round(claim_count / (_approx_tokens(doc_text) / 1000.0), 3)


# ---- Per-metric scorers ------------------------------------------------

def score_factscore(regenerated: str, model: str) -> tuple[list[Claim], dict[str, Any]]:
    prompt = load_prompt("factual_divergence").format(regenerated_doc=regenerated)
    raw = call_judge(prompt, model)
    payload = _parse_json_response(raw)
    claims = [Claim(**c) for c in payload.get("claims", [])]
    summary = {
        "supported_count": payload.get("supported_count", 0),
        "unsupported_count": payload.get("unsupported_count", 0),
        "contradicted_count": payload.get("contradicted_count", 0),
        "total_claims": payload.get("total_claims", len(claims)),
        "factscore": float(payload.get("factscore", 0.0)),
    }
    return claims, summary


def score_topic_coverage(original: str, regenerated: str, model: str) -> float:
    prompt = load_prompt("topic_coverage").format(
        original_doc=original, regenerated_doc=regenerated,
    )
    raw = call_judge(prompt, model)
    payload = _parse_json_response(raw)
    return float(payload["jaccard"])


def resolve_divergence(
    divergence: Divergence, repo_root: Path, model: str,
) -> Divergence:
    """Fetch the cited span (if any) and ask the judge which side the source supports."""
    source_excerpt = ""
    if divergence.docagent_citation:
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
    payload = _parse_json_response(raw)
    divergence.resolution = payload["resolution"]
    divergence.reasoning = payload["reasoning"]
    return divergence


def _score_axis(prompt_name: str, regenerated: str, model: str,
                **extra: str) -> AxisScore:
    prompt = load_prompt(prompt_name).format(
        regenerated_doc=regenerated, **extra,
    )
    raw = call_judge(prompt, model)
    payload = _parse_json_response(raw)
    return AxisScore(
        score=int(payload["score"]),
        rationale=payload.get("rationale", ""),
        details={k: v for k, v in payload.items() if k not in ("score", "rationale")},
    )


def score_completeness(regenerated: str, model: str) -> AxisScore:
    return _score_axis("rubric_completeness", regenerated, model)


def score_helpfulness(regenerated: str, model: str) -> AxisScore:
    return _score_axis("rubric_helpfulness", regenerated, model)


def score_truthfulness(regenerated: str, model: str,
                       factscore_json: str) -> AxisScore:
    return _score_axis(
        "rubric_truthfulness", regenerated, model, factscore_json=factscore_json,
    )


# ---- Baseline modes (KNOWN-GAPS.md §5) ---------------------------------

def _read_doc(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def _baseline_inputs(
    result_dir: Path, mode: str,
) -> tuple[str, str, str] | None:
    """Return (original, regenerated, note) for a baseline mode.

    `identity`: score the original doc against itself (judge noise floor).
    `empty`: score an empty string vs the original (zero-coverage floor).
    """
    orig = _read_doc(result_dir / "original" / "README.md")
    if orig is None:
        return None
    if mode == "identity":
        return orig, orig, "baseline=identity (judge noise floor)"
    if mode == "empty":
        return orig, "", "baseline=empty (zero-coverage floor)"
    raise ValueError(f"unknown baseline mode: {mode!r}")


# ---- Per-repo orchestration -------------------------------------------

def score_one(
    result_dir: Path,
    judge_model: str,
    repo_root: Path,
    baseline: str | None = None,
) -> JudgePassMetrics:
    metrics = JudgePassMetrics(judge_model=judge_model)

    if baseline is not None:
        triple = _baseline_inputs(result_dir, baseline)
        if triple is None:
            metrics.notes.append(
                f"baseline {baseline!r}: README missing; skipped",
            )
            return metrics
        original, regenerated, note = triple
        metrics.notes.append(note)
    else:
        orig_readme = result_dir / "original" / "README.md"
        regen_readme = result_dir / "regenerated" / "README.md"
        if not (orig_readme.exists() and regen_readme.exists()):
            metrics.notes.append("README missing on one side; skipped scoring")
            return metrics
        original = orig_readme.read_text()
        regenerated = regen_readme.read_text()

    # 1. FActScore atomic decomposition
    claims, fs = score_factscore(regenerated, judge_model)
    metrics.factscore = fs["factscore"]
    metrics.supported_count = fs["supported_count"]
    metrics.unsupported_count = fs["unsupported_count"]
    metrics.contradicted_count = fs["contradicted_count"]
    metrics.total_claims = fs["total_claims"]
    metrics.claims_per_1000_tokens = _claims_per_1000_tokens(
        metrics.total_claims, regenerated,
    )

    # 2. Topic coverage
    metrics.topic_coverage_jaccard = score_topic_coverage(
        original, regenerated, judge_model,
    )

    # 3. Three-axis rubric
    metrics.completeness = score_completeness(regenerated, judge_model)
    metrics.helpfulness = score_helpfulness(regenerated, judge_model)
    metrics.truthfulness = score_truthfulness(
        regenerated, judge_model, json.dumps(fs),
    )

    # 4. Divergence resolution — only meaningful for the non-baseline pass.
    # Identity-vs-identity has no divergences; empty-vs-original has only
    # missing-content asymmetry, not factual disagreement.
    if baseline is None and claims:
        bucket: dict[str, int] = {}
        for claim in claims:
            if claim.verdict != "contradicted":
                continue
            div = Divergence(
                subject=claim.text[:80],
                original_claim="(see original doc)",
                docagent_claim=claim.doc_excerpt,
                docagent_citation=claim.doc_citation,
                resolution="unresolved",
                reasoning="",
            )
            resolved = resolve_divergence(div, repo_root, judge_model)
            bucket[resolved.resolution] = bucket.get(resolved.resolution, 0) + 1
        metrics.divergence_resolution = bucket

    # Write per-pass artifacts
    suffix = f".{baseline}" if baseline else f".{_safe(judge_model)}"
    (result_dir / f"claims{suffix}.jsonl").write_text(
        "".join(json.dumps(asdict(c)) + "\n" for c in claims),
    )

    return metrics


def _safe(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", model)


# ---- Aggregation across passes ----------------------------------------

def _disagreement_buckets(passes: list[JudgePassMetrics]) -> dict[str, int]:
    """For each axis, return the max gap across the judge panel."""
    if len(passes) < 2:
        return {}
    out: dict[str, int] = {}
    for axis in ("completeness", "helpfulness", "truthfulness"):
        scores = [getattr(p, axis).score for p in passes if getattr(p, axis)]
        if len(scores) < 2:
            continue
        out[axis] = max(scores) - min(scores)
    return out


def aggregate() -> None:
    rows: list[dict[str, Any]] = []
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
    parser.add_argument(
        "--judge-model", action="append", default=[],
        help="LiteLLM model string for the judge. Repeat for a cross-family "
             "panel (e.g. --judge-model anthropic/claude-opus-4-7 "
             "--judge-model gemini/gemini-2.0-pro). See KNOWN-GAPS.md §2.",
    )
    parser.add_argument(
        "--only", action="append", default=[],
        help="Score only these repo names (repeatable).",
    )
    parser.add_argument(
        "--baseline", choices=("identity", "empty"), default=None,
        help="Run a calibration pass instead of regen scoring. "
             "`identity` scores original vs. original (judge noise floor). "
             "`empty` scores '' vs. original (zero-coverage floor). "
             "Per KNOWN-GAPS.md §5, run both before publishing numbers.",
    )
    parser.add_argument(
        "--aggregate", action="store_true",
        help="Roll up existing metrics.json files only; do not re-score.",
    )
    args = parser.parse_args()

    if args.aggregate:
        aggregate()
        return 0

    if not args.judge_model:
        args.judge_model = ["anthropic/claude-opus-4-7"]

    clones_dir = HERE / "clones"
    targets = sorted(RESULTS.glob("*-*"))
    if args.only:
        targets = [
            t for t in targets
            if any(t.name.startswith(n + "-") for n in args.only)
        ]

    for result_dir in targets:
        if not result_dir.is_dir():
            continue
        name = result_dir.name.rsplit("-", 1)[0]
        repo_root = clones_dir / name
        if not repo_root.exists():
            print(
                f"[{name}] WARNING: clone missing at {repo_root}; "
                f"citation resolution may fail. Re-run run.py first.",
            )

        run_meta = json.loads((result_dir / "run.json").read_text())
        repo_metrics = RepoMetrics(name=run_meta["name"], sha=run_meta["sha"])
        if args.baseline:
            repo_metrics.notes.append(
                f"baseline={args.baseline}; not a regen comparison",
            )

        for model in args.judge_model:
            repo_metrics.passes.append(
                score_one(result_dir, model, repo_root, baseline=args.baseline),
            )

        repo_metrics.inter_judge_axis_disagreement = _disagreement_buckets(
            repo_metrics.passes,
        )
        suffix = f".{args.baseline}" if args.baseline else ""
        (result_dir / f"metrics{suffix}.json").write_text(
            json.dumps(asdict(repo_metrics), indent=2),
        )

    aggregate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
