"""Logging setup tests.

The CLI is responsible for initialising the ``docagent`` logger via
``--debug`` or ``DOCAGENT_DEBUG``. Library users who embed DocAgent should
NOT find their root logger reconfigured.
"""

from __future__ import annotations

import logging

import pytest

from docagent._logging import get_logger, setup_logging


def _docagent_logger() -> logging.Logger:
    return logging.getLogger("docagent")


def test_default_is_warning() -> None:
    setup_logging(debug=False)
    assert _docagent_logger().level == logging.WARNING


def test_debug_flag_sets_debug_level() -> None:
    setup_logging(debug=True)
    try:
        assert _docagent_logger().level == logging.DEBUG
    finally:
        setup_logging(debug=False)


def test_env_var_enables_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCAGENT_DEBUG", "1")
    setup_logging(debug=False)
    try:
        assert _docagent_logger().level == logging.DEBUG
    finally:
        monkeypatch.delenv("DOCAGENT_DEBUG", raising=False)
        setup_logging(debug=False)


def test_env_var_falsey_values_do_not_enable(monkeypatch: pytest.MonkeyPatch) -> None:
    for val in ("", "0", "false", "no"):
        monkeypatch.setenv("DOCAGENT_DEBUG", val)
        setup_logging(debug=False)
        assert _docagent_logger().level == logging.WARNING, val


def test_repeated_setup_does_not_pile_handlers() -> None:
    setup_logging(debug=True)
    setup_logging(debug=True)
    setup_logging(debug=False)
    assert len(_docagent_logger().handlers) == 1


def test_get_logger_returns_namespaced() -> None:
    assert get_logger("orchestrator").name == "docagent.orchestrator"


def test_does_not_configure_root_logger() -> None:
    """Library users mustn't have their root logger hijacked."""
    root_handlers_before = list(logging.getLogger().handlers)
    setup_logging(debug=True)
    setup_logging(debug=False)
    assert list(logging.getLogger().handlers) == root_handlers_before
