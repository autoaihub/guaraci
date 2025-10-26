"""
Guaraci SINAN CLI
================

Modern CLI interface for SINAN data operations using Click and Rich.
"""

from typing import Optional, List
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from loguru import logger

from guaraci.datasus.sinan import SinanDataSource
from guaraci.core.config import config

console = Console()


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--config-file', type=click.Path(exists=True), help='Custom config file path')
def sinan(verbose: bool, config_file: Optional[str]):
    """SINAN data operations for Guaraci platform."""
    if verbose:
        logger.remove()
        logger.add(lambda msg: console.print(msg, end=""), level="DEBUG")
    
    if config_file:
        # Load custom config if provided
        pass


@sinan.command()
@click.argument('start_year', type=int)
@click.argument('end_year', type=int)
@click.option('--diseases', '-d', multiple=True, help='Disease codes (e.g., DENG ZIKA)')
@click.option('--output-dir', type=click.Path(), help='Output directory')
@click.option('--format', 'output_format', type=click.Choice(['csv', 'parquet', 'sqlite']), 
              default='csv', help='Output format')
@click.option('--force', is_flag=True, help='Force re-download existing data')
def download(start_year: int, end_year: int, diseases: tuple, output_dir: Optional[str], 
             output_format: str, force: bool):
    """Download SINAN data for specified years and diseases."""
    
    console.print(f"[bold blue]Guaraci SINAN Downloader[/bold blue]")
    console.print(f"Years: {start_year}-{end_year}")
    
    # Convert diseases tuple to list, use defaults if empty
    disease_list = list(diseases) if diseases else None
    
    try:
        # Initialize data source
        sinan_ds = SinanDataSource(output_path=output_dir or str(config.get_datasus_path("sinan")))
        
        # Download data with progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Downloading SINAN data...", total=None)
            sinan_ds.download(start_year, end_year, disease_list)
            progress.update(task, completed=True)
        
        # Process and export the downloaded data
        console.print("[blue]📊 Processing and exporting data...[/blue]")
        
        for disease in disease_list:
            try:
                # Load the downloaded data
                df = sinan_ds.load_dataframe(disease)
                
                if len(df) > 0:
                    # Export the data
                    output_name = f"{disease}_{start_year}_{end_year}"
                    sinan_ds.export(df, format=output_format, name=output_name)
                    console.print(f"[green]✅ {disease}: {len(df)} records exported as {output_name}.{output_format}[/green]")
                else:
                    console.print(f"[yellow]⚠️ {disease}: No data found[/yellow]")
                    
            except Exception as e:
                console.print(f"[red]❌ {disease}: Failed to process - {e}[/red]")
        
        console.print("[green]✅ Download and export completed successfully![/green]")
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        console.print(f"[red]❌ Error: {e}[/red]")
        raise click.Abort()


@sinan.command()
@click.argument('disease')
@click.option('--uf', help='Filter by state (UF)')
@click.option('--sexo', type=click.Choice(['M', 'F']), help='Filter by sex')
@click.option('--ano', type=int, help='Filter by year')
@click.option('--municipio', help='Filter by municipality')
@click.option('--evolucao', help='Filter by case evolution')
@click.option('--classificacao', help='Filter by classification')
@click.option('--output', '-o', help='Output file name')
@click.option('--format', 'output_format', type=click.Choice(['csv', 'parquet', 'sqlite']), 
              default='csv', help='Output format')
def filter(disease: str, uf: Optional[str], sexo: Optional[str], ano: Optional[int],
           municipio: Optional[str], evolucao: Optional[str], classificacao: Optional[str],
           output: Optional[str], output_format: str):
    """Filter SINAN data with specified criteria."""
    
    console.print(f"[bold blue]Filtering {disease} data[/bold blue]")
    
    try:
        sinan_ds = SinanDataSource()
        
        # Load dataframe
        with Progress(SpinnerColumn(), TextColumn("Loading data..."), console=console) as progress:
            task = progress.add_task("Loading...", total=None)
            df = sinan_ds.load_dataframe(disease)
            progress.update(task, completed=True)
        
        console.print(f"Loaded {len(df)} records")
        
        # Apply filters
        filtered_df = sinan_ds.filter(
            df, uf=uf, sexo=sexo, ano=ano, municipio=municipio,
            evolucao=evolucao, classificacao=classificacao
        )
        
        console.print(f"Filtered to {len(filtered_df)} records")
        
        # Export results
        output_name = output or f"{disease}_filtered"
        sinan_ds.export(filtered_df, format=output_format, name=output_name)
        
        console.print(f"[green]✅ Results exported as {output_name}.{output_format}[/green]")
        
    except Exception as e:
        logger.error(f"Filtering failed: {e}")
        console.print(f"[red]❌ Error: {e}[/red]")
        raise click.Abort()


@sinan.command()
@click.argument('disease')
@click.option('--by', 'group_by', default='UF', help='Group by column')
@click.option('--metric', type=click.Choice(['count', 'mean', 'sum']), 
              default='count', help='Summary metric')
def summary(disease: str, group_by: str, metric: str):
    """Generate summary statistics for SINAN data."""
    
    console.print(f"[bold blue]Summary for {disease}[/bold blue]")
    
    try:
        sinan_ds = SinanDataSource()
        df = sinan_ds.load_dataframe(disease)
        
        summary_df = sinan_ds.summary(df, by=group_by, metric=metric)
        
        # Display results in a nice table
        table = Table(title=f"{disease} Summary by {group_by}")
        
        for col in summary_df.columns:
            table.add_column(col, style="cyan")
        
        for row in summary_df.iter_rows():
            table.add_row(*[str(val) for val in row])
        
        console.print(table)
        
    except Exception as e:
        logger.error(f"Summary failed: {e}")
        console.print(f"[red]❌ Error: {e}[/red]")
        raise click.Abort()


@sinan.command()
@click.argument('disease')
def info(disease: str):
    """Show information about available fields for a disease."""
    
    try:
        sinan_ds = SinanDataSource()
        fields = sinan_ds.describe_fields(disease)
        
        console.print(f"[bold blue]Available fields for {disease}:[/bold blue]")
        
        table = Table()
        table.add_column("Field Name", style="cyan")
        
        for field in fields:
            table.add_row(field)
        
        console.print(table)
        
    except Exception as e:
        logger.error(f"Info retrieval failed: {e}")
        console.print(f"[red]❌ Error: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    sinan()
