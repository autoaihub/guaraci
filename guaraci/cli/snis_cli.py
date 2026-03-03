"""
Guaraci SNIS CLI
================

CLI for SNIS via gov.br (default) and legacy BigQuery helpers.
"""

from pathlib import Path
from typing import Optional, Sequence

import click
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from guaraci.snis import (
    SinisaDataSource,
    SnisDataSource,
    SnisLegacyBigQueryDataSource,
)

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def snis(verbose: bool) -> None:
    """SNIS data operations for the Guaraci platform."""
    if verbose:
        logger.remove()
        logger.add(lambda msg: console.print(msg, end=""), level="DEBUG")


@snis.command()
@click.option(
    "--output-dir",
    type=click.Path(),
    help="Diretorio de saida para arquivos SNIS crus (default: data/snis).",
)
@click.option(
    "--results-url",
    help="URL da pagina SNIS (padrao: diagnosticos-anteriores-do-snis).",
)
@click.option(
    "--file-kinds",
    multiple=True,
    type=click.Choice(SinisaDataSource.VALID_FILE_KINDS, case_sensitive=False),
    help="Tipos de arquivo (planilhas, relatorios, glossarios, atestados, all).",
)
@click.option(
    "--modules",
    multiple=True,
    type=click.Choice(SinisaDataSource.VALID_MODULES, case_sensitive=False),
    help="Modulos do SINISA (agua, esgoto, residuos, aguas_pluviais, gestao_municipal).",
)
@click.option(
    "--extract-archives/--no-extract-archives",
    default=True,
    show_default=True,
    help="Extrai arquivos .zip apos download.",
)
@click.option("--overwrite", is_flag=True, help="Sobrescreve arquivos existentes.")
@click.option(
    "--timeout",
    type=int,
    default=120,
    show_default=True,
    help="Timeout HTTP em segundos.",
)
def download(
    output_dir: Optional[str],
    results_url: Optional[str],
    file_kinds: Sequence[str],
    modules: Sequence[str],
    extract_archives: bool,
    overwrite: bool,
    timeout: int,
) -> None:
    """Download SNIS raw files directly from official gov.br source."""
    console.print("[bold blue]Guaraci SNIS Downloader[/bold blue]")

    try:
        snis_ds = SnisDataSource(output_path=output_dir)

        with Progress(
            SpinnerColumn(),
            TextColumn("Coletando links e baixando arquivos crus..."),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("baixando", total=None)
            summary = snis_ds.download(
                output_dir=output_dir,
                results_url=results_url,
                file_kinds=list(file_kinds) if file_kinds else None,
                modules=list(modules) if modules else None,
                extract_archives=extract_archives,
                overwrite=overwrite,
                timeout=timeout,
            )
            progress.update(task, completed=True)

        console.print("[green]SUCCESS SNIS raw download completed![/green]")
        console.print(
            "Found: {found} | Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed}".format(
                found=summary.documents_found,
                downloaded=summary.downloaded_count,
                skipped=summary.skipped_count,
                failed=summary.failed_count,
            )
        )
        console.print(f"Manifest: {summary.manifest_path}")
    except Exception as exc:
        logger.error(f"SNIS download failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@snis.command(name="download-legacy")
@click.option("--ano", type=int, required=True, help="Ano da serie historica")
@click.option("--output-csv", type=click.Path(), required=True, help="CSV output path")
@click.option("--ufs", multiple=True, help="Siglas de UFs (ex: SP RJ)")
@click.option("--municipios", multiple=True, help="Codigos IBGE de municipio")
@click.option("--table-id", help="BigQuery table id (project.dataset.table)")
@click.option("--ano-col", help="Nome da coluna de ano no BigQuery")
@click.option("--municipio-col", help="Nome da coluna de municipio no BigQuery")
@click.option("--uf-col", help="Nome da coluna de UF no BigQuery")
@click.option(
    "--all-columns",
    is_flag=True,
    help="Inclui todas as colunas disponiveis da tabela (alem dos indicadores).",
)
@click.option(
    "--billing-project",
    help="Projeto de faturamento no BigQuery (ou defina BASEDOSDADOS_BILLING_PROJECT).",
)
def download_legacy(
    ano: int,
    output_csv: str,
    ufs: Sequence[str],
    municipios: Sequence[str],
    table_id: Optional[str],
    ano_col: Optional[str],
    municipio_col: Optional[str],
    uf_col: Optional[str],
    all_columns: bool,
    billing_project: Optional[str],
) -> None:
    """Download SNIS from legacy BigQuery integration."""
    console.print("[bold yellow]Guaraci SNIS Legacy BigQuery Downloader[/bold yellow]")
    console.print(f"Ano: {ano}")

    try:
        legacy_ds = SnisLegacyBigQueryDataSource()

        with Progress(
            SpinnerColumn(),
            TextColumn("Consultando BigQuery legado..."),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("buscando", total=None)
            legacy_ds.download(
                ano=ano,
                output_csv=output_csv,
                ufs=list(ufs) if ufs else None,
                municipios=list(municipios) if municipios else None,
                table_id=table_id,
                billing_project_id=billing_project,
                ano_col_override=ano_col,
                municipio_col_override=municipio_col,
                uf_col_override=uf_col,
                all_columns=all_columns,
            )
            progress.update(task, completed=True)

        console.print("[green]SUCCESS Legacy SNIS data saved successfully![/green]")
        console.print(f"Output: {output_csv}")
    except Exception as exc:
        logger.error(f"Legacy SNIS download failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@snis.command(name="schema-legacy")
@click.option("--table-id", help="BigQuery table id (project.dataset.table)")
@click.option("--output-csv", type=click.Path(), required=True, help="CSV output path")
@click.option(
    "--billing-project",
    help="Projeto de faturamento no BigQuery (ou defina BASEDOSDADOS_BILLING_PROJECT).",
)
def schema_legacy(
    table_id: Optional[str],
    output_csv: str,
    billing_project: Optional[str],
) -> None:
    """Export legacy SNIS BigQuery schema to CSV."""
    console.print("[bold yellow]Guaraci SNIS Legacy Schema Export[/bold yellow]")

    try:
        legacy_ds = SnisLegacyBigQueryDataSource()
        output_path = legacy_ds.export_schema(
            output_csv=output_csv,
            table_id=table_id,
            billing_project_id=billing_project,
        )
        console.print(f"[green]SUCCESS Schema saved to {output_path}[/green]")
    except Exception as exc:
        logger.error(f"Legacy SNIS schema export failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@snis.command(name="sinisa-list")
@click.option(
    "--results-url",
    help="URL da pagina de resultados SINISA (padrao: pagina oficial).",
)
@click.option(
    "--file-kinds",
    multiple=True,
    type=click.Choice(SinisaDataSource.VALID_FILE_KINDS, case_sensitive=False),
    help="Tipos de arquivo (planilhas, relatorios, glossarios, atestados, all).",
)
@click.option(
    "--modules",
    multiple=True,
    type=click.Choice(SinisaDataSource.VALID_MODULES, case_sensitive=False),
    help="Modulos do SINISA (agua, esgoto, residuos, aguas_pluviais, gestao_municipal).",
)
@click.option(
    "--timeout",
    type=int,
    default=120,
    show_default=True,
    help="Timeout HTTP em segundos.",
)
def sinisa_list(
    results_url: Optional[str],
    file_kinds: Sequence[str],
    modules: Sequence[str],
    timeout: int,
) -> None:
    """List SINISA documents available on the selected results page."""
    console.print("[bold blue]Guaraci SINISA Link Discovery[/bold blue]")
    try:
        sinisa_ds = SinisaDataSource()
        docs = sinisa_ds.list_documents(
            results_url=results_url,
            file_kinds=list(file_kinds) if file_kinds else None,
            modules=list(modules) if modules else None,
            timeout=timeout,
        )
        if not docs:
            console.print("[yellow]Nenhum documento encontrado com esses filtros.[/yellow]")
            return

        console.print(f"[green]Documentos encontrados: {len(docs)}[/green]")
        for idx, doc in enumerate(docs, start=1):
            module = doc.module or "-"
            label = doc.text or Path(doc.url).name
            console.print(f"{idx:02d}. [{doc.kind}] [{module}] {label}", markup=False)
            console.print(f"    {doc.url}", markup=False)
    except Exception as exc:
        logger.error(f"SINISA listing failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


@snis.command(name="sinisa-download")
@click.option(
    "--output-dir",
    type=click.Path(),
    help="Diretorio de saida para arquivos crus do SINISA (default: data/sinisa).",
)
@click.option(
    "--results-url",
    help="URL da pagina de resultados SINISA (padrao: pagina oficial).",
)
@click.option(
    "--file-kinds",
    multiple=True,
    type=click.Choice(SinisaDataSource.VALID_FILE_KINDS, case_sensitive=False),
    help="Tipos de arquivo (planilhas, relatorios, glossarios, atestados, all).",
)
@click.option(
    "--modules",
    multiple=True,
    type=click.Choice(SinisaDataSource.VALID_MODULES, case_sensitive=False),
    help="Modulos do SINISA (agua, esgoto, residuos, aguas_pluviais, gestao_municipal).",
)
@click.option(
    "--extract-archives/--no-extract-archives",
    default=True,
    show_default=True,
    help="Extrai arquivos .zip apos download.",
)
@click.option("--overwrite", is_flag=True, help="Sobrescreve arquivos existentes.")
@click.option(
    "--timeout",
    type=int,
    default=120,
    show_default=True,
    help="Timeout HTTP em segundos.",
)
def sinisa_download(
    output_dir: Optional[str],
    results_url: Optional[str],
    file_kinds: Sequence[str],
    modules: Sequence[str],
    extract_archives: bool,
    overwrite: bool,
    timeout: int,
) -> None:
    """Download raw SINISA files directly from official gov.br source."""
    console.print("[bold blue]Guaraci SINISA Raw Downloader[/bold blue]")

    try:
        sinisa_ds = SinisaDataSource(output_path=output_dir)
        with Progress(
            SpinnerColumn(),
            TextColumn("Coletando links e baixando arquivos crus..."),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("baixando", total=None)
            summary = sinisa_ds.download(
                output_dir=output_dir,
                results_url=results_url,
                file_kinds=list(file_kinds) if file_kinds else None,
                modules=list(modules) if modules else None,
                extract_archives=extract_archives,
                overwrite=overwrite,
                timeout=timeout,
            )
            progress.update(task, completed=True)

        console.print("[green]SUCCESS SINISA raw download completed![/green]")
        console.print(
            "Found: {found} | Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed}".format(
                found=summary["documents_found"],
                downloaded=summary["downloaded_count"],
                skipped=summary["skipped_count"],
                failed=summary["failed_count"],
            )
        )
        console.print(f"Manifest: {summary['manifest_path']}")
    except Exception as exc:
        logger.error(f"SINISA raw download failed: {exc}")
        console.print(f"[red]ERROR Error: {exc}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    snis()
