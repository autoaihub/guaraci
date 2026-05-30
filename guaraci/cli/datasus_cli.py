"""Generic CLI for the phase-5 direct-FTP DATASUS systems.

SIH/SIM/SINAN keep their dedicated CLIs; the eleven systems added in
phase 5 (SINASC, SIA, CNES, PNI, CIHA, CIH, SISCAN, SISPRENATAL, RESP,
PCE, painel de oncologia) share one spec-driven command group instead of
eleven near-identical modules. Collection runs through the same
``DownloadService`` the API/jobs use, so behaviour matches exactly.
"""

from __future__ import annotations

from typing import Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from guaraci.datasus.ftp import specs

console = Console()


@click.group()
def datasus() -> None:
    """DATASUS direct-FTP systems (SINASC, SIA, CNES, PNI, …)."""


@datasus.command(name="list")
def list_sources() -> None:
    """List the available direct-FTP DATASUS systems."""
    table = Table(title="DATASUS FTP systems (phase 5)")
    table.add_column("source", style="cyan")
    table.add_column("title")
    table.add_column("groups", style="dim")
    table.add_column("state?", justify="center")
    table.add_column("since", justify="right")
    for spec in specs.ALL_SPECS:
        groups = ", ".join(spec.groups) if spec.groups else "—"
        table.add_row(
            spec.name,
            spec.title,
            groups,
            "yes" if spec.has_state else "no",
            str(spec.min_year),
        )
    console.print(table)


@datasus.command()
@click.argument("source")
@click.argument("start_year", type=int)
@click.argument("end_year", type=int)
@click.option("--groups", "-g", multiple=True, help="Group codes (only for multi-group systems).")
@click.option("--states", "-s", multiple=True, help="UF filter (only for state-level systems).")
@click.option("--format", "output_format", default=None, help="Export format: csv, parquet, or sqlite.")
@click.option("--output-dir", "-o", default=None, help="Output directory.")
def download(
    source: str,
    start_year: int,
    end_year: int,
    groups: Tuple[str, ...],
    states: Tuple[str, ...],
    output_format: Optional[str],
    output_dir: Optional[str],
) -> None:
    """Download a SOURCE window, e.g. ``guaraci datasus download sinasc 2018 2020``."""
    # Import here so `guaraci datasus list` stays fast and import-light.
    from guaraci.services.downloads import DownloadService

    if source.strip().lower() not in specs.SPECS:
        raise click.BadParameter(
            f"Unknown source '{source}'. Known: {', '.join(sorted(specs.SPECS))}"
        )

    kwargs: dict = {"start_year": start_year, "end_year": end_year}
    if groups:
        kwargs["groups"] = list(groups)
    if states:
        kwargs["states"] = list(states)
    if output_format:
        kwargs["output_format"] = output_format
    if output_dir:
        kwargs["output_dir"] = output_dir

    console.print(f"[bold]Downloading {source}[/bold] {start_year}-{end_year} …")
    result = DownloadService().run(source.strip().lower(), **kwargs)
    payload = getattr(result, "payload", result)
    console.print(payload)


@datasus.command()
@click.argument("source")
@click.argument("start_year", type=int)
@click.argument("end_year", type=int)
@click.option("--groups", "-g", multiple=True, help="Group codes (only for multi-group systems).")
@click.option("--states", "-s", multiple=True, help="UF filter (only for state-level systems).")
def discover(
    source: str,
    start_year: int,
    end_year: int,
    groups: Tuple[str, ...],
    states: Tuple[str, ...],
) -> None:
    """Preflight a SOURCE window: count files per group/UF, no download."""
    from guaraci.services.downloads import DownloadService

    if source.strip().lower() not in specs.SPECS:
        raise click.BadParameter(
            f"Unknown source '{source}'. Known: {', '.join(sorted(specs.SPECS))}"
        )

    kwargs: dict = {"start_year": start_year, "end_year": end_year}
    if groups:
        kwargs["groups"] = list(groups)
    if states:
        kwargs["states"] = list(states)

    summary = DownloadService().discover(source.strip().lower(), **kwargs)
    console.print(
        f"[bold]{source}[/bold] {start_year}-{end_year}: "
        f"[cyan]{summary.get('documents_found', 0)}[/cyan] files"
    )
    if summary.get("by_group"):
        console.print(f"  by group: {summary['by_group']}")
    if summary.get("by_state"):
        console.print(f"  by state: {summary['by_state']}")


if __name__ == "__main__":
    datasus()
