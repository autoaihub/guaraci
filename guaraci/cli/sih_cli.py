"""
Guaraci SIH CLI
===============

CLI interface for SIH (Hospital Information System) data operations.
"""

from typing import List, Optional

import click
from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from guaraci.core.config import config
from guaraci.datasus.sih import SihDataSource

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--config-file", type=click.Path(exists=True), help="Custom config file path")
def sih(verbose: bool, config_file: Optional[str]):
    """SIH data operations for Guaraci platform."""
    if verbose:
        logger.remove()
        logger.add(lambda msg: console.print(msg, end=""), level="DEBUG")

    if config_file:
        console.print(f"[dim]Using custom config file: {config_file}[/dim]")


@sih.command()
@click.argument("start_year", type=int)
@click.argument("end_year", type=int)
@click.option(
    "--groups",
    "-g",
    multiple=True,
    help="SIH groups to download (e.g., RD RJ SP). Default: RD only.",
)
@click.option("--states", "-s", multiple=True, help="States (UF codes) to download, e.g. SP RJ")
@click.option(
    "--months",
    "-m",
    multiple=True,
    type=int,
    help="Months to download (1-12). If omitted, all months are used.",
)
@click.option("--output-dir", type=click.Path(), help="Output directory")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "parquet", "sqlite"]),
    default="csv",
    help="Output format",
)
@click.option("--uf", help="Filter by state (UF) for exported data")
@click.option("--municipio", help="Filter by municipality substring")
@click.option("--sexo", type=click.Choice(["M", "F"]), help="Filter by sex")
@click.option("--ano", type=int, help="Filter by year (e.g., ANO_CMPT)")
@click.option("--mes", type=int, help="Filter by month (1-12)")
def download(
    start_year: int,
    end_year: int,
    groups: tuple,
    states: tuple,
    months: tuple,
    output_dir: Optional[str],
    output_format: str,
    uf: Optional[str],
    municipio: Optional[str],
    sexo: Optional[str],
    ano: Optional[int],
    mes: Optional[int],
):
    """Download SIH data for specified years, groups, states and months."""
    console.print("[bold blue]Guaraci SIH Downloader[/bold blue]")
    console.print(f"Years: {start_year}-{end_year}")

    try:
        sih_ds = SihDataSource(output_path=output_dir or str(config.get_datasus_path("sih")))
        group_list: List[str] = list(groups) if groups else sih_ds.DEFAULT_GROUPS.copy()
        state_list: Optional[List[str]] = list(states) if states else None
        month_list: Optional[List[int]] = list(months) if months else None

        progress_state = {"task": None}

        def progress_callback(completed: int, total: int) -> None:
            if total <= 0:
                return
            if progress_state["task"] is None:
                progress_state["task"] = progress.add_task(
                    "Downloading SIH data...",
                    total=total,
                )
            progress.update(progress_state["task"], completed=completed)

        with Progress(
            SpinnerColumn(),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total} files"),
            console=console,
            transient=True,
        ) as progress:
            download_info = sih_ds.download(
                start_year,
                end_year,
                groups=group_list,
                states=state_list,
                months=month_list,
                progress_callback=progress_callback,
            )

        if download_info["total_files"] == 0:
            console.print("[yellow]No SIH files available for the requested parameters.[/yellow]")
            return

        if download_info["failed_downloads"]:
            console.print(
                f"[yellow]WARNING: {len(download_info['failed_downloads'])} files failed during download[/yellow]"
            )

        console.print("[blue]Processing and exporting SIH data...[/blue]")

        for group in group_list:
            try:
                df = sih_ds.load_dataframe(group)

                filters_provided = any([uf, municipio, sexo, ano, mes])

                if filters_provided:
                    df = sih_ds.filter(
                        df,
                        uf=uf,
                        municipio=municipio,
                        sexo=sexo,
                        ano=ano,
                        mes=mes,
                    )

                if len(df) == 0:
                    console.print(f"[yellow]WARNING {group}: No data found[/yellow]")
                    continue

                output_name = f"{group}_{start_year}_{end_year}"
                exported_path = sih_ds.export(df, format=output_format, name=output_name)

                if exported_path:
                    console.print(
                        f"[green]SUCCESS {group}: {len(df)} records exported to "
                        f"{exported_path.name}[/green]"
                    )
                else:
                    console.print(f"[yellow]WARNING {group}: Export skipped (no data).[/yellow]")

            except Exception as exc:  # pragma: no cover - CLI/runtime only
                console.print(f"[red]ERROR {group}: Failed to process - {exc}[/red]")

        console.print("[green]SUCCESS SIH download and export completed![/green]")

    except Exception as exc:
        logger.error(f"SIH download failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@sih.command()
@click.argument("group")
@click.option("--uf", help="Filter by state (UF)")
@click.option("--sexo", type=click.Choice(["M", "F"]), help="Filter by sex")
@click.option("--ano", type=int, help="Filter by year (e.g., ANO_CMPT)")
@click.option("--mes", type=int, help="Filter by month (1-12)")
@click.option("--municipio", help="Filter by municipality")
@click.option("--output", "-o", help="Output file name")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "parquet", "sqlite"]),
    default="csv",
    help="Output format",
)
def filter(
    group: str,
    uf: Optional[str],
    sexo: Optional[str],
    ano: Optional[int],
    mes: Optional[int],
    municipio: Optional[str],
    output: Optional[str],
    output_format: str,
):
    """Filter SIH data with specified criteria."""
    console.print(f"[bold blue]Filtering SIH {group} data[/bold blue]")

    try:
        sih_ds = SihDataSource()

        with Progress(SpinnerColumn(), TextColumn("Loading data..."), console=console) as progress:
            task = progress.add_task("Loading...", total=None)
            df = sih_ds.load_dataframe(group)
            progress.update(task, completed=True)

        console.print(f"Loaded {len(df)} records")

        filtered_df = sih_ds.filter(
            df,
            uf=uf,
            municipio=municipio,
            sexo=sexo,
            ano=ano,
            mes=mes,
        )

        console.print(f"Filtered to {len(filtered_df)} records")

        output_name = output or f"{group}_filtered"
        sih_ds.export(filtered_df, format=output_format, name=output_name)

        console.print(f"[green]SUCCESS Results exported as {output_name}.{output_format}[/green]")

    except Exception as exc:
        logger.error(f"SIH filtering failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@sih.command()
@click.argument("group")
@click.option("--by", "group_by", default="UF_ZI", help="Group by column")
@click.option(
    "--metric",
    type=click.Choice(["count", "mean", "sum"]),
    default="count",
    help="Summary metric",
)
def summary(group: str, group_by: str, metric: str):
    """Generate summary statistics for SIH data."""
    console.print(f"[bold blue]SIH Summary for {group}[/bold blue]")

    try:
        sih_ds = SihDataSource()
        df = sih_ds.load_dataframe(group)

        summary_df = sih_ds.summary(df, by=group_by, metric=metric)

        table = Table(title=f"SIH {group} Summary by {group_by}")

        for col in summary_df.columns:
            table.add_column(col, style="cyan")

        for row in summary_df.iter_rows():
            table.add_row(*[str(val) for val in row])

        console.print(table)

    except Exception as exc:
        logger.error(f"SIH summary failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@sih.command()
@click.argument("group")
def info(group: str):
    """Show information about available fields for a SIH group."""
    try:
        sih_ds = SihDataSource()
        fields = sih_ds.describe_fields(group)

        console.print(f"[bold blue]Available SIH fields for {group}:[/bold blue]")

        table = Table()
        table.add_column("Field Name", style="cyan")

        for field in fields:
            table.add_row(field)

        console.print(table)

    except Exception as exc:
        logger.error(f"SIH info retrieval failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


if __name__ == "__main__":  # pragma: no cover
    sih()

