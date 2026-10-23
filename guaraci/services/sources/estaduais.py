"""Fontes estaduais e municipais: TabNet do CVE-SP e IQAR diário do Rio de Janeiro."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.estaduais.cvesp import CVESP_SPECS, CvespSpec, cvesp_datasource_for
from guaraci.estaduais.rio_iqar import RioIqarDiarioDataSource
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.tabnet import TabnetClient

#: Último ano com casos no TabNet do CVE-SP, conferido ao vivo em 2026-10-23.
CVESP_ANO_PADRAO = 2025


def _normalize_year_params(params):
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


def _output_params() -> List[SourceParameterSpec]:
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
    ]


def _cvesp_params(spec: CvespSpec) -> List[SourceParameterSpec]:
    current_year = datetime.now().year
    return [
        *_output_params(),
        SourceParameterSpec(
            name="start_year", phase="coleta", param_type="integer",
            description=(
                f"Ano inicial de notificação (desde {spec.min_year}; padrão {CVESP_ANO_PADRAO}, "
                "último ano publicado). Uma só consulta traz a série; o intervalo filtra os anos."
            ),
            required=True, default=CVESP_ANO_PADRAO, minimum=spec.min_year, maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False, default=None, minimum=spec.min_year, maximum=current_year,
        ),
        SourceParameterSpec(
            name="keep_raw", phase="tecnica", param_type="boolean",
            description="Se true, guarda a página HTML da consulta como veio do TabNet.",
            required=False, default=False,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="Timeout de socket, em segundos.",
            required=False, default=TabnetClient.DEFAULT_TIMEOUT, minimum=1,
        ),
        SourceParameterSpec(
            name="base_url", phase="tecnica", param_type="string",
            description="Optional deftohtm.exe URL override.",
            required=False, default=None,
        ),
    ]


def _rio_params() -> List[SourceParameterSpec]:
    return [
        *_output_params(),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="Timeout de cada requisição, em segundos.",
            required=False, default=RioIqarDiarioDataSource.DEFAULT_TIMEOUT, minimum=1,
        ),
        SourceParameterSpec(
            name="layer_url", phase="tecnica", param_type="string",
            description="Optional ArcGIS REST layer URL override.",
            required=False, default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes estaduais e municipais na ordem canônica."""
    sources: List[DownloadSource] = []
    for spec in CVESP_SPECS.values():
        sources.append(
            ApiDownloadSource(
                descriptor=SourceDescriptor(
                    source=spec.dataset, title=spec.title, mode="cvesp tabnet"
                ),
                datasource_cls=cvesp_datasource_for(spec),
                params_schema=_cvesp_params(spec),
                normalize_params=_normalize_year_params,
            )
        )
    sources.append(
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=RioIqarDiarioDataSource.DATASET,
                title=RioIqarDiarioDataSource.TITLE,
                mode="arcgis rest",
            ),
            datasource_cls=RioIqarDiarioDataSource,
            params_schema=_rio_params(),
            normalize_params=_normalize_year_params,
        )
    )
    return sources
