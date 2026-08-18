"""Fonte INMET (estacoes meteorologicas automaticas historicas)."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_inmet_params
from guaraci.utils.mapping import UF_DICT

_UF_VALUES = sorted(set(UF_DICT.values()))


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes INMET na ordem canonica."""
    current_year = datetime.now().year
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="inmet_estacoes",
                title="INMET (Estações Meteorológicas Automáticas)",
                mode="inmet portal zip",
            ),
            datasource_cls=_downloads.InmetEstacoesDataSource,
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
                    description="Optional export format for the parsed series.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial (2000+). Cada ano baixa 1 ZIP com TODAS "
                        "as estações automáticas do Brasil "
                        "(≈90 MB para um ano recente completo; use 'ufs' "
                        "para reduzir o volume extraído)."
                    ),
                    required=True,
                    default=None,
                    minimum=_downloads.InmetEstacoesDataSource.MIN_YEAR,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (2000+). Igual a start_year se omitido.",
                    required=False,
                    default=None,
                    minimum=_downloads.InmetEstacoesDataSource.MIN_YEAR,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="ufs",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "UFs a extrair do ZIP anual (por nome do arquivo da "
                        "estação). Vazio/omitido = todas as estações do Brasil."
                    ),
                    required=False,
                    default=None,
                    allowed_values=_UF_VALUES,
                ),
                SourceParameterSpec(
                    name="variables",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Projeção opcional de colunas de variáveis (slug do "
                        "cabeçalho do CSV original, ex.: "
                        "'precipitacao_total_horario_mm'). Vazio = todas."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description=(
                        "Se true, mantém os CSVs originais extraídos por "
                        "estação além da tabela materializada."
                    ),
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.InmetEstacoesDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional INMET portal base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_inmet_params,
        ),
    ]
