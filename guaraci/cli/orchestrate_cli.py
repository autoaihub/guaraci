"""``guaraci orchestrate`` — sweep every source into the bronze tree.

Commands::

    guaraci orchestrate profiles                 # resolved cadence/kind per source (offline)
    guaraci orchestrate plan   [--update]        # dry-run: what WOULD be fetched
    guaraci orchestrate backfill [--source sih]  # full history ("sair tudo")
    guaraci orchestrate update  [--source sih]   # incremental delta (ledger-driven)
    guaraci orchestrate status                   # read the ledger: what exists

The bronze root comes from ``--bronze-root``/``-o`` or ``GUARACI_BRONZE_ROOT``
(default ``./bronze``). ``plan``/``backfill``/``update`` contact the DATASUS FTP
server; ``profiles`` and ``status`` are offline.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from guaraci.orchestrator import Ledger, Orchestrator
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.ledger import STATUS_OK, STATUS_PLANNED

console = Console()


def _bronze_root(opt: Optional[str]) -> Path:
    root = opt or os.environ.get("GUARACI_BRONZE_ROOT") or "./bronze"
    return Path(root).expanduser()


def _sources_opt(source: Tuple[str, ...]) -> Optional[list]:
    return [s for s in source] if source else None


def _tiers(value: str) -> Tuple[str, ...]:
    return {"raw": ("raw",), "refined": ("refined",), "both": ("raw", "refined")}[value]


_tier_option = click.option(
    "--tier",
    type=click.Choice(["raw", "refined", "both"]),
    default="both",
    help="Bronze tier(s) to write: raw (as-is), refined (month-partitioned), or both.",
)


_source_option = click.option(
    "--source",
    "-s",
    multiple=True,
    help="Restrict to these source(s); repeatable. Omit to sweep all.",
)
_root_option = click.option(
    "--bronze-root",
    "-o",
    "bronze_root",
    default=None,
    help="Bronze output root (default: $GUARACI_BRONZE_ROOT or ./bronze).",
)


@click.group()
def orchestrate() -> None:
    """Sweep Guaraci sources into a browsable bronze tree with a CSV ledger."""


@orchestrate.command(name="profiles")
@_source_option
def profiles_cmd(source: Tuple[str, ...]) -> None:
    """Show each source's resolved profile (kind, cadence, backfill floor)."""
    orch = Orchestrator(bronze_root=_bronze_root(None))
    table = Table(title="Orchestrator source profiles")
    for col in ("source", "kind", "cadence", "min_year", "auto", "note"):
        table.add_column(col, overflow="fold")
    for profile in sorted(orch.profiles(_sources_opt(source)), key=lambda p: p.source):
        table.add_row(
            profile.source,
            profile.kind.value,
            profile.cadence.value,
            "" if profile.min_year is None else str(profile.min_year),
            "yes" if profile.auto else "no",
            profile.note,
        )
    console.print(table)


def _print_report(report, *, dry_run: bool) -> None:
    table = Table(
        title=f"{report.mode} [{report.run_id}]" + (" - DRY RUN" if dry_run else "")
    )
    for col in ("source", "ok", "skipped", "empty", "error", "planned"):
        table.add_column(col, overflow="fold")
    for src in sorted(report.by_source):
        counts = report.by_source[src]
        table.add_row(
            src,
            str(counts.get("ok", 0)),
            str(counts.get("skipped", 0)),
            str(counts.get("empty", 0)),
            str(counts.get("error", 0)),
            str(counts.get("planned", 0)),
        )
    console.print(table)

    totals = report.totals
    console.print(
        "[bold]totals[/bold]: "
        + ", ".join(f"{k}={v}" for k, v in sorted(totals.items()))
        + f"  ([cyan]{sum(totals.values())}[/cyan] units)"
    )
    for skipped in report.skipped_sources:
        console.print(f"[dim]skip {skipped['source']}: {skipped['reason']}[/dim]")
    for err in report.source_errors:
        console.print(f"[red]plan error {err['source']}: {err['error']}[/red]")


def _progress(profile, rows) -> None:
    counts = Counter(r.status for r in rows)
    console.print(
        f"  [green]{profile.source}[/green] "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )


