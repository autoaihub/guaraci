"""
Guaraci Main CLI
===============

Main command-line interface for the Guaraci platform.
"""

import click
from rich.console import Console

from guaraci import __version__
from guaraci.cli.sinan_cli import sinan
from guaraci.cli.sim_cli import sim
from guaraci.cli.sih_cli import sih
from guaraci.cli.snis_cli import snis
from guaraci.cli.datasus_cli import datasus
from guaraci.cli.fetch_cli import fetch

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="Guaraci")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def app(verbose: bool):
    """
    🇧🇷 Guaraci - Brazilian Public Data Integration Platform

    A comprehensive toolkit for accessing, integrating, and analyzing
    Brazilian public data with focus on health and epidemiology.
    """
    if verbose:
        console.print(f"[dim]Guaraci v{__version__} - Verbose mode enabled[/dim]")


# Add subcommands
app.add_command(sinan)
app.add_command(sim)
app.add_command(sih)
app.add_command(snis)
app.add_command(datasus)
app.add_command(fetch)


@app.command()
def info():
    """Show platform information and available data sources."""
    console.print(f"[bold blue]Guaraci v{__version__}[/bold blue]")
    console.print("Brazilian Public Data Integration Platform")
    console.print()
    console.print("[bold]Available Data Sources:[/bold]")
    console.print("• [cyan]sinan[/cyan] - DATASUS notification system (health surveillance)")
    console.print("• [cyan]sim[/cyan]   - DATASUS mortality information system (SIM)")
    console.print("• [cyan]sih[/cyan]   - DATASUS hospital information system (SIH/SUS)")
    console.print("• [cyan]snis[/cyan]  - SNIS legado (BigQuery) e SINISA cru (gov.br)")
    console.print("• [cyan]datasus[/cyan] - 11 sistemas DATASUS via FTP direto (SINASC, SIA, CNES, PNI, …)")
    console.print("• [cyan]fetch[/cyan]  - busca genérica schema-driven de QUALQUER fonte (OpenDataSUS, NASA, …)")
    console.print("• [cyan]api[/cyan]   - HTTP API (FastAPI) em guaraci.api.main:app")
    console.print()
    console.print("[bold]Quick Start:[/bold]")
    console.print("  guaraci sinan download 2020 2022 --diseases DENG ZIKA")
    console.print("  guaraci sim download 2015 2020 --groups CID10 --states SP RJ")
    console.print("  guaraci sih download 2019 2020 --groups RD --states SP --months 1 2 3")
    console.print("  guaraci fetch run srag_demas --set start_year=2023 --set end_year=2023 --set uf=SP --format parquet -o ./out")
    console.print("  guaraci sinan filter DENG --uf SP --sexo M")
    console.print("  guaraci sim summary CID10 --by CAUSABAS")
    console.print("  guaraci sih summary RD --by UF_ZI")
    console.print()
    console.print(
        "[dim]For more help: guaraci --help, guaraci sinan --help, "
        "guaraci sim --help or guaraci sih --help[/dim]"
    )


if __name__ == "__main__":
    app()
