"""Fonte do MI Social (MDS/SAGI) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.mds import ANO_PADRAO, DATASET, GRUPOS, MIN_YEAR, MisocialDataSource
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

TITLE = "MDS MI Social - Indicadores municipais mensais (Bolsa Família, CadÚnico, BPC, SUAS)"


def _normalize_mds_params(params):
    normalized = dict(params)
    for key in ("start_year", "end_year"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            try:
                normalized[key] = int(value.strip())
            except ValueError:
                pass
    grupos = normalized.get("grupos")
    if isinstance(grupos, str):
        grupos = [part for part in grupos.split(",")]
    if isinstance(grupos, (list, tuple)):
        normalized["grupos"] = [str(g).strip().lower() for g in grupos if str(g).strip()] or None
    fmt = normalized.get("output_format")
    if isinstance(fmt, str):
        normalized["output_format"] = fmt.strip().lower() or None
    return normalized


def _params() -> List[SourceParameterSpec]:
    current_year = datetime.now().year
    tamanhos = ", ".join(f"{nome} ({len(campos)})" for nome, campos in GRUPOS.items())
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
            description=(
                f"Ano inicial (desde {MIN_YEAR}; padrão {ANO_PADRAO}, último ano completo). "
                "Uma consulta por mês, todos os municípios."
            ),
            required=True, default=ANO_PADRAO, minimum=MIN_YEAR, maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False, default=None, minimum=MIN_YEAR, maximum=current_year,
        ),
        SourceParameterSpec(
            name="grupos", phase="coleta", param_type="string_list",
            description=(
                f"Grupos de campos (número de campos): {tamanhos}. Omita para todos; "
                "com todos, cada mês leva cerca de 50 s, então prefira os grupos que vai usar."
            ),
            required=False, default=None, allowed_values=list(GRUPOS),
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="HTTP timeout per request, in seconds.",
            required=False, default=MisocialDataSource.DEFAULT_TIMEOUT, minimum=1,
        ),
        SourceParameterSpec(
            name="base_url", phase="tecnica", param_type="string",
            description="Optional Solr select URL override.",
            required=False, default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna a fonte do MI Social."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=DATASET, title=TITLE, mode="mds solr"),
            datasource_cls=MisocialDataSource,
            params_schema=_params(),
            normalize_params=_normalize_mds_params,
        ),
    ]
