"""DocAgent CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from docagent import __version__
from docagent.artifacts.builtins import register_v1_builtins
from docagent.artifacts.registry import Registry
from docagent.core import diff, state
from docagent.core.scanner import Scanner
from docagent.index.store import open_store

app = typer.Typer(
    name="docagent",
    help="Repository documentation agent for humans and coding agents.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _registry() -> Registry:
    reg = Registry()
    register_v1_builtins(reg)
    return reg


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"docagent {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    pass


@app.command()
def init(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
) -> None:
    """Full pass: scan repo, build index, generate all artifacts."""
    console.print(f"[bold]init[/bold] {repo}")
    scanner = Scanner(repo)
    store = open_store(repo)

    n_files = 0
    n_symbols = 0
    now = datetime.now(timezone.utc).isoformat()
    for scanned in scanner.walk():
        n_files += 1
        parsed = scanned.adapter.parse(scanned.path, scanned.path.read_bytes())
        symbols = scanned.adapter.extract_symbols(parsed)
        n_symbols += len(symbols)
        rows = [
            (
                s.qualified_name,
                s.kind,
                str(s.file.relative_to(repo)) if s.file.is_absolute() else str(s.file),
                s.byte_start,
                s.byte_end,
                s.line_start,
                s.line_end,
                s.signature,
                s.existing_doc,
                scanned.adapter.language_id,
                scanned.sha256,
            )
            for s in symbols
        ]
        rel = str(scanned.path.relative_to(repo)) if scanned.path.is_absolute() else str(scanned.path)
        store.replace_symbols_for_file(rel, rows)
        store.upsert_file_hash(rel, scanned.sha256, scanned.adapter.language_id, now)

    console.print(f"indexed [cyan]{n_files}[/cyan] files, [cyan]{n_symbols}[/cyan] symbols")

    registry = _registry()
    order = registry.topo_order()
    console.print(f"artifacts (topo order): {[a.id for a in order]}")
    console.print("[yellow]note:[/yellow] artifact generation is not yet wired (v1 scaffold).")

    rs = state.RunState.load(repo)
    rs.doc_version = diff.current_head(repo)
    rs.last_run = now
    rs.save(repo)
    store.close()


@app.command()
def update(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
) -> None:
    """Incremental refresh: regenerate artifacts affected by changes since the last run."""
    console.print(f"[bold]update[/bold] {repo}")
    rs = state.RunState.load(repo)
    if rs.doc_version is None:
        console.print("[yellow]no doc_version found[/yellow] — run `docagent init` first.")
        raise typer.Exit(code=2)
    try:
        changed = diff.changed_files_since(repo, rs.doc_version)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"changed files: {len(changed)}")
    for p in changed[:25]:
        console.print(f"  - {p}")
    console.print("[yellow]note:[/yellow] affected-artifact resolution is not yet wired.")


@app.command()
def verify(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
    strict: bool = typer.Option(False, "--strict", help="Fail on any warning."),
) -> None:
    """Run the deterministic-first verifier pipeline against existing artifacts."""
    from docagent.verify.pipeline import default_pipeline

    console.print(f"[bold]verify[/bold] {repo} (strict={strict})")
    pipeline = default_pipeline()
    console.print(f"gates: {[g.name for g in pipeline.gates]}")
    console.print("[yellow]note:[/yellow] gate execution against on-disk artifacts is not yet wired.")


if __name__ == "__main__":
    app()
