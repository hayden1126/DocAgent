# tinylib

> A tiny Python library that exposes a single Typer-based `greet` command. <!-- ground: tinylib/cli.py:7-13 --> It exists as a golden-test fixture for DocAgent's snapshot harness, not for production use.

The package is named `tinylib` and is configured by `pyproject.toml`. <!-- ground: pyproject.toml:5-7 -->

## Code

- [tinylib/__init__.py](tinylib/__init__.py): Package init; exposes `__version__`. <!-- ground: tinylib/__init__.py:1-3 -->
- [tinylib/cli.py](tinylib/cli.py): Typer app definition and the `greet` command. <!-- ground: tinylib/cli.py:7-13 -->

## Build

- [pyproject.toml](pyproject.toml): Build configuration, dependencies, and the `tinylib` console script entry. <!-- ground: pyproject.toml:13-14 -->

## Optional

- [LICENSE](LICENSE): MIT license text. <!-- ground: LICENSE:1-1 -->
