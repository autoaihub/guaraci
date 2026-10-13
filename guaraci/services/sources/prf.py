"""Fontes PRF (acidentes em rodovias federais) do registro padrao."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.prf import PRF_SPECS, PrfClient, datasource_for
from guaraci.prf.acidentes import MIN_YEAR
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def _params() -> List[SourceParameterSpec]:
    current_year = datetime.now().year
    return [
        SourceParameterSpec(
            name="output_dir", phase="tecnica", param_type="string",
            description="Output directory for downloaded files.",
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="output_format", phase="exportacao", param_type="string",
            description=(
                "Exporta um CSV UTF-8, Parquet ou SQLite por ano, com todas as "
                "colunas como texto e nomes de coluna como publicados."
            ),
            required=False, default=None, allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year", phase="coleta", param_type="integer",
            description=f"Ano inicial (desde {MIN_YEAR}, confirmado ao vivo).",
            required=True, default=None, minimum=MIN_YEAR, maximum=current_year + 1,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False, default=None, minimum=MIN_YEAR, maximum=current_year + 1,
        ),
        SourceParameterSpec(
            name="keep_raw", phase="tecnica", param_type="boolean",
            description="Se true, mantém o zip original além da exportação.",
            required=False, default=False,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="HTTP timeout in seconds.",
            required=False, default=PrfClient.DEFAULT_TIMEOUT, minimum=1,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes PRF na ordem de ``PRF_SPECS``."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode="prf drive files"),
            datasource_cls=datasource_for(spec.key),
            params_schema=_params(),
        )
        for spec in PRF_SPECS.values()
    ]
