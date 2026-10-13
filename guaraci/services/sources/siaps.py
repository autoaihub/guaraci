"""Fontes SIAPS (MS/SAPS, API DEMAS) do registro padrao.

O SIAPS publica dois modelos de informacao da atencao primaria: atendimento
individual (MIAI) e cadastro individual (MICI). Ambos sao agregados por
competencia (AAAAMM) e perfil do individuo, e o atendimento passa de 6
milhoes de linhas por competencia.

Por isso o ``max_pages`` padrao aqui e o teto do coletor (200000 paginas), e
nao o ``DEFAULT_MAX_PAGES`` de 250 do OpenDataSUS, que cortaria a competencia
em 250 mil linhas e so avisaria no manifesto. A coleta termina na primeira
pagina incompleta ou vazia; o teto existe apenas como trava de seguranca.

O orquestrador (cadencia ``API_MONTHLY``) entrega ``start_date``/``end_date``
de um mes; ``normalize_params`` converte esse par em ``competencia_siaps``
e descarta as datas, porque a fonte nao tem coluna de data para o recorte
local do coletor. Uma competencia por unidade.

As chaves coincidem com as que o scaffold do registro geraria, de modo que o
dedup por nome em ``DownloadService._default_sources`` mantem esta versao.
"""

import re
from datetime import date
from typing import Dict, List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.opendatasus.datasource import OpenDataSUSDataSource
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    DownloadSource,
    OpenDataSUSDownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_opendatasus_params

# Teto de paginas do coletor (datasource.py: min(max_pages, 200000)).
SIAPS_MAX_PAGES = 200000

_COMPETENCIA_RE = re.compile(r"^(\d{4})(0[1-9]|1[0-2])$")


def _competencia_from_date(value: object, *, field_name: str) -> str:
    try:
        parsed = date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ValueError(
            f"Parameter '{field_name}' must be an ISO date (YYYY-MM-DD)."
        ) from exc
    return f"{parsed.year:04d}{parsed.month:02d}"


def _normalize_siaps_params(params: Dict[str, object]) -> Dict[str, object]:
    """Converte datas em ``competencia_siaps`` e fixa o teto de paginas."""
    normalized = _normalize_opendatasus_params(params)

    start_date = normalized.pop("start_date", None)
    end_date = normalized.pop("end_date", None)

    competencia = normalized.get("competencia_siaps")
    if isinstance(competencia, str):
        competencia = competencia.strip() or None
    elif competencia is not None:
        competencia = str(competencia)

    if competencia is None and start_date:
        competencia = _competencia_from_date(start_date, field_name="start_date")
        if end_date:
            fim = _competencia_from_date(end_date, field_name="end_date")
            if fim != competencia:
                raise ValueError(
                    "SIAPS collects one competencia per run: start_date and "
                    f"end_date must fall in the same month ({competencia} != {fim})."
                )
    elif competencia is None and end_date:
        competencia = _competencia_from_date(end_date, field_name="end_date")

    if competencia is not None and not _COMPETENCIA_RE.match(competencia):
        raise ValueError(
            "Parameter 'competencia_siaps' must be in YYYYMM format (e.g., 202606)."
        )
    if competencia is None:
        normalized.pop("competencia_siaps", None)
    else:
        normalized["competencia_siaps"] = competencia

    if normalized.get("max_pages") is None:
        normalized["max_pages"] = SIAPS_MAX_PAGES
    return normalized


def _common_specs(
    *, extra_filters: List[SourceParameterSpec]
) -> List[SourceParameterSpec]:
    specs: List[SourceParameterSpec] = [
        SourceParameterSpec(
            name="start_date",
            phase="coleta",
            param_type="string",
            description=(
                "Inicio da competencia (AAAA-MM-DD). O mes vira "
                "competencia_siaps; usado pelo orquestrador mensal."
            ),
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="end_date",
            phase="coleta",
            param_type="string",
            description="Fim da competencia (AAAA-MM-DD); deve cair no mesmo mes de start_date.",
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="competencia_siaps",
            phase="basico",
            param_type="string",
            description="Competencia no formato AAAAMM (ex.: 202606). Tem precedencia sobre as datas.",
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="municipio",
            phase="basico",
            param_type="string",
            description="Codigo IBGE do municipio, sem digito verificador (6 digitos).",
            required=False,
            default=None,
        ),
    ]
    specs.extend(extra_filters)
    specs.extend(
        [
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
                description="Optional export format for processed datasets.",
                required=False,
                default=None,
                allowed_values=EXPORT_FORMAT_VALUES,
            ),
            SourceParameterSpec(
                name="keep_raw",
                phase="tecnica",
                param_type="boolean",
                description="Se true, salva snapshot bruto JSONL alem da exportacao.",
                required=False,
                default=False,
            ),
            SourceParameterSpec(
                name="batch_size",
                phase="tecnica",
                param_type="integer",
                description="Page size for the DEMAS API pagination.",
                required=False,
                default=1000,
                minimum=1,
                maximum=1000,
            ),
            SourceParameterSpec(
                name="max_pages",
                phase="tecnica",
                param_type="integer",
                description=(
                    "Maximo de paginas. O padrao e o teto do coletor, para cobrir a "
                    "competencia inteira (o atendimento passa de 6 milhoes de linhas)."
                ),
                required=False,
                default=SIAPS_MAX_PAGES,
                minimum=1,
                maximum=SIAPS_MAX_PAGES,
            ),
            SourceParameterSpec(
                name="api_base_url",
                phase="tecnica",
                param_type="string",
                description="Optional DEMAS API base URL override.",
                required=False,
                default=None,
            ),
        ]
    )
    return specs


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes SIAPS na ordem canonica."""
    atendimento_filters = [
        SourceParameterSpec(
            name="co_uf_ibge",
            phase="basico",
            param_type="string",
            description="Codigo IBGE da UF (ex.: 52). Fatia a coleta por UF.",
            required=False,
            default=None,
        ),
    ]
    cadastro_filters = [
        SourceParameterSpec(
            name="regiao",
            phase="basico",
            param_type="string",
            description="Regiao do registro (ex.: Centro-Oeste).",
            required=False,
            default=None,
        ),
    ]
    return [
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="atencao_primaria_siaps_atendimento_individual",
                title="SIAPS Atendimento Individual (MIAI)",
                mode="siaps api",
            ),
            datasource_cls=OpenDataSUSDataSource,
            params_schema=_common_specs(extra_filters=atendimento_filters),
            fixed_dataset="atencao-primaria/siaps-atendimento-individual",
            normalize_params=_normalize_siaps_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="atencao_primaria_siaps_cadastro_individual",
                title="SIAPS Cadastro Individual (MICI)",
                mode="siaps api",
            ),
            datasource_cls=OpenDataSUSDataSource,
            params_schema=_common_specs(extra_filters=cadastro_filters),
            fixed_dataset="atencao-primaria/siaps-cadastro-individual",
            normalize_params=_normalize_siaps_params,
        ),
    ]
