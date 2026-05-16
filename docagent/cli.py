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


def _index_repo(repo: Path, store, now: str) -> tuple[int, int]:
    scanner = Scanner(repo)
    n_files = 0
    n_symbols = 0
    for scanned in scanner.walk():
        n_files += 1
        parsed = scanned.adapter.parse(scanned.path, scanned.path.read_bytes())
        symbols = scanned.adapter.extract_symbols(parsed)
        n_symbols += len(symbols)
        rel = str(scanned.path.relative_to(repo)) if scanned.path.is_absolute() else str(scanned.path)
        rows = [
            (
                s.qualified_name,
                s.kind,
                rel,
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
        store.replace_symbols_for_file(rel, rows)
        store.upsert_file_hash(rel, scanned.sha256, scanned.adapter.language_id, now)
    return n_files, n_symbols


@app.command()
def init(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
    only: list[str] = typer.Option(
        [], "--only", help="Restrict to one or more artifact ids (repeatable)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print diffs; do not write."),
    skip_index: bool = typer.Option(
        False, "--skip-index", help="Skip the symbol index rebuild (use existing .docagent/index.db)."
    ),
) -> None:
    """Full pass: scan repo, build index, generate all artifacts."""
    from docagent.backends.agent_sdk import AgentSDKBackend
    from docagent.core.orchestrator import Orchestrator

    console.print(f"[bold]init[/bold] {repo}")
    store = open_store(repo)
    now = datetime.now(timezone.utc).isoformat()

    if not skip_index:
        n_files, n_symbols = _index_repo(repo, store, now)
        console.print(f"indexed [cyan]{n_files}[/cyan] files, [cyan]{n_symbols}[/cyan] symbols")
    else:
        console.print("[yellow]skip-index[/yellow] — using existing index")

    registry = _registry()
    backend = AgentSDKBackend()
    orchestrator = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=backend,
        store=store,
        only=tuple(only),
        dry_run=dry_run,
    )
    runs = orchestrator.run()
    for r in runs:
        status = "ok" if r.verify_ok and r.error is None else "FAIL"
        color = "green" if status == "ok" else "red"
        console.print(f"[{color}]{status}[/{color}] {r.artifact_id}")
        if r.error:
            console.print(f"  [red]error:[/red] {r.error}")
        for f in r.findings[:10]:
            console.print(f"  • {f}")
        for w in r.writes:
            verb = "would write" if dry_run else ("wrote" if w.written else "unchanged")
            console.print(f"  → {verb}: {w.target}")
            if dry_run and w.diff:
                console.print(w.diff[:4000])
        if r.digest:
            console.print(
                f"  digest={r.digest[:12]}… mentions={r.mention_count}"
            )

    rs = state.RunState.load(repo)
    rs.doc_version = diff.current_head(repo)
    rs.last_run = now
    rs.save(repo)
    store.close()


@app.command()
def update(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print diffs; do not write."),
    only: list[str] = typer.Option(
        [], "--only", help="Restrict to one or more artifact ids (repeatable)."
    ),
) -> None:
    """Incremental refresh: regenerate artifacts affected by changes since the last run."""
    from docagent.backends.agent_sdk import AgentSDKBackend
    from docagent.core.affected import compute_affected_artifacts
    from docagent.core.orchestrator import Orchestrator
    from docagent.core.scanner import Scanner

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

    if not changed:
        console.print("[dim]no changes since last run[/dim]")
        return

    console.print(f"changed files: [cyan]{len(changed)}[/cyan]")

    store = open_store(repo)
    registry = _registry()

    # Re-scan changed files to compute the new symbol set, BUT first capture
    # the existing symbol set so compute_affected can diff. The affected
    # resolver reads `store.symbols_for_file()` directly (pre-update state),
    # then we hand it the new symbols as a kwarg.
    scanner = Scanner(repo)
    by_ext = scanner.by_ext
    new_symbols_by_file: dict[str, set[str]] = {}
    now = datetime.now(timezone.utc).isoformat()

    for p in changed:
        if not p.exists() or not p.is_file():
            new_symbols_by_file[
                str(p.relative_to(repo)) if p.is_absolute() else str(p)
            ] = set()
            continue
        adapter = by_ext.get(p.suffix)
        if adapter is None:
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        parsed = adapter.parse(p, data)
        new_syms = adapter.extract_symbols(parsed)
        rel = str(p.relative_to(repo)) if p.is_absolute() else str(p)
        new_symbols_by_file[rel] = {s.qualified_name for s in new_syms}

    affected = compute_affected_artifacts(repo, store, changed, new_symbols_by_file, registry)
    if only:
        affected = [aid for aid in affected if aid in only]

    if not affected:
        console.print("[dim]no artifacts affected by these changes[/dim]")
        store.close()
        return

    console.print(f"affected artifacts: [cyan]{', '.join(affected)}[/cyan]")

    # Re-index the changed files now that we've computed affected (must happen
    # after, because compute_affected diffs OLD vs NEW symbol sets).
    import hashlib as _hashlib

    for p in changed:
        if not p.exists() or not p.is_file():
            continue
        adapter = by_ext.get(p.suffix)
        if adapter is None:
            continue
        data = p.read_bytes()
        parsed = adapter.parse(p, data)
        syms = adapter.extract_symbols(parsed)
        rel = str(p.relative_to(repo)) if p.is_absolute() else str(p)
        sha = _hashlib.sha256(data).hexdigest()
        rows = [
            (
                s.qualified_name,
                s.kind,
                rel,
                s.byte_start,
                s.byte_end,
                s.line_start,
                s.line_end,
                s.signature,
                s.existing_doc,
                adapter.language_id,
                sha,
            )
            for s in syms
        ]
        store.replace_symbols_for_file(rel, rows)
        store.upsert_file_hash(rel, sha, adapter.language_id, now)

    backend = AgentSDKBackend()
    orchestrator = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=backend,
        store=store,
        changed_files=tuple(changed),
        only=tuple(affected),
        dry_run=dry_run,
    )
    runs = orchestrator.run()
    for r in runs:
        status = "ok" if r.verify_ok and r.error is None else "FAIL"
        color = "green" if status == "ok" else "red"
        console.print(f"[{color}]{status}[/{color}] {r.artifact_id}")
        if r.error:
            console.print(f"  [red]error:[/red] {r.error}")
        for f in r.findings[:10]:
            console.print(f"  • {f}")
        for w in r.writes:
            verb = "would write" if dry_run else ("wrote" if w.written else "unchanged")
            console.print(f"  → {verb}: {w.target}")
            if dry_run and w.diff:
                console.print(w.diff[:4000])
        if r.digest:
            console.print(f"  digest={r.digest[:12]}… mentions={r.mention_count}")

    if not dry_run:
        rs.doc_version = diff.current_head(repo)
        rs.last_run = now
        rs.save(repo)
    store.close()


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
