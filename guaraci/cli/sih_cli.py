"""
Guaraci SIH CLI
===============

CLI interface for SIH (Hospital Information System) data operations.
"""

from typing import List, Optional

import click
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from guaraci.cli._common import (
    current_verbose,
    download_progress,
    format_option,
    json_option,
    output_dir_option,
    print_json,
    raise_cli_error,
    resolve_verbose,
    states_option,
)
from guaraci.core.config import config
from guaraci.core.results import JobResult
from guaraci.datasus.sih import SihDataSource

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def sih(ctx: click.Context, verbose: bool):
    """SIH data operations for Guaraci platform."""
    if resolve_verbose(ctx, verbose):
        logger.remove()
        logger.add(lambda msg: console.print(msg, end=""), level="DEBUG")


@sih.command()
@click.argument("start_year", type=int)
@click.argument("end_year", type=int)
@click.option(
    "--groups",
    "-g",
    multiple=True,
    help="SIH groups to download (e.g., RD RJ SP). Default: RD only.",
)
@states_option
@click.option(
    "--months",
    "-m",
    multiple=True,
    type=int,
    help="Months to download (1-12). If omitted, all months are used.",
)
@output_dir_option
@format_option
@click.option("--uf", help="Filter by state (UF) for exported data")
@click.option("--municipio", help="Filter by municipality substring")
@click.option("--sexo", type=click.Choice(["M", "F"]), help="Filter by sex")
@click.option("--ano", type=int, help="Filter by year (e.g., ANO_CMPT)")
@click.option("--mes", type=int, help="Filter by month (1-12)")
@json_option
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
    as_json: bool,
):
    """Download SIH data for specified years, groups, states and months."""
    verbose = current_verbose()
    if not as_json:
        console.print("[bold blue]Guaraci SIH Downloader[/bold blue]")
        console.print(f"Years: {start_year}-{end_year}")

    try:
        sih_ds = SihDataSource(output_path=output_dir or str(config.get_datasus_path("sih")))
        group_list: List[str] = list(groups) if groups else sih_ds.DEFAULT_GROUPS.copy()
        state_list: Optional[List[str]] = list(states) if states else None
        month_list: Optional[List[int]] = list(months) if months else None

        download_kwargs = dict(
            groups=group_list,
            states=state_list,
            months=month_list,
        )
        if as_json:
            download_info = sih_ds.download(start_year, end_year, **download_kwargs)
        else:
            with download_progress(console, "Downloading SIH data...") as progress_callback:
                download_info = sih_ds.download(
                    start_year,
                    end_year,
                    progress_callback=progress_callback,
                    **download_kwargs,
                )

        if download_info["total_files"] == 0:
            if as_json:
                print_json(JobResult.from_payload(source="sih", payload=download_info))
            else:
                console.print(
                    "[yellow]No SIH files available for the requested parameters.[/yellow]"
                )
            return

        if download_info["failed_downloads"] and not as_json:
            console.print(
                f"[yellow]WARNING: {len(download_info['failed_downloads'])} files failed during download[/yellow]"
            )

        if not as_json:
            console.print("[blue]Processing and exporting SIH data...[/blue]")

        exported_files: List[str] = []
        failed_groups: List[str] = []
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
                    if not as_json:
                        console.print(f"[yellow]WARNING {group}: No data found[/yellow]")
                    continue

                output_name = f"{group}_{start_year}_{end_year}"
                exported_path = sih_ds.export(df, format=output_format, name=output_name)

                if exported_path:
                    exported_files.append(str(exported_path))
                    if not as_json:
                        console.print(
                            f"[green]SUCCESS {group}: {len(df)} records exported to "
                            f"{exported_path.name}[/green]"
                        )
                elif not as_json:
                    console.print(f"[yellow]WARNING {group}: Export skipped (no data).[/yellow]")

            except Exception as exc:  # pragma: no cover - CLI/runtime only
                failed_groups.append(group)
                if not as_json:
                    console.print(f"[red]ERROR {group}: Failed to process - {exc}[/red]")

        if as_json:
            print_json(
                JobResult.from_payload(
                    source="sih",
                    payload={
                        **dict(download_info),
                        "exported_files": exported_files,
                        "failed_groups": failed_groups,
                    },
                )
            )
        elif not failed_groups:
            console.print("[green]SUCCESS SIH download and export completed![/green]")

        if failed_groups:
            raise click.ClickException(
                f"{len(failed_groups)} group(s) failed during processing: "
                f"{', '.join(failed_groups)}"
            )

    except click.ClickException:
        raise
    except Exception as exc:
        logger.error(f"SIH download failed: {exc}")
        raise_cli_error(exc, verbose)


@sih.command("filter")
@click.argument("group")
@click.option("--uf", help="Filter by state (UF)")
@click.option("--sexo", type=click.Choice(["M", "F"]), help="Filter by sex")
@click.option("--ano", type=int, help="Filter by year (e.g., ANO_CMPT)")
@click.option("--mes", type=int, help="Filter by month (1-12)")
@click.option("--municipio", help="Filter by municipality")
@click.option("--output", "-o", help="Output file name")
@format_option
def filter_cmd(
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
        raise_cli_error(exc, current_verbose())


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
        raise_cli_error(exc, current_verbose())


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
        raise_cli_error(exc, current_verbose())


if __name__ == "__main__":  # pragma: no cover
    sih()
