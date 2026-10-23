"""Fontes do MTE (Novo CAGED e RAIS) por FTP e 7z."""

from datetime import datetime
from typing import List

from guaraci.arquivos.http_files import HttpFileClient
from guaraci.core.contracts import SourceParameterSpec
from guaraci.mte.caged import CAGED_FILES, MIN_YEAR as CAGED_MIN_YEAR
from guaraci.mte.caged import datasource_for as caged_datasource_for
from guaraci.mte.rais import MIN_YEAR as RAIS_MIN_YEAR
from guaraci.mte.rais import RAIS_FILES, RAIS_REGIOES
from guaraci.mte.rais import datasource_for as rais_datasource_for
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

_MODE = "mte ftp files"


def _common() -> List[SourceParameterSpec]:
    return [
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
                "Exporta em CSV UTF-8, Parquet ou SQLite (um arquivo por 7z), com todas as "
                "colunas como texto e nomes de coluna como publicados. Exige o 7-Zip no PATH "
                "ou o pacote py7zr. Omita para guardar o 7z como o MTE publica."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description="Se true, mantém o 7z original além da exportação.",
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="Timeout do FTP em segundos.",
            required=False,
            default=HttpFileClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
    ]


def _caged_params() -> List[SourceParameterSpec]:
    years = [str(y) for y in range(CAGED_MIN_YEAR, datetime.now().year + 1)]
    return [
        SourceParameterSpec(
            name="anos",
            phase="coleta",
            param_type="string_list",
            description=(
                f"Anos (desde {CAGED_MIN_YEAR}). Sem anos nem datas, baixa só o último mês "
                "publicado (defasagem de cerca de 1 mês)."
            ),
            required=False,
            default=None,
            allowed_values=years,
        ),
        SourceParameterSpec(
            name="meses",
            phase="coleta",
            param_type="string_list",
            description="Meses (01 a 12) dentro dos anos pedidos. Omita para o ano inteiro.",
            required=False,
            default=None,
            allowed_values=[f"{m:02d}" for m in range(1, 13)],
        ),
        SourceParameterSpec(
            name="start_date",
            phase="coleta",
            param_type="string",
            description="Data inicial (`AAAA-MM-DD` ou `DD/MM/AAAA`); vale o mês dela.",
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="end_date",
            phase="coleta",
            param_type="string",
            description="Data final (`AAAA-MM-DD` ou `DD/MM/AAAA`); padrão: a data inicial.",
            required=False,
            default=None,
        ),
        *_common(),
    ]


def _rais_params(key: str) -> List[SourceParameterSpec]:
    last = datetime.now().year
    params = [
        SourceParameterSpec(
            name="anos",
            phase="coleta",
            param_type="string_list",
            description=(
                f"Anos (desde {RAIS_MIN_YEAR}, o primeiro com o leiaute atual). Informe "
                "'anos' ou start_year/end_year: o ano de vínculos passa de 4 GB comprimidos."
            ),
            required=False,
            default=None,
            allowed_values=[str(y) for y in range(RAIS_MIN_YEAR, last + 1)],
        ),
        SourceParameterSpec(
            name="start_year",
            phase="coleta",
            param_type="integer",
            description=f"Ano inicial (desde {RAIS_MIN_YEAR}).",
            required=False,
            default=None,
            minimum=RAIS_MIN_YEAR,
            maximum=last,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False,
            default=None,
            minimum=RAIS_MIN_YEAR,
            maximum=last,
        ),
    ]
    if key == "mte_rais_vinculos":
        params.append(
            SourceParameterSpec(
                name="regioes",
                phase="coleta",
                param_type="string_list",
                description=(
                    "Arquivos regionais dos vínculos (um CSV por região). Omita para todas; "
                    "SP sozinho tem cerca de 1 GB comprimido por ano."
                ),
                required=False,
                default=None,
                allowed_values=list(RAIS_REGIOES),
            )
        )
    return [*params, *_common()]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes do MTE: três do Novo CAGED e duas da RAIS."""
    sources: List[DownloadSource] = [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODE),
            datasource_cls=caged_datasource_for(spec.key),
            params_schema=_caged_params(),
        )
        for spec in CAGED_FILES.values()
    ]
    sources.extend(
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODE),
            datasource_cls=rais_datasource_for(spec.key),
            params_schema=_rais_params(spec.key),
        )
        for spec in RAIS_FILES.values()
    )
    return sources
