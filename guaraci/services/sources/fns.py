"""Fonte FNS (repasses fundo a fundo) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.fns import FNS_REPASSES_KEY, FnsClient, FnsRepassesDataSource
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

#: Último ano completo publicado, conferido ao vivo em 2026-10-19 (o portal lista 2002 a 2026, e 2026 é parcial).
#: Padrão de ``start_year``: a coleta sem ano fica leve. Microdados pesados
#: (PNAD, PNS, POF, PeNSE) ficam sem padrão de propósito.
ANO_PADRAO = 2025


def build_sources() -> List[DownloadSource]:
    """Retorna a fonte FNS de repasses fundo a fundo."""
    current_year = datetime.now().year
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=FNS_REPASSES_KEY,
                title="FNS Repasses Fundo a Fundo (com população)",
                mode="fns files",
            ),
            datasource_cls=FnsRepassesDataSource,
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
                        "Exporta um arquivo por ano em CSV UTF-8, Parquet ou SQLite, com todas "
                        "as colunas como texto. Omita para guardar CSV/XLSX como o FNS publica."
                    ),
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=f"Ano inicial (desde {FnsRepassesDataSource.MIN_YEAR}; padrão {ANO_PADRAO}).",
                    required=True,
                    default=ANO_PADRAO,
                    minimum=FnsRepassesDataSource.MIN_YEAR,
                    maximum=current_year + 1,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (padrão: igual a start_year). O ano corrente é parcial.",
                    required=False,
                    default=None,
                    minimum=FnsRepassesDataSource.MIN_YEAR,
                    maximum=current_year + 1,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, mantém o arquivo original além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=FnsClient.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
            ],
        )
    ]
