"""Fontes do Banco Central (SICOR, crédito rural) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.bcb import (
    SicorComercializacaoUfDataSource as _Comercializacao,
    SicorCusteioMunicipioDataSource as _Custeio,
    SicorInvestimentoMunicipioDataSource as _Investimento,
)
from guaraci.bcb.sicor import MIN_YEAR
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

#: Padrão de ``start_year``: um exercício fechado, para a coleta sem ano ficar leve.
ANO_PADRAO = 2025


def _params(timeout_default: int) -> List[SourceParameterSpec]:
    current_year = datetime.now().year
    return [
        SourceParameterSpec(
            name="output_dir", phase="tecnica", param_type="string",
            description="Output directory for downloaded files.",
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="output_format", phase="exportacao", param_type="string",
            description="Export format (padrão csv), tudo como texto.",
            required=False, default=None, allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year", phase="coleta", param_type="integer",
            description=f"Ano de emissão inicial (desde {MIN_YEAR}; padrão {ANO_PADRAO}).",
            required=True, default=ANO_PADRAO, minimum=MIN_YEAR, maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano de emissão final (padrão: igual a start_year).",
            required=False, default=None, minimum=MIN_YEAR, maximum=current_year,
        ),
        SourceParameterSpec(
            name="meses", phase="coleta", param_type="string_list",
            description="Meses de emissão (1 a 12); padrão: todos. Uma requisição por ano e mês.",
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="HTTP timeout in seconds.",
            required=False, default=timeout_default, minimum=1,
        ),
        SourceParameterSpec(
            name="pause_ms", phase="tecnica", param_type="integer",
            description="Pausa entre requisições, em milissegundos.",
            required=False, default=0, minimum=0,
        ),
        SourceParameterSpec(
            name="api_base_url", phase="tecnica", param_type="string",
            description="Optional SICOR OData base URL override.",
            required=False, default=None,
        ),
    ]


def _source(datasource_cls, title: str) -> ApiDownloadSource:
    return ApiDownloadSource(
        descriptor=SourceDescriptor(source=datasource_cls.DATASET, title=title, mode="sicor odata"),
        datasource_cls=datasource_cls,
        params_schema=_params(datasource_cls.DEFAULT_TIMEOUT),
    )


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes do Banco Central (SICOR) na ordem canônica."""
    return [
        _source(_Custeio, "BCB SICOR - Crédito rural de custeio por município e produto"),
        _source(_Investimento, "BCB SICOR - Crédito rural de investimento por município e produto"),
        _source(_Comercializacao, "BCB SICOR - Crédito rural de comercialização por UF e produto"),
    ]
