---
docagent_artifact: api_reference
module: docagent._logging
generated_by: docagent
---

# `docagent._logging`


The `docagent._logging` module centralises logging configuration for the package, deferring setup until the CLI explicitly invokes it so that library embedders keep their own host configuration. `setup_logging` initialises a single stderr handler on the `docagent` logger at DEBUG or WARNING (driven by the `--debug` flag or the `DOCAGENT_DEBUG` environment variable) and is idempotent, while `get_logger` returns child loggers under the `docagent.` namespace for module-local use. <!-- ground: docagent/_logging.py:1-44 -->

## Public surface

| Name | Kind | Signature |
|------|------|-----------|
| `setup_logging` | function | `setup_logging` |
| `get_logger` | function | `get_logger` |

## Common workflows

Initialise logging once at CLI entry, opting into debug output either by argument or environment variable:

```python
from docagent._logging import setup_logging

setup_logging(debug=True)  # equivalent to DOCAGENT_DEBUG=1
```
<!-- ground: docagent/_logging.py:19-35 -->

Acquire a child logger for a module under the `docagent.` namespace:

```python
from docagent._logging import get_logger

log = get_logger(__name__)  # e.g. "docagent.core.orchestrator"
log.debug("planning artifacts")
```
<!-- ground: docagent/_logging.py:38-40 -->

<!-- For rendered per-symbol details, point mkdocstrings or pdoc at this module. -->