@orchestrate.command(name="plan")
@_source_option
@_root_option
@click.option("--update", "as_update", is_flag=True, help="Plan the delta instead of the full backfill.")
@click.option("--limit", default=20, help="Max sample units to list (0 = none).")
def plan_cmd(source: Tuple[str, ...], bronze_root: Optional[str], as_update: bool, limit: int) -> None:
    """Dry-run: contact the source and list what WOULD be fetched (no download)."""
    orch = Orchestrator(bronze_root=_bronze_root(bronze_root))
    sources = _sources_opt(source)
    console.print("[dim]discovering (no download)...[/dim]")
    report = (orch.update if as_update else orch.backfill)(
        sources, dry_run=True, progress=_progress
    )
    _print_report(report, dry_run=True)
    planned = [r for r in report.rows if r.status == STATUS_PLANNED]
    if limit and planned:
        console.print(f"[bold]sample ({min(limit, len(planned))} of {len(planned)}):[/bold]")
        for row in planned[:limit]:
            console.print(f"  {row.out_path or row.partition_key}")


@orchestrate.command(name="backfill")
@_source_option
@_root_option
@_tier_option
@click.option("--dry-run", is_flag=True, help="Plan only; do not download.")
def backfill_cmd(source: Tuple[str, ...], bronze_root: Optional[str], tier: str, dry_run: bool) -> None:
    """Full-history sweep ("sair tudo") into the bronze tree."""
    root = _bronze_root(bronze_root)
    console.print(f"[bold]bronze root:[/bold] {root}  [dim]tier={tier}[/dim]")
    orch = Orchestrator(bronze_root=root, tiers=_tiers(tier))
    report = orch.backfill(_sources_opt(source), dry_run=dry_run, progress=_progress)
    _print_report(report, dry_run=dry_run)


@orchestrate.command(name="update")
@_source_option
@_root_option
@_tier_option
@click.option("--dry-run", is_flag=True, help="Plan only; do not download.")
def update_cmd(source: Tuple[str, ...], bronze_root: Optional[str], tier: str, dry_run: bool) -> None:
    """Incremental sweep: pull only the delta the ledger doesn't have yet."""
    root = _bronze_root(bronze_root)
    console.print(f"[bold]bronze root:[/bold] {root}  [dim]tier={tier}[/dim]")
    orch = Orchestrator(bronze_root=root, tiers=_tiers(tier))
    report = orch.update(_sources_opt(source), dry_run=dry_run, progress=_progress)
    _print_report(report, dry_run=dry_run)


@orchestrate.command(name="status")
@_source_option
@_root_option
def status_cmd(source: Tuple[str, ...], bronze_root: Optional[str]) -> None:
    """Read the ledger: materialised partitions per source and last activity."""
    root = _bronze_root(bronze_root)
    ledger = Ledger(root / "_ledger.csv")
    all_rows = ledger.read_all()
    if not all_rows:
        console.print(f"[yellow]no ledger yet[/yellow] at {ledger.path}")
        return
    wanted = {s.strip().lower() for s in source} if source else None

    per_source: dict = {}
    for row in all_rows:
        if wanted and row.source not in wanted:
            continue
        agg = per_source.setdefault(row.source, {"counts": Counter(), "last": ""})
        agg["counts"][row.status] += 1
        if row.ts_utc > agg["last"]:
            agg["last"] = row.ts_utc

    table = Table(title=f"Bronze ledger — {ledger.path}")
    for col in ("source", "ok", "other", "last_run_utc"):
        table.add_column(col, overflow="fold")
    grand = Counter()
    for src in sorted(per_source):
        counts = per_source[src]["counts"]
        grand.update(counts)
        other = sum(v for k, v in counts.items() if k != STATUS_OK)
        table.add_row(src, str(counts.get(STATUS_OK, 0)), str(other), per_source[src]["last"])
    console.print(table)
    console.print(
        f"[bold]total rows:[/bold] {len(all_rows)}  "
        f"[bold]ok:[/bold] {grand.get(STATUS_OK, 0)}"
    )


if __name__ == "__main__":
    orchestrate()
