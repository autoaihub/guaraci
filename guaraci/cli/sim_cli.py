"""
Guaraci SIM CLI
===============

CLI interface for SIM (Mortality Information System) data operations.
"""

from typing import List, Optional

import click
from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from guaraci.core.config import config
from guaraci.datasus.sim import SimDataSource

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--config-file", type=click.Path(exists=True), help="Custom config file path")
def sim(verbose: bool, config_file: Optional[str]):
    """SIM data operations for Guaraci platform."""
    if verbose:
        logger.remove()
        logger.add(lambda msg: console.print(msg, end=""), level="DEBUG")

    if config_file:
        # Custom config handling could be added here in the future
        console.print(f"[dim]Using custom config file: {config_file}[/dim]")


@sim.command()
@click.argument("start_year", type=int)
@click.argument("end_year", type=int)
@click.option(
    "--groups",
    "-g",
    multiple=True,
    help="SIM groups to download (e.g., CID10 CID9). Default: CID10 only.",
)
@click.option("--states", "-s", multiple=True, help="States (UF codes) to download, e.g. SP RJ")
@click.option("--output-dir", type=click.Path(), help="Output directory")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "parquet", "sqlite"]),
    default="csv",
    help="Output format",
)
@click.option("--uf", help="Filter by state (UF) for exported data")
@click.option("--municipio", "-m", help="Filter by municipality substring")
@click.option("--sexo", type=click.Choice(["M", "F"]), help="Filter by sex")
@click.option("--causa-basica", "-c", help="Filter by basic cause of death (CAUSABAS)")
@click.option("--ano-obito", "-a", type=int, help="Filter by year of death")
def download(
    start_year: int,
    end_year: int,
    groups: tuple,
    states: tuple,
    output_dir: Optional[str],
    output_format: str,
    uf: Optional[str],
    municipio: Optional[str],
    sexo: Optional[str],
    causa_basica: Optional[str],
    ano_obito: Optional[int],
):
    """Download SIM data for specified years, groups and states."""
    console.print("[bold blue]Guaraci SIM Downloader[/bold blue]")
    console.print(f"Years: {start_year}-{end_year}")

    try:
        sim_ds = SimDataSource(output_path=output_dir or str(config.get_datasus_path("sim")))
        group_list: List[str] = list(groups) if groups else sim_ds.DEFAULT_GROUPS.copy()
        state_list: Optional[List[str]] = list(states) if states else None

        progress_state = {"task": None}

        def progress_callback(completed: int, total: int) -> None:
            if total <= 0:
                return
            if progress_state["task"] is None:
                progress_state["task"] = progress.add_task(
                    "Downloading SIM data...",
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
            download_info = sim_ds.download(
                start_year,
                end_year,
                groups=group_list,
                states=state_list,
                progress_callback=progress_callback,
            )

        if download_info["total_files"] == 0:
            console.print("[yellow]No SIM files available for the requested parameters.[/yellow]")
            return

        if download_info["failed_downloads"]:
            console.print(
                f"[yellow]WARNING: {len(download_info['failed_downloads'])} files failed during download[/yellow]"
            )

        console.print("[blue]Processing and exporting SIM data...[/blue]")

        for group in group_list:
            try:
                df = sim_ds.load_dataframe(group)

                filters_provided = any([uf, municipio, sexo, causa_basica, ano_obito])

                if filters_provided:
                    df = sim_ds.filter(
                        df,
                        uf=uf,
                        municipio=municipio,
                        sexo=sexo,
                        causa_basica=causa_basica,
                        ano_obito=ano_obito,
                    )

                if len(df) == 0:
                    console.print(f"[yellow]WARNING {group}: No data found[/yellow]")
                    continue

                output_name = f"{group}_{start_year}_{end_year}"
                exported_path = sim_ds.export(df, format=output_format, name=output_name)

                if exported_path:
                    console.print(
                        f"[green]SUCCESS {group}: {len(df)} records exported to "
                        f"{exported_path.name}[/green]"
                    )
                else:
                    console.print(f"[yellow]WARNING {group}: Export skipped (no data).[/yellow]")

            except Exception as exc:  # pragma: no cover - CLI/runtime only
                console.print(f"[red]ERROR {group}: Failed to process - {exc}[/red]")

        console.print("[green]SUCCESS SIM download and export completed![/green]")

    except Exception as exc:
        logger.error(f"SIM download failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@sim.command()
@click.argument("group")
@click.option("--uf", help="Filter by state (UF)")
@click.option("--sexo", type=click.Choice(["M", "F"]), help="Filter by sex")
@click.option("--ano-obito", type=int, help="Filter by year of death")
@click.option("--municipio", help="Filter by municipality")
@click.option("--causa-basica", help="Filter by basic cause of death (CAUSABAS)")
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
    ano_obito: Optional[int],
    municipio: Optional[str],
    causa_basica: Optional[str],
    output: Optional[str],
    output_format: str,
):
    """Filter SIM data with specified criteria."""
    console.print(f"[bold blue]Filtering SIM {group} data[/bold blue]")

    try:
        sim_ds = SimDataSource()

        with Progress(SpinnerColumn(), TextColumn("Loading data..."), console=console) as progress:
            task = progress.add_task("Loading...", total=None)
            df = sim_ds.load_dataframe(group)
            progress.update(task, completed=True)

        console.print(f"Loaded {len(df)} records")

        filtered_df = sim_ds.filter(
            df,
            uf=uf,
            municipio=municipio,
            sexo=sexo,
            causa_basica=causa_basica,
            ano_obito=ano_obito,
        )

        console.print(f"Filtered to {len(filtered_df)} records")

        output_name = output or f"{group}_filtered"
        sim_ds.export(filtered_df, format=output_format, name=output_name)

        console.print(f"[green]SUCCESS Results exported as {output_name}.{output_format}[/green]")

    except Exception as exc:
        logger.error(f"SIM filtering failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@sim.command()
@click.argument("group")
@click.option("--by", "group_by", default="CAUSABAS", help="Group by column")
@click.option(
    "--metric",
    type=click.Choice(["count", "mean", "sum"]),
    default="count",
    help="Summary metric",
)
def summary(group: str, group_by: str, metric: str):
    """Generate summary statistics for SIM data."""
    console.print(f"[bold blue]SIM Summary for {group}[/bold blue]")

    try:
        sim_ds = SimDataSource()
        df = sim_ds.load_dataframe(group)

        summary_df = sim_ds.summary(df, by=group_by, metric=metric)

        table = Table(title=f"SIM {group} Summary by {group_by}")

        for col in summary_df.columns:
            table.add_column(col, style="cyan")

        for row in summary_df.iter_rows():
            table.add_row(*[str(val) for val in row])

        console.print(table)

    except Exception as exc:
        logger.error(f"SIM summary failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@sim.command()
@click.argument("group")
def info(group: str):
    """Show information about available fields for a SIM group."""
    try:
        sim_ds = SimDataSource()
        fields = sim_ds.describe_fields(group)

        console.print(f"[bold blue]Available SIM fields for {group}:[/bold blue]")

        table = Table()
        table.add_column("Field Name", style="cyan")

        for field in fields:
            table.add_row(field)

        console.print(table)

    except Exception as exc:
        logger.error(f"SIM info retrieval failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


if __name__ == "__main__":  # pragma: no cover
    sim()

