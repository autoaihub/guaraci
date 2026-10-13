"""Fontes do SIOPS (indicadores municipais e estaduais via TabNet) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.siops import (
    SiopsIndicadoresEstadosDataSource as _Est,
    SiopsIndicadoresMunicipiosDataSource as _Mun,
)


def _normalize_siops_params(params):
    normalized = dict(params)
    for key in ("start_year", "end_year"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            try:
                normalized[key] = int(value.strip())
            except ValueError:
                pass
    fmt = normalized.get("output_format")
    if isinstance(fmt, str):
        normalized["output_format"] = fmt.strip().lower() or None
    return normalized


def _params(cls, unidade: str) -> List[SourceParameterSpec]:
    current_year = datetime.now().year
    first = cls.SPEC.min_year
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
            description=f"Ano inicial (desde {first}, confirmado ao vivo). Uma consulta por ano, {unidade}.",
            required=True, default=None, minimum=first, maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False, default=None, minimum=first, maximum=current_year,
        ),
        SourceParameterSpec(
            name="keep_raw", phase="tecnica", param_type="boolean",
            description="Se true, guarda a página HTML de cada ano como veio do TabNet.",
            required=False, default=False,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="Timeout de socket, em segundos.",
            required=False, default=cls.DEFAULT_TIMEOUT, minimum=1,
        ),
        SourceParameterSpec(
            name="base_url", phase="tecnica", param_type="string",
            description="Optional tabcgi.exe URL override.",
            required=False, default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes do SIOPS na ordem canônica."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Mun.SPEC.dataset, title=_Mun.SPEC.title, mode="siops tabnet"
            ),
            datasource_cls=_Mun,
            params_schema=_params(_Mun, "todos os municípios declarantes"),
            normalize_params=_normalize_siops_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Est.SPEC.dataset, title=_Est.SPEC.title, mode="siops tabnet"
            ),
            datasource_cls=_Est,
            params_schema=_params(_Est, "todas as UFs declarantes"),
            normalize_params=_normalize_siops_params,
        ),
    ]
