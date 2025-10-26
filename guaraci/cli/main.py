"""
Guaraci Main CLI
===============

Main command-line interface for the Guaraci platform.
"""

import click
from rich.console import Console
from guaraci.cli.sinan_cli import sinan
from guaraci import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="Guaraci")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
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


@app.command()
def info():
    """Show platform information and available data sources."""
    console.print(f"[bold blue]Guaraci v{__version__}[/bold blue]")
    console.print("Brazilian Public Data Integration Platform")
    console.print()
    console.print("[bold]Available Data Sources:[/bold]")
    console.print("• [cyan]sinan[/cyan] - DATASUS notification system (health surveillance)")
    console.print()
    console.print("[bold]Quick Start:[/bold]")
    console.print("  guaraci sinan download 2020 2022 --diseases DENG ZIKA")
    console.print("  guaraci sinan filter DENG --uf SP --sexo M")
    console.print("  guaraci sinan summary DENG --by UF")
    console.print()
    console.print("[dim]For more help: guaraci --help or guaraci sinan --help[/dim]")


if __name__ == "__main__":
    app()