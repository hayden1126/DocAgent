# tinylib

A tiny Python library exposing a single `greet` CLI command via Typer. <!-- ground: tinylib/cli.py:7-13 -->

## Quick commands

```bash
pip install -e .           # install in editable mode
tinylib greet --name foo   # run the only command
```

The package installs a `tinylib` console script. <!-- ground: pyproject.toml:13-14 -->

## Where to look

- `tinylib/cli.py` — the Typer app and `greet` command definition. <!-- ground: tinylib/cli.py:7-13 -->
- `tinylib/__init__.py` — package init; only exposes `__version__`. <!-- ground: tinylib/__init__.py:1-3 -->
- `pyproject.toml` — build metadata and the `[project.scripts]` entry. <!-- ground: pyproject.toml:13-14 -->

## Conventions Claude should follow

- Use `from __future__ import annotations` in new modules; the existing CLI does so. <!-- ground: tinylib/cli.py:3-3 -->
- Add a module-level docstring at the top of new files. <!-- ground: tinylib/cli.py:1-1 -->
- Declare new CLI commands with `@app.command()` on the existing Typer app. <!-- ground: tinylib/cli.py:10-13 -->

## Gotchas

- This fixture has no test suite; do not assume `pytest` exists in the project graph until one is added.
- `LICENSE` is the MIT license text; do not modify it. <!-- ground: LICENSE:1-1 -->

## Test invocation

No tests are configured. If a test suite is added, prefer `pytest` and place tests under `tests/`.
