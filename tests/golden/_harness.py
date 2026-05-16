"""Shared infrastructure for golden snapshot tests.

The point of these tests is to catch *post-pipeline* regressions
deterministically: cleaner logic, citation validation, write formatting. Real
LLM regression detection is a separate concern (humans + slow nightly runs).

Pattern:
- ``RecordedBackend`` replays a saved LLM response from disk.
- Each test loads a fixture repo, runs an artifact generator with a recorded
  backend, and asserts byte-equality between the produced content and a
  committed snapshot.
- Setting ``UPDATE_SNAPSHOTS=1`` in the environment rewrites the snapshot on
  the fly — review the diff and commit deliberately.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from docagent.backends.base import GenerationRequest, GenerationResponse

GOLDEN_DIR = Path(__file__).parent
FIXTURES_DIR = GOLDEN_DIR / "fixtures"
RECORDINGS_DIR = GOLDEN_DIR / "recordings"
SNAPSHOTS_DIR = GOLDEN_DIR / "snapshots"


@dataclass
class RecordedBackend:
    """A backend that returns a fixed response read from disk."""

    name: str = "recorded"
    recording_path: Path | None = None

    def run(self, request: GenerationRequest) -> GenerationResponse:
        if self.recording_path is None:
            raise RuntimeError("RecordedBackend.recording_path is not set")
        content = self.recording_path.read_text(encoding="utf-8")
        return GenerationResponse(content=content, tool_calls=0)


def assert_or_update_snapshot(snapshot_name: str, actual: str) -> None:
    """Compare ``actual`` to the committed snapshot, or rewrite if env says so."""
    snapshot_path = SNAPSHOTS_DIR / snapshot_name
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual, encoding="utf-8")
        return
    if not snapshot_path.exists():
        raise AssertionError(
            f"Snapshot {snapshot_path} does not exist. Run with UPDATE_SNAPSHOTS=1."
        )
    expected = snapshot_path.read_text(encoding="utf-8")
    if expected != actual:
        # Surface a diff in the failure message — pytest will render it.
        import difflib

        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=str(snapshot_path) + " (committed)",
                tofile="(actual)",
                lineterm="",
            )
        )
        raise AssertionError(
            f"Snapshot mismatch for {snapshot_name}.\n"
            "Run with UPDATE_SNAPSHOTS=1 to accept, then review the diff.\n\n"
            + diff
        )
