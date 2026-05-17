#!/usr/bin/env python3
"""Citation-rate measurement tool for LLM backends.

Runs the `LiteLLMBackend` against a fixture (default
`tests/golden/fixtures/tinylib_ts/`) with a README-style prompt, then
measures what fraction of the generated `<!-- ground: path:lines -->`
citations resolve via DocAgent's existing citations gate.

Output goes to stderr (one human-readable summary) and to a JSON file
(default `.planning/decisions/0001-spike-results.json`).

Permanent measurement tool — used both for ADR-0001 ingestion and for
future allowlist additions (new Gemini SKUs, Ollama re-measurement when
the model lineup justifies it, etc.).

Usage:
    # Gemini (requires GEMINI_API_KEY env var):
    python scripts/measure_citation_rate.py --model gemini/gemini-2.5-flash

    # OpenRouter (requires OPENROUTER_API_KEY):
    python scripts/measure_citation_rate.py --model openrouter/anthropic/claude-sonnet-4-6

    # Anthropic-direct via LiteLLM (requires ANTHROPIC_API_KEY):
    python scripts/measure_citation_rate.py --model anthropic/claude-sonnet-4-6

Citation gating definition (from ADR-0001):
- ≥80%: ships in BACKEND-01 allowlist.
- 60-79%: ships behind [unsupported-model] WARN; opt-in.
- <60%: dropped from BACKEND-01 scope.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_prompt(target_path: Path) -> str:
    return (
        "Generate a short README.md for the TypeScript package at the current "
        "working directory. Use Read, Glob, and Grep to discover what the "
        "package exports. The README must include a one-paragraph overview "
        "and a short 'Usage' section. Every non-trivial claim must end with a "
        "`<!-- ground: path:line-start-line-end -->` HTML comment. Paths are "
        "repo-relative POSIX. Do not invent symbols. Output only the Markdown."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="LiteLLM model string.")
    parser.add_argument(
        "--fixture",
        default="tests/golden/fixtures/tinylib_ts",
        help="Repo-relative fixture path.",
    )
    parser.add_argument(
        "--out",
        default=".planning/decisions/0001-spike-results.json",
        help="JSON output path (relative to repo root).",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT))
    from docagent.backends.base import GenerationRequest
    from docagent.backends.litellm_backend import LiteLLMBackend
    from docagent.citations import iter_citations

    fixture = (REPO_ROOT / args.fixture).resolve()
    if not fixture.is_dir():
        sys.stderr.write(f"fixture not found: {fixture}\n")
        return 2

    backend = LiteLLMBackend(model=args.model)
    request = GenerationRequest(
        artifact_id="spike_readme",
        prompt=_build_prompt(fixture),
        repo_root=fixture,
    )

    started = time.monotonic()
    try:
        response = backend.run(request)
    except Exception as exc:
        sys.stderr.write(f"backend failed: {exc}\n")
        return 3
    duration = time.monotonic() - started

    citations = list(iter_citations(response.content.encode("utf-8")))
    resolved = 0
    unresolved: list[dict[str, object]] = []
    for cite in citations:
        cite_path_str = cite.path.decode("utf-8") if isinstance(cite.path, bytes) else cite.path
        cited_path = fixture / cite_path_str
        ok = False
        if cited_path.is_file():
            line_count = sum(1 for _ in cited_path.open(encoding="utf-8", errors="replace"))
            if 1 <= cite.line_start <= cite.line_end <= line_count:
                ok = True
        if ok:
            resolved += 1
        else:
            unresolved.append(
                {"path": cite_path_str, "line_start": cite.line_start, "line_end": cite.line_end}
            )

    rate = (resolved / len(citations)) if citations else 0.0
    summary = {
        "model": args.model,
        "fixture": args.fixture,
        "duration_sec": round(duration, 2),
        "content_chars": len(response.content),
        "tool_calls": response.tool_calls,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "citations_total": len(citations),
        "citations_resolved": resolved,
        "citation_emission_rate": round(rate, 3),
        "verdict": (
            "ships_as_is" if rate >= 0.8
            else "ships_with_warn" if rate >= 0.6
            else "drop_from_backend_01"
        ),
        "unresolved": unresolved[:20],
    }

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    sys.stderr.write(
        f"\n=== Phase 8 spike: {args.model} ===\n"
        f"  citations: {resolved}/{len(citations)} resolved "
        f"({summary['citation_emission_rate']:.1%})\n"
        f"  verdict:   {summary['verdict']}\n"
        f"  tokens:    in={response.input_tokens} out={response.output_tokens} "
        f"tool_calls={response.tool_calls}\n"
        f"  wall:      {duration:.1f}s\n"
        f"  output:    {out_path}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
