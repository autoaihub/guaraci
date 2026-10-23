"""Fontes do IPEADATA (OData v4) do registro padrão."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.ipea import (
    DEFAULT_SERIES_CODES,
    IpeadataMetadadosDataSource as _Metadados,
    IpeadataSeriesDataSource as _Series,
)
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

_MODE = "ipeadata api"


def _technical(timeout_default: int) -> List[SourceParameterSpec]:
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
            name="timeout", phase="tecnica", param_type="integer",
            description="HTTP timeout in seconds.",
            required=False, default=timeout_default, minimum=1,
        ),
        SourceParameterSpec(
            name="api_base_url", phase="tecnica", param_type="string",
            description="Optional IPEADATA OData base URL override.",
            required=False, default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes do IPEADATA na ordem canônica."""
    series_params = _technical(_Series.DEFAULT_TIMEOUT) + [
        SourceParameterSpec(
            name="series", phase="coleta", param_type="string_list",
            description=(
                "Códigos SERCODIGO das séries (ver ipeadata_metadados). Padrão: "
                f"{len(DEFAULT_SERIES_CODES)} séries sem par primário acessível "
                "(Atlas da Violência, Atlas da Vulnerabilidade Social, arrecadação "
                "municipal e censos demográficos antigos), lista em guaraci/ipea/series.py."
            ),
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="pause_ms", phase="tecnica", param_type="integer",
            description="Pausa entre séries, em milissegundos.",
            required=False, default=0, minimum=0,
        ),
    ]
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Series.DATASET,
                title="IPEADATA - Séries selecionadas",
                mode=_MODE,
            ),
            datasource_cls=_Series,
            params_schema=series_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Metadados.DATASET,
                title="IPEADATA - Catálogo de séries e territórios",
                mode=_MODE,
            ),
            datasource_cls=_Metadados,
            params_schema=_technical(_Metadados.DEFAULT_TIMEOUT),
        ),
    ]
