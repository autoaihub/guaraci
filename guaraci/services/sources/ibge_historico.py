"""Fontes IBGE de profundidade histórica e preços: IPCA, INPC e IPCA-15 (SIDRA), MUNIC e
ESTADIC em edições anteriores (FTP) e microdados das amostras dos Censos de 2010 e 2000."""

from typing import List

from guaraci.arquivos import ibge_perfil
from guaraci.core.contracts import SourceParameterSpec
from guaraci.ibge.microdados import datasource_for_pesquisa
from guaraci.ibge.microdados_censos import PESQUISAS_CENSOS
from guaraci.ibge.precos import (
    DETALHES,
    NIVEIS_GRUPOS,
    PRECOS_GRUPOS_SOURCES,
    PRECOS_SERIE_SOURCES,
)
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_ibge_params
from guaraci.services.sources.arquivos import http_file_source
from guaraci.services.sources.ibge_microdados import _params as _params_microdados

_TITULOS = {
    "ibge_ipca_serie": "IBGE IPCA: série histórica do índice geral (desde 1979)",
    "ibge_inpc_serie": "IBGE INPC: série histórica do índice geral (desde 1979)",
    "ibge_ipca15_serie": "IBGE IPCA-15: série histórica do índice geral (desde 2000)",
    "ibge_ipca_grupos": "IBGE IPCA: grupos, subgrupos, itens e subitens (desde 2006)",
    "ibge_inpc_grupos": "IBGE INPC: grupos, subgrupos, itens e subitens (desde 2012)",
    "ibge_ipca15_grupos": "IBGE IPCA-15: grupos, subgrupos, itens e subitens (desde 2012)",
}


def _params_precos(cls, *, grupos: bool) -> List[SourceParameterSpec]:
    piso = cls.PRIMEIRO_ANO if not grupos else cls.TABELAS[0][0]
    params = [
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
            description="Optional export format for the price table.",
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year",
            phase="coleta",
            param_type="integer",
            description=f"Primeiro ano (a série começa em {piso}). Cada ano traz até 12 meses.",
            required=True,
            default=None,
            minimum=piso,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Último ano (padrão: igual a start_year).",
            required=False,
            default=None,
            minimum=piso,
        ),
    ]
    if grupos:
        params += [
            SourceParameterSpec(
                name="level",
                phase="coleta",
                param_type="string",
                description=(
                    "Nível territorial: brasil, municipio (capitais e municípios da pesquisa) "
                    "ou regiao_metropolitana."
                ),
                required=False,
                default="brasil",
                allowed_values=list(NIVEIS_GRUPOS),
            ),
            SourceParameterSpec(
                name="detalhe",
                phase="coleta",
                param_type="string",
                description=(
                    "grupos (índice geral e os nove grupos, padrão), saude (grupo Saúde e "
                    "cuidados pessoais e seus subgrupos) ou todos (também itens e subitens; "
                    "fora do Brasil o volume é grande)."
                ),
                required=False,
                default="grupos",
                allowed_values=list(DETALHES),
            ),
        ]
    params += [
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description="Se true, salva o JSON bruto da resposta.",
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="HTTP timeout in seconds.",
            required=False,
            default=cls.DEFAULT_TIMEOUT,
            minimum=1,
        ),
        SourceParameterSpec(
            name="api_base_url",
            phase="tecnica",
            param_type="string",
            description="Optional IBGE API base URL override.",
            required=False,
            default=None,
        ),
    ]
    return params


def build_sources() -> List[DownloadSource]:
    sources: List[DownloadSource] = []
    for grupos, classes in ((False, PRECOS_SERIE_SOURCES), (True, PRECOS_GRUPOS_SOURCES)):
        for cls in classes:
            chave = cls().name
            sources.append(
                ApiDownloadSource(
                    descriptor=SourceDescriptor(
                        source=chave, title=_TITULOS[chave], mode="ibge api"
                    ),
                    datasource_cls=cls,
                    params_schema=_params_precos(cls, grupos=grupos),
                    normalize_params=_normalize_ibge_params,
                )
            )
    for spec in ibge_perfil.SPECS:
        sources.append(http_file_source(spec, ibge_perfil.MODES[spec.key]))
    for pesquisa in PESQUISAS_CENSOS:
        sources.append(
            ApiDownloadSource(
                descriptor=SourceDescriptor(
                    source=pesquisa.key, title=pesquisa.title, mode="ibge microdados"
                ),
                datasource_cls=datasource_for_pesquisa(pesquisa),
                params_schema=_params_microdados(pesquisa),
            )
        )
    return sources
