"""Tests for the regeneration benchmark's scoring half.

Covers helpers in `benchmarks/regeneration/score.py`:
- `_parse_json_response` — fence stripping for LLM outputs
- `_approx_tokens` / `_claims_per_1000_tokens` — length normalization
- `_safe` — model-string-to-path sanitizer
- `_ensure_judge_credentials` — SystemExit on missing env var
- `_disagreement_buckets` — cross-judge axis-gap accounting
- `_safe_judge_call` — try/except contract: runtime exceptions
  become a `(None, cost, error)` tuple; SystemExit propagates
- `_score_axis` — defensive parse: accepts `{axis_name: N}` and
  emits a `-1` sentinel rather than raising when both keys absent
"""

from __future__ import annotations

import json

import pytest

from benchmarks.regeneration import score as s


# ---- JSON parse + fence stripping --------------------------------------

def test_parse_json_response_bare() -> None:
    assert s._parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_response_fenced_with_lang() -> None:
    assert s._parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_response_fenced_plain() -> None:
    assert s._parse_json_response('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_response_raises_on_garbage() -> None:
    with pytest.raises(json.JSONDecodeError):
        s._parse_json_response("this is not JSON")


# ---- Length normalization ----------------------------------------------

def test_approx_tokens_minimum_is_one() -> None:
    assert s._approx_tokens("") == 1


def test_approx_tokens_four_chars_per_token() -> None:
    assert s._approx_tokens("a" * 4000) == 1000


def test_claims_per_1000_tokens_normalizes() -> None:
    # 4000 chars ≈ 1000 tokens; 20 claims → 20.0 claims per 1k tokens
    assert s._claims_per_1000_tokens(20, "a" * 4000) == 20.0


# ---- Path-safe model name ----------------------------------------------

def test_safe_replaces_slash() -> None:
    assert s._safe("anthropic/claude-opus-4-7") == "anthropic_claude-opus-4-7"


def test_safe_replaces_special_chars() -> None:
    assert s._safe("openrouter/meta-llama/llama-3.1-70b") == "openrouter_meta-llama_llama-3.1-70b"


# ---- Credentials gate --------------------------------------------------

def test_ensure_judge_credentials_raises_for_known_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        s._ensure_judge_credentials("anthropic/claude-opus-4-7")
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_ensure_judge_credentials_skips_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unknown provider → no env var to check; LiteLLM surfaces its own error
    # downstream. We must NOT spuriously raise here.
    s._ensure_judge_credentials("mystery/some-model")  # no raise


def test_ensure_judge_credentials_passes_when_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    s._ensure_judge_credentials("anthropic/claude-opus-4-7")  # no raise


# ---- Inter-judge axis disagreement -------------------------------------

def test_disagreement_buckets_empty_for_single_judge() -> None:
    pass_ = s.JudgePassMetrics(
        judge_model="anthropic/claude-opus-4-7",
        completeness=s.AxisScore(5, ""),
    )
    assert s._disagreement_buckets([pass_]) == {}


def test_disagreement_buckets_reports_max_axis_gap() -> None:
    p1 = s.JudgePassMetrics(
        judge_model="a",
        completeness=s.AxisScore(5, ""),
        helpfulness=s.AxisScore(4, ""),
        truthfulness=s.AxisScore(3, ""),
    )
    p2 = s.JudgePassMetrics(
        judge_model="b",
        completeness=s.AxisScore(2, ""),
        helpfulness=s.AxisScore(4, ""),
        truthfulness=s.AxisScore(1, ""),
    )
    assert s._disagreement_buckets([p1, p2]) == {
        "completeness": 3,
        "helpfulness": 0,
        "truthfulness": 2,
    }


# ---- Safe judge call ---------------------------------------------------

def test_safe_judge_call_swallows_runtime_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(prompt: str, model: str) -> tuple[str, float]:
        raise RuntimeError("upstream 429")

    monkeypatch.setattr(s, "call_judge", fake)
    payload, cost, err = s._safe_judge_call("x", "anthropic/claude-opus-4-7")
    assert payload is None
    assert cost == 0.0
    assert err is not None and "RuntimeError" in err and "429" in err


def test_safe_judge_call_records_partial_cost_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If we got a response but couldn't parse it, the provider was still
    billed — cost should be recorded."""
    def fake(prompt: str, model: str) -> tuple[str, float]:
        return "not json at all", 0.012

    monkeypatch.setattr(s, "call_judge", fake)
    payload, cost, err = s._safe_judge_call("x", "anthropic/claude-opus-4-7")
    assert payload is None
    assert cost == 0.012
    assert err is not None and "JSONDecodeError" in err


def test_safe_judge_call_passes_through_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(prompt: str, model: str) -> tuple[str, float]:
        return '{"jaccard": 0.42}', 0.001

    monkeypatch.setattr(s, "call_judge", fake)
    payload, cost, err = s._safe_judge_call("x", "anthropic/claude-opus-4-7")
    assert payload == {"jaccard": 0.42}
    assert cost == 0.001
    assert err is None


def test_safe_judge_call_lets_system_exit_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential / install failures should abort the run, not be logged
    per-call. Catching SystemExit here would mean a missing API key
    silently produced empty metrics for every repo."""
    def fake(prompt: str, model: str) -> tuple[str, float]:
        raise SystemExit("missing ANTHROPIC_API_KEY")

    monkeypatch.setattr(s, "call_judge", fake)
    with pytest.raises(SystemExit):
        s._safe_judge_call("x", "anthropic/claude-opus-4-7")


# ---- Defensive axis-score parse ----------------------------------------

def test_score_axis_accepts_score_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(prompt: str, model: str) -> tuple[str, float]:
        return '{"score": 4, "rationale": "ok"}', 0.001

    monkeypatch.setattr(s, "call_judge", fake)
    axis, cost, err = s._score_axis(
        "rubric_completeness", "completeness", "doc", "anthropic/claude-opus-4-7",
    )
    assert axis is not None and axis.score == 4
    assert err is None


def test_score_axis_falls_back_to_axis_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real LLMs sometimes emit {axis_name: N} despite the prompt asking
    for {"score": N}. The defensive parse should accept either."""
    def fake(prompt: str, model: str) -> tuple[str, float]:
        return '{"completeness": 3, "rationale": "ok"}', 0.001

    monkeypatch.setattr(s, "call_judge", fake)
    axis, cost, err = s._score_axis(
        "rubric_completeness", "completeness", "doc", "anthropic/claude-opus-4-7",
    )
    assert axis is not None and axis.score == 3
    assert err is None


def test_score_axis_sentinel_when_score_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(prompt: str, model: str) -> tuple[str, float]:
        return '{"rationale": "no score field"}', 0.001

    monkeypatch.setattr(s, "call_judge", fake)
    axis, cost, err = s._score_axis(
        "rubric_completeness", "completeness", "doc", "anthropic/claude-opus-4-7",
    )
    assert axis is not None and axis.score == -1
    assert err is None
