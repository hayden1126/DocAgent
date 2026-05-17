"""Golden snapshot for LiteLLMBackend (Plan 08-06).

Drives `LiteLLMBackend` end-to-end against `tests/golden/fixtures/tinylib_ts/`
using LiteLLM's built-in `mock_response` parameter — no live API calls,
no env vars required. Uses the Anthropic-direct routing path
(`anthropic/claude-sonnet-4-6`) which RESEARCH.md identifies as the
stable choice for committed snapshots.

Skip-condition: pytest.importorskip("litellm") so default-`[dev]`-extras
CI passes cleanly without `[multi]` installed.

Re-record with: `UPDATE_SNAPSHOTS=1 pytest tests/golden/test_litellm_backend_snapshot.py`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

# Skip the entire module when litellm isn't installed (default dev extras).
litellm = pytest.importorskip("litellm")

from docagent.backends.base import GenerationRequest  # noqa: E402
from docagent.backends.litellm_backend import LiteLLMBackend  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "tinylib_ts"
SNAPSHOT = Path(__file__).parent / "snapshots" / "tinylib_ts_litellm_readme.md"

# Hand-crafted "model output" — pinned to a stable, citation-bearing README
# shape. LiteLLM's `mock_response="..."` returns this verbatim as the
# `choices[0].message.content` of a synthetic response, with no tool_calls
# (the mock mode doesn't exercise the tool-use loop — which is exactly
# what we want for snapshot stability).
MOCK_README = (
    "# tinylib_ts\n"
    "\n"
    "A tiny TypeScript library used as a DocAgent test fixture. "
    "<!-- ground: package.json:1-15 -->\n"
    "\n"
    "## Usage\n"
    "\n"
    "Import the public API from the main entry point. "
    "<!-- ground: src/index.ts:1-10 -->\n"
)


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        artifact_id="readme",
        prompt="Generate a README.md for this tinylib_ts library.",
        repo_root=FIXTURE.resolve(),
    )


@pytest.fixture
def _mock_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrap `litellm.completion` to inject `mock_response=MOCK_README`
    into kwargs. LiteLLM's mock_response is a built-in SDK feature — it
    returns a synthetic ModelResponse without touching any provider API.
    """
    original = litellm.completion

    def wrapper(**kwargs: Any) -> Any:
        kwargs["mock_response"] = MOCK_README
        return original(**kwargs)

    monkeypatch.setattr(litellm, "completion", wrapper)


def test_litellm_backend_snapshot(_mock_completion) -> None:
    """End-to-end LiteLLMBackend snapshot against tinylib_ts/."""
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6")
    response = backend.run(_make_request())

    actual = response.content
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(actual, encoding="utf-8")
        pytest.skip(f"Snapshot updated at {SNAPSHOT}")

    if not SNAPSHOT.exists():
        raise AssertionError(
            f"Snapshot {SNAPSHOT} does not exist. Re-record with "
            f"UPDATE_SNAPSHOTS=1."
        )
    expected = SNAPSHOT.read_text(encoding="utf-8")
    assert actual == expected


def test_litellm_snapshot_cost_attached(_mock_completion) -> None:
    """response.cost_usd is attached (either a float or 0.0 from Tier 3).
    What matters is the field is present, not its specific value."""
    backend = LiteLLMBackend(model="anthropic/claude-sonnet-4-6")
    response = backend.run(_make_request())
    assert response.cost_usd is not None
    assert isinstance(response.cost_usd, float)
