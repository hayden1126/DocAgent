"""Regeneration benchmark - clone + strip + regenerate phase.

For each repo in corpus.yaml:
  1. Shallow-clone at the pinned SHA into clones/<name>/
  2. Move all external-facing docs (README, AGENTS.md, CLAUDE.md,
     llms.txt, docs/) into results/<name>-<sha>/original/
  3. Run `docagent init` against the stripped clone
  4. Copy the regenerated docs into results/<name>-<sha>/regenerated/
  5. Write run metadata (cost, wall, verifier exit, artifact list) to
     results/<name>-<sha>/run.json

This phase is deterministic apart from the LLM call inside docagent.
Scoring runs in score.py.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. `pip install pyyaml`.", file=sys.stderr)
    sys.exit(2)


HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus.yaml"
CLONES = HERE / "clones"
RESULTS = HERE / "results"

DOC_TARGETS_FILES = (
    "README.md",
    "README.rst",
    "AGENTS.md",
    "CLAUDE.md",
    "llms.txt",
    "llms-full.txt",
)
DOC_TARGETS_DIRS = ("docs",)


@dataclass
class RepoSpec:
    name: str
    language: str
    url: str
    sha: str | None
    notes: str = ""


EXPECTED_ROOT_ARTIFACTS = ("README.md", "AGENTS.md", "CLAUDE.md", "llms.txt")


@dataclass
class RunRecord:
    name: str
    sha: str
    backend: str
    artifacts_written: list[str]
    artifacts_expected: list[str]
    write_rate: float
    docagent_init_exit: int
    docagent_verify_exit: int
    cost_usd: float | None
    wall_seconds: float
    stripped_paths: list[str]


def load_corpus(path: Path) -> list[RepoSpec]:
    data = yaml.safe_load(path.read_text())
    return [RepoSpec(**entry) for entry in data["repos"]]


def shallow_clone(spec: RepoSpec, dest: Path) -> str:
    """Clone `spec.url` at `spec.sha` into `dest`. Returns the resolved SHA."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--filter=blob:none", spec.url, str(dest)], check=True)
    if spec.sha:
        subprocess.run(["git", "-C", str(dest), "checkout", spec.sha], check=True)
        return spec.sha
    sha = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return sha


def _is_sphinx_dir(d: Path) -> bool:
    """Return True if `d` looks like a Sphinx source tree.

    Heuristic: presence of `conf.py` OR any `*.rst` file. DocAgent emits
    Markdown into `docs/reference/` and `docs/how-to/`; pitting that
    against Sphinx RST is an unfair comparison (KNOWN-GAPS.md §4).
    """
    if (d / "conf.py").exists():
        return True
    try:
        return any(d.glob("**/*.rst"))
    except OSError:
        return False


