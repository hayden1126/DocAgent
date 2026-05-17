"""Centralised logging setup for DocAgent.

By default the package logs at WARNING. ``--debug`` on any CLI command, or
``DOCAGENT_DEBUG=1`` in the environment, switches to DEBUG and routes the
output to stderr. Logging is intentionally *not* configured at import time;
the CLI calls :func:`setup_logging` from its root callback so library users
who embed DocAgent inherit their host application's logging config.
"""

from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "docagent"


def setup_logging(debug: bool = False) -> None:
    """Initialise the ``docagent`` logger. Idempotent; safe to call twice."""
    enabled = debug or _env_truthy(os.environ.get("DOCAGENT_DEBUG"))
    level = logging.DEBUG if enabled else logging.WARNING

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    # Reset handlers so repeated calls (e.g. from tests) don't pile up.
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    # Bubble nothing up to root; our handler is the single output.
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return ``docagent.<name>`` logger. Convenience for module-local use."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def _env_truthy(value: str | None) -> bool:
    return value is not None and value.lower() not in {"", "0", "false", "no"}
