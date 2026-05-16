# tinylib

A tiny library used as a DocAgent golden-test fixture. <!-- ground: pyproject.toml:8-8 -->

## Why

`tinylib` is a deliberately minimal Python library for exercising DocAgent's
golden-snapshot harness. It ships a Typer-based CLI with a single command and
no production purpose. <!-- ground: tinylib/cli.py:7-13 -->

## Install

```bash
pip install tinylib
```

Requires Python ≥ 3.10. <!-- ground: pyproject.toml:9-9 --> The package is
named `tinylib` and installs a `tinylib` console script. <!-- ground: pyproject.toml:13-14 -->

## Quickstart

```bash
tinylib greet --name world
```

The `greet` command prints a friendly greeting. <!-- ground: tinylib/cli.py:10-13 -->

## Architecture

- `tinylib/__init__.py` exports `__version__`. <!-- ground: tinylib/__init__.py:1-3 -->
- `tinylib/cli.py` defines the Typer app and the `greet` command. <!-- ground: tinylib/cli.py:1-13 -->

## Status

Pre-alpha — this package exists only as a test fixture. <!-- ground: pyproject.toml:7-7 -->

## License

MIT. <!-- ground: LICENSE:1-1 -->