def strip_docs(clone_dir: Path, archive_dir: Path) -> list[str]:
    """Move external-facing docs out of `clone_dir` into `archive_dir`.
    Inline docstrings and code comments are intentionally NOT touched.

    Sphinx `docs/` trees (detected via conf.py or *.rst presence) are
    LEFT IN PLACE — DocAgent writes Markdown and can't reproduce RST,
    so stripping a Sphinx tree would pit DocAgent against an artifact
    it categorically can't recreate. A WARN is printed and the directory
    name is suffixed with ` (skipped:sphinx)` in the returned list so
    `run.json` records the decision.
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for name in DOC_TARGETS_FILES:
        src = clone_dir / name
        if src.exists() and src.is_file():
            shutil.move(str(src), str(archive_dir / name))
            moved.append(name)
    for name in DOC_TARGETS_DIRS:
        src = clone_dir / name
        if src.exists() and src.is_dir():
            if _is_sphinx_dir(src):
                print(
                    f"[strip_docs] WARN: {src} looks like a Sphinx source "
                    f"tree (conf.py or *.rst present); leaving in place so "
                    f"DocAgent's Markdown output isn't compared against RST."
                )
                moved.append(name + "/ (skipped:sphinx)")
                continue
            shutil.move(str(src), str(archive_dir / name))
            moved.append(name + "/")
    return moved


_COST_RE = re.compile(r"cost=\$([0-9]+\.[0-9]+)")


def _parse_cost_from_stdout(stdout: str) -> float | None:
    """Best-effort: grep last `cost=$X.XXX` token from docagent stdout.

    docagent emits this in cli.py:147 via `format_usd(summary.cost_usd)`. The
    cleaner path would be a `last_run_cost_usd` field in `.docagent/state.json`,
    but `RunState` (docagent/core/state.py:17-31) doesn't carry one today.
    """
    matches = _COST_RE.findall(stdout)
    return float(matches[-1]) if matches else None


def run_docagent_init(
    clone_dir: Path, backend: str, max_cost: float
) -> tuple[int, list[str], float | None]:
    """Invoke `docagent init` in clone_dir.

    Returns (exit_code, artifact_files_written, cost_usd_or_none).
    """
    cmd = [
        "docagent", "init",
        "-C", str(clone_dir),
        "--backend", backend,
        "--max-cost", str(max_cost),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    written = [
        name for name in (*DOC_TARGETS_FILES, "docs")
        if (clone_dir / name).exists()
    ]
    return proc.returncode, written, _parse_cost_from_stdout(proc.stdout)


def run_docagent_verify(clone_dir: Path) -> int:
    proc = subprocess.run(
        ["docagent", "verify", "-C", str(clone_dir)],
        capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def copy_regenerated(clone_dir: Path, dest: Path, artifact_names: list[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in artifact_names:
        src = clone_dir / name
        if src.is_dir():
            shutil.copytree(src, dest / name, dirs_exist_ok=True)
        elif src.is_file():
            shutil.copy2(src, dest / name)


def run_one(spec: RepoSpec, backend: str, max_cost: float) -> RunRecord:
    clone_dir = CLONES / spec.name
    sha = shallow_clone(spec, clone_dir)
    result_dir = RESULTS / f"{spec.name}-{sha[:12]}"
    if result_dir.exists():
        shutil.rmtree(result_dir)
    original_dir = result_dir / "original"
    regenerated_dir = result_dir / "regenerated"

    stripped = strip_docs(clone_dir, original_dir)
    print(f"[{spec.name}] stripped: {stripped}")

    t0 = time.monotonic()
    init_exit, written, cost_usd = run_docagent_init(clone_dir, backend, max_cost)
    wall = time.monotonic() - t0
    verify_exit = run_docagent_verify(clone_dir)
    copy_regenerated(clone_dir, regenerated_dir, written)

    written_root = [a for a in written if a in EXPECTED_ROOT_ARTIFACTS]
    expected = list(EXPECTED_ROOT_ARTIFACTS)
    write_rate = len(written_root) / len(expected) if expected else 0.0

    record = RunRecord(
        name=spec.name,
        sha=sha,
        backend=backend,
        artifacts_written=written,
        artifacts_expected=expected,
        write_rate=write_rate,
        docagent_init_exit=init_exit,
        docagent_verify_exit=verify_exit,
        cost_usd=cost_usd,
        wall_seconds=wall,
        stripped_paths=stripped,
    )
    (result_dir / "run.json").write_text(json.dumps(asdict(record), indent=2))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="agent_sdk",
                        help="Backend to pass to `docagent init --backend` "
                             "(agent_sdk | litellm; see docagent/cli.py:26).")
    parser.add_argument("--max-cost", type=float, default=5.0,
                        help="Per-repo cost cap in USD.")
    parser.add_argument("--only", action="append", default=[],
                        help="Run only these repo names (repeatable).")
    args = parser.parse_args()

    corpus = load_corpus(CORPUS)
    if args.only:
        corpus = [s for s in corpus if s.name in args.only]
    if not corpus:
        print("ERROR: no repos selected; check corpus.yaml or --only.", file=sys.stderr)
        return 2

    records: list[RunRecord] = []
    for spec in corpus:
        if spec.sha is None:
            print(f"WARNING: {spec.name} has no pinned SHA; "
                  f"will use current HEAD. Pin it for reproducibility.")
        try:
            records.append(run_one(spec, args.backend, args.max_cost))
        except subprocess.CalledProcessError as exc:
            print(f"[{spec.name}] FAILED: {exc}", file=sys.stderr)

    summary = RESULTS / "run-summary.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps([asdict(r) for r in records], indent=2))
    print(f"\nWrote summary: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
