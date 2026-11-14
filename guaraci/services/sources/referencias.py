"""Fontes de tabelas oficiais de códigos (chaves de cruzamento entre bases)."""

from typing import List, Optional, Type

from guaraci.core.contracts import SourceParameterSpec
from guaraci.referencias import (
    Cid10DataSource,
    CnaeClassesDataSource,
    CnaeSubclassesDataSource,
    IbgeDistritosDataSource,
    IbgeMunicipiosDataSource,
    SigtapDataSource,
    TseMunicipiosDataSource,
)
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def _basicos(timeout_default: int) -> List[SourceParameterSpec]:
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
    ]


def _fonte(cls: Type, title: str, mode: str, extra: Optional[List[SourceParameterSpec]] = None) -> ApiDownloadSource:
    return ApiDownloadSource(
        descriptor=SourceDescriptor(source=cls.DATASET, title=title, mode=mode),
        datasource_cls=cls,
        params_schema=_basicos(cls.DEFAULT_TIMEOUT) + (extra or []),
    )


_API_BASE = SourceParameterSpec(
    name="api_base_url", phase="tecnica", param_type="string",
    description="Optional IBGE API base URL override.",
    required=False, default=None,
)
_URL = SourceParameterSpec(
    name="url", phase="tecnica", param_type="string",
    description="Optional URL override of the source zip.",
    required=False, default=None,
)
_SIGTAP = [
    SourceParameterSpec(
        name="competencia", phase="coleta", param_type="string",
        description="Competência AAAAMM do SIGTAP (um zip por mês); padrão: a mais recente do FTP.",
        required=False, default=None,
    ),
    SourceParameterSpec(
        name="tabelas", phase="coleta", param_type="string_list",
        description=(
            "Tabelas do zip (por exemplo tb_procedimento, tb_cid, tb_ocupacao, "
            "rl_procedimento_cid, rl_procedimento_compativel); padrão: todas."
        ),
        required=False, default=None,
    ),
    SourceParameterSpec(
        name="ftp_host", phase="tecnica", param_type="string",
        description="Optional FTP host override (padrão ftp2.datasus.gov.br).",
        required=False, default=None,
    ),
]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes de tabelas de códigos na ordem canônica."""
    return [
        _fonte(IbgeMunicipiosDataSource, "IBGE - Municípios e divisão territorial (localidades)",
               "referencias json", [_API_BASE]),
        _fonte(IbgeDistritosDataSource, "IBGE - Distritos e divisão territorial (localidades)",
               "referencias json", [_API_BASE]),
        _fonte(SigtapDataSource, "DATASUS - SIGTAP, Tabela Unificada de procedimentos do SUS",
               "referencias ftp", _SIGTAP),
        _fonte(Cid10DataSource, "DATASUS - CID-10 (capítulos, grupos, categorias e subcategorias)",
               "referencias zip csv", [_URL]),
        _fonte(CnaeSubclassesDataSource, "IBGE/CONCLA - CNAE subclasses com a hierarquia até a seção",
               "referencias json", [_API_BASE]),
        _fonte(CnaeClassesDataSource, "IBGE/CONCLA - CNAE classes com a hierarquia até a seção",
               "referencias json", [_API_BASE]),
        _fonte(TseMunicipiosDataSource, "TSE - Equivalência de códigos de município com o IBGE",
               "referencias zip csv", [_URL]),
    ]
