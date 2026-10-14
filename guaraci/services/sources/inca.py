"""Fontes INCA (Registros Hospitalares de Câncer) do registro padrao."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.inca import INCA_SPECS, MAX_YEAR_FALLBACK, MIN_YEAR, IncaClient, datasource_for
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
                "Exporta um CSV, Parquet ou SQLite por ano, com todos os estados "
                "e todas as colunas do DBF como o INCA publica."
            ),
            required=False, default=None, allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year", phase="coleta", param_type="integer",
            description=(
                f"Ano inicial do diagnóstico (desde {MIN_YEAR}; último ano "
                f"publicado conferido: {MAX_YEAR_FALLBACK})."
            ),
            required=True, default=MAX_YEAR_FALLBACK, minimum=MIN_YEAR, maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False, default=None, minimum=MIN_YEAR, maximum=current_year,
        ),
        SourceParameterSpec(
            name="keep_raw", phase="tecnica", param_type="boolean",
            description="Se true, mantém o zip original além da exportação.",
            required=False, default=False,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="HTTP timeout and generation wait, in seconds.",
            required=False, default=IncaClient.DEFAULT_TIMEOUT, minimum=1,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes INCA na ordem de ``INCA_SPECS``."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode="inca rhc zip"),
            datasource_cls=datasource_for(spec.key),
            params_schema=_params(),
        )
        for spec in INCA_SPECS.values()
    ]
