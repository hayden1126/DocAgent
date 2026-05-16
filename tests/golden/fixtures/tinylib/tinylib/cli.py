"""Tinylib CLI entry point."""

from __future__ import annotations

import typer

app = typer.Typer(name="tinylib", help="A tiny library.")


@app.command()
def greet(name: str = "world") -> None:
    """Print a friendly greeting."""
    typer.echo(f"hello, {name}!")
