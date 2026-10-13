"""Fontes de microdados do IBGE (PNS, PeNSE, POF) do registro padrão."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.ibge.microdados import PESQUISAS, IbgeFtpClient, Pesquisa, datasource_for
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def _params(pesquisa: Pesquisa) -> List[SourceParameterSpec]:
    anos = sorted(pesquisa.edicoes)
    edicoes = ", ".join(e.rotulo for _, e in sorted(pesquisa.edicoes.items()))
    tabelas = sorted({t.nome for e in pesquisa.edicoes.values() for t in e.tabelas})
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
            name="start_year",
            phase="coleta",
            param_type="integer",
            description=(
                f"Ano da edição inicial. Edições publicadas: {edicoes}. Ano sem "
                "edição não baixa nada."
            ),
            required=True,
            default=None,
            minimum=anos[0],
            maximum=anos[-1],
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ano da edição final (padrão: igual a start_year).",
            required=False,
            default=None,
            minimum=anos[0],
            maximum=anos[-1],
        ),
        SourceParameterSpec(
            name="tabelas",
            phase="coleta",
            param_type="string_list",
            description=(
                "Tabelas a exportar (padrão: todas da edição). Um arquivo por "
                "tabela, a primeira é a principal."
            ),
            required=False,
            default=None,
            allowed_values=tabelas,
        ),
        SourceParameterSpec(
            name="output_format",
            phase="exportacao",
            param_type="string",
            description=(
                "Exporta cada tabela em CSV UTF-8, Parquet ou SQLite, com todas "
                "as colunas como texto e os nomes do leiaute do IBGE. Omita para "
                "guardar só os zips publicados."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description="Se true, mantém os zips originais além da exportação.",
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="HTTP timeout in seconds.",
            required=False,
            default=IbgeFtpClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
        SourceParameterSpec(
            name="api_base_url",
            phase="tecnica",
            param_type="string",
            description="Optional ftp.ibge.gov.br base URL override.",
            required=False,
            default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes de microdados na ordem do registro de pesquisas."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=pesquisa.key,
                title=pesquisa.title,
                mode="ibge microdados",
            ),
            datasource_cls=datasource_for(pesquisa.key),
            params_schema=_params(pesquisa),
        )
        for pesquisa in PESQUISAS.values()
    ]
