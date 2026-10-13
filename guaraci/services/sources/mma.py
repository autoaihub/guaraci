"""Fontes MMA (MonitorAr) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.mma import MIN_YEAR, MonitorArClient, MonitorArDataSource
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes MMA."""
    current_year = datetime.now().year
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="mma_monitorar",
                title="MMA MonitorAr (Qualidade do Ar)",
                mode="mma ckan files",
            ),
            datasource_cls=MonitorArDataSource,
            params_schema=[
                SourceParameterSpec(
                    name="output_dir",
                    phase="tecnica",
                    param_type="string",
                    description="Output directory for downloaded files.",
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="output_format",
                    phase="exportacao",
                    param_type="string",
                    description=(
                        "Exporta em CSV UTF-8, Parquet ou SQLite (um arquivo por ano), "
                        "com todas as colunas como texto. Omita para guardar o zip "
                        "como o MMA publica."
                    ),
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        f"Ano inicial (desde {MIN_YEAR}). Sem ano, baixa todos os "
                        "anos publicados."
                    ),
                    required=False,
                    default=None,
                    minimum=MIN_YEAR,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (padrão: igual a start_year).",
                    required=False,
                    default=None,
                    minimum=MIN_YEAR,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, mantém o zip original além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=MonitorArClient.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional dados.mma.gov.br CKAN action API base URL override.",
                    required=False,
                    default=None,
                ),
            ],
        )
    ]
