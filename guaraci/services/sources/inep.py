"""Fonte INEP: Censo Escolar (tabela de escolas, um zip por ano)."""

from datetime import datetime
from typing import List

from guaraci.arquivos.inep_censo_escolar import (
    INEP_CENSO_ESCOLAR,
    MIN_YEAR,
    InepCensoEscolarDataSource,
)
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes INEP."""
    current_year = datetime.now().year
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=INEP_CENSO_ESCOLAR,
                title="INEP Censo Escolar - Tabela de escolas",
                mode="inep files",
            ),
            datasource_cls=InepCensoEscolarDataSource,
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
                        "Exporta em CSV UTF-8, Parquet ou SQLite, com todas as colunas "
                        "como texto e nomes de coluna como publicados. Omita para guardar "
                        "o zip como a fonte publica."
                    ),
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
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
                    description="HTTP timeout in seconds (cada zip tem de 200 a 540 MB).",
                    required=False,
                    default=1800,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        f"Ano inicial (desde {MIN_YEAR}; antes disso o esquema é outro). "
                        "Omita para todos os anos."
                    ),
                    required=False,
                    default=None,
                    minimum=MIN_YEAR,
                    maximum=current_year + 1,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (padrão: igual a start_year).",
                    required=False,
                    default=None,
                    minimum=MIN_YEAR,
                    maximum=current_year + 1,
                ),
            ],
        )
    ]
