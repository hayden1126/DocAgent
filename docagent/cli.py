"""DocAgent CLI."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from docagent import __version__
from docagent._logging import get_logger, setup_logging
from docagent.artifacts.builtins import register_v1_builtins
from docagent.artifacts.registry import Registry
from docagent.core import diff, state
from docagent.core.budget import BudgetTracker
from docagent.core.paths import to_repo_rel_posix
from docagent.core.scanner import Scanner
from docagent.index.store import open_store
from docagent.pricing import format_usd

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


def _validate_max_cost(value: float) -> float:
    """Typer Option callback. Rejects negative flag values via BadParameter
    so typer produces a clean exit code 2 (parameter validation error).
    The env-var fallback is more lenient — see `_resolve_max_cost`."""
    if value < 0:
        raise typer.BadParameter("--max-cost must be >= 0; 0 disables the cap")
    return value


def _resolve_max_cost(flag_value: float) -> float:
    """Precedence: explicit flag > DOCAGENT_MAX_COST env var > 0 (off).

    Negative flag values are rejected upstream by `_validate_max_cost`.
    Env-var path is intentionally lenient: malformed or negative values
    are logged at DEBUG and treated as no cap (env vars often leak from
    unrelated parents).
    """
    if flag_value > 0:
        return flag_value
    raw = os.environ.get("DOCAGENT_MAX_COST")
    if raw is None or raw == "":
        return 0.0
    log = get_logger("cli")
    try:
        parsed = float(raw)
    except ValueError:
        log.debug("DOCAGENT_MAX_COST=%r is not a valid float; ignoring", raw)
        return 0.0
    if parsed < 0:
        log.debug("DOCAGENT_MAX_COST=%r is negative; ignoring", raw)
        return 0.0
    return parsed


def _render_summary(
    out: Console,
    tracker: BudgetTracker,
    dry_run: bool,
    effective_cap: float,
    runs_count: int,
    expected_total: int,
    wall: float,
) -> None:
    """Render the final run summary footer.

    Pure presentation: writes only to the supplied `out` Console. Both
    `init` and `update` call this function — single source of truth so
    the footer cannot drift between commands.
    """
    if dry_run:
        out.print(f"\ntokens: n/a (dry-run)  wall={wall:.1f}s")
        return
    summary = tracker.summary(
        artifacts_completed=runs_count,
        artifacts_total=expected_total,
    )
    if tracker.aborted:
        out.print(
            f"\n[yellow]aborted at {format_usd(summary.cost_usd)} of "
            f"{format_usd(effective_cap)} cap; "
            f"{summary.artifacts_completed} of {summary.artifacts_total} "
            f"artifacts shipped[/yellow]"
        )
    out.print(
        f"in={summary.input_tokens} out={summary.output_tokens} "
        f"tool_calls={summary.tool_calls} cost={format_usd(summary.cost_usd)} "
        f"wall={wall:.1f}s"
    )


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Emit DEBUG-level logs to stderr (also: DOCAGENT_DEBUG=1)."
    ),
) -> None:
    setup_logging(debug=debug)


def _index_repo(repo: Path, store, now: str) -> tuple[int, int]:
    scanner = Scanner(repo)
    n_files = 0
    n_symbols = 0
    for scanned in scanner.walk():
        n_files += 1
        parsed = scanned.adapter.parse(scanned.path, scanned.path.read_bytes())
        symbols = scanned.adapter.extract_symbols(parsed)
        n_symbols += len(symbols)
        rel = to_repo_rel_posix(repo, scanned.path)
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
    max_modules: int = typer.Option(
        25,
        "--max-modules",
        help="Cap on per-module artifacts (e.g. api_reference). 0 = unlimited.",
    ),
    max_howtos: int = typer.Option(
        15,
        "--max-howtos",
        help="Cap on how-to-guide pages. 0 = unlimited.",
    ),
    max_cost: float = typer.Option(
        0.0,
        "--max-cost",
        callback=_validate_max_cost,
        help=(
            "Soft cost cap in USD; 0 (default) disables. Also reads "
            "DOCAGENT_MAX_COST. Aborts BETWEEN artifacts; exit code 3."
        ),
    ),
) -> None:
    """Full pass: scan repo, build index, generate all artifacts."""
    from docagent.backends.agent_sdk import AgentSDKBackend, BackendUnavailableError
    from docagent.core.orchestrator import Orchestrator

    start_time = time.monotonic()
    console.print(f"[bold]init[/bold] {repo}")
    store = open_store(repo)
    now = datetime.now(UTC).isoformat()

    if not skip_index:
        n_files, n_symbols = _index_repo(repo, store, now)
        console.print(f"indexed [cyan]{n_files}[/cyan] files, [cyan]{n_symbols}[/cyan] symbols")
    else:
        console.print("[yellow]skip-index[/yellow] — using existing index")

    registry = _registry()
    backend = AgentSDKBackend()
    preflight = getattr(backend, "_preflight", None)
    if preflight is not None:
        try:
            preflight()
        except BackendUnavailableError as exc:
            console.print(f"[red]{exc}[/red]")
            store.close()
            raise typer.Exit(code=2) from exc
    effective_cap = _resolve_max_cost(max_cost)
    orchestrator = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=backend,
        store=store,
        only=tuple(only),
        dry_run=dry_run,
        config={"max_modules": max_modules, "max_howtos": max_howtos},
        max_cost=effective_cap,
        console=console,
    )
    runs = orchestrator.run()
    tracker = orchestrator.tracker
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

    last_ctx_config = getattr(orchestrator, "_last_ctx_config", None) or {}
    orphans = last_ctx_config.get("how_to_orphans") or []
    if orphans:
        console.print("[yellow]Flagged orphans:[/yellow]")
        for o in orphans:
            console.print(f"  • {o}")

    wall = time.monotonic() - start_time
    expected_total = len(registry.topo_order(list(only) if only else None))
    _render_summary(
        console, tracker, dry_run, effective_cap, len(runs), expected_total, wall
    )

    rs = state.RunState.load(repo)
    rs.doc_version = diff.current_head(repo)
    rs.last_run = now
    rs.save(repo)
    store.close()

    if tracker.aborted:
        raise typer.Exit(code=3)


@app.command()
def update(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print diffs; do not write."),
    only: list[str] = typer.Option(
        [], "--only", help="Restrict to one or more artifact ids (repeatable)."
    ),
    max_howtos: int = typer.Option(
        15,
        "--max-howtos",
        help="Cap on how-to-guide pages. 0 = unlimited.",
    ),
    max_cost: float = typer.Option(
        0.0,
        "--max-cost",
        callback=_validate_max_cost,
        help=(
            "Soft cost cap in USD; 0 (default) disables. Also reads "
            "DOCAGENT_MAX_COST. Aborts BETWEEN artifacts; exit code 3."
        ),
    ),
) -> None:
    """Incremental refresh: regenerate artifacts affected by changes since the last run."""
    from docagent.backends.agent_sdk import AgentSDKBackend, BackendUnavailableError
    from docagent.core.affected import compute_affected_artifacts
    from docagent.core.orchestrator import Orchestrator
    from docagent.core.scanner import Scanner

    start_time = time.monotonic()
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
    now = datetime.now(UTC).isoformat()

    for p in changed:
        if not p.exists() or not p.is_file():
            new_symbols_by_file[to_repo_rel_posix(repo, p)] = set()
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
        rel = to_repo_rel_posix(repo, p)
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
        rel = to_repo_rel_posix(repo, p)
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
    preflight = getattr(backend, "_preflight", None)
    if preflight is not None:
        try:
            preflight()
        except BackendUnavailableError as exc:
            console.print(f"[red]{exc}[/red]")
            store.close()
            raise typer.Exit(code=2) from exc
    effective_cap = _resolve_max_cost(max_cost)
    orchestrator = Orchestrator(
        repo_root=repo,
        registry=registry,
        backend=backend,
        store=store,
        changed_files=tuple(changed),
        only=tuple(affected),
        dry_run=dry_run,
        config={"max_howtos": max_howtos},
        max_cost=effective_cap,
        console=console,
    )
    runs = orchestrator.run()
    tracker = orchestrator.tracker
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

    last_ctx_config = getattr(orchestrator, "_last_ctx_config", None) or {}
    orphans = last_ctx_config.get("how_to_orphans") or []
    if orphans:
        console.print("[yellow]Flagged orphans:[/yellow]")
        for o in orphans:
            console.print(f"  • {o}")

    wall = time.monotonic() - start_time
    _render_summary(
        console, tracker, dry_run, effective_cap, len(runs), len(affected), wall
    )

    if not dry_run:
        rs.doc_version = diff.current_head(repo)
        rs.last_run = now
        rs.save(repo)
    store.close()

    if tracker.aborted:
        raise typer.Exit(code=3)


@app.command()
def verify(
    repo: Path = typer.Option(Path.cwd(), "--repo", "-C", help="Repository root."),
    strict: bool = typer.Option(False, "--strict", help="Fail on any finding, even non-blocking."),
    only: list[str] = typer.Option(
        [], "--only", help="Restrict to one or more artifact ids (repeatable)."
    ),
) -> None:
    """Run the deterministic-first verifier pipeline against on-disk artifacts.

    Reads each artifact recorded in ``.docagent/index.db`` (or registered in
    the registry, whichever subset ``--only`` intersects), synthesizes a
    ``DocPatch`` from the current file contents, and runs the default
    pipeline. Exits non-zero when any blocking gate fails, or under
    ``--strict`` when any gate emits any finding.
    """
    from docagent.artifacts.registry import DocPatch, GenerationContext
    from docagent.verify.pipeline import default_pipeline

    console.print(f"[bold]verify[/bold] {repo} (strict={strict})")
    store = open_store(repo)
    registry = _registry()
    pipeline = default_pipeline()
    console.print(f"gates: {[g.name for g in pipeline.gates]}")

    registered = {a.id: a for a in registry.all()}
    # Multi-file artifacts produce N rows per artifact_id; verify each path.
    entries: list[tuple[str, str]] = [
        (row[0], row[1]) for row in store.list_artifacts()
    ]
    on_disk_ids = {aid for aid, _ in entries}

    # Discovery fallback: a fresh CI checkout has ``.docagent/`` gitignored,
    # so the artifacts table is empty. Walk the registry and include any
    # artifact whose declared ``target`` exists as a file on disk. This is
    # what makes the GitHub Action work without a prior ``docagent init``.
    for aid, artifact in registered.items():
        if aid in on_disk_ids:
            continue
        target = getattr(artifact, "target", None)
        if not isinstance(target, Path):
            continue
        abs_target = repo / target
        if abs_target.is_file():
            entries.append((aid, target.as_posix()))
            on_disk_ids.add(aid)

    entries = [(aid, path) for aid, path in entries if aid in registered]
    if only:
        missing = [aid for aid in only if aid not in on_disk_ids]
        for aid in missing:
            console.print(f"[yellow]{aid}[/yellow] not generated yet — run `docagent init`.")
        entries = [(aid, path) for aid, path in entries if aid in only]
    entries.sort()

    if not entries:
        console.print("[dim]no artifacts on disk to verify[/dim]")
        store.close()
        return

    ctx = GenerationContext(repo_root=repo, store=store, backend=None)
    any_failure = False
    any_finding = False

    for aid, rel in entries:
        target = repo / rel
        if not target.is_file():
            console.print(f"[red]FAIL[/red] {aid}  missing on disk: {rel}")
            any_failure = True
            continue
        try:
            content = target.read_bytes()
        except OSError as exc:
            console.print(f"[red]FAIL[/red] {aid}  read error: {exc}")
            any_failure = True
            continue

        artifact = registered[aid]
        patch = DocPatch(
            artifact_id=aid,
            target_path=target,
            new_content=content,
            in_place=False,
            prompt_version=getattr(artifact, "prompt_version", "0"),
        )
        result = pipeline.run(patch, ctx)
        if not result.ok:
            any_failure = True
        if result.findings:
            any_finding = True

        status = "ok" if result.ok else "FAIL"
        color = "green" if result.ok else "red"
        console.print(f"[{color}]{status}[/{color}] {aid}  {rel}")
        for f in result.findings:
            console.print(f"  • {f}")

    store.close()

    if any_failure or (strict and any_finding):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
