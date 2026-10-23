"""Fontes de gestão pública (Transferegov e Obrasgov) do registro padrão."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.gestao_publica import (
    ObrasgovProjetosDataSource as _Obrasgov,
    TransferegovFundoAFundoDataSource as _FundoAFundo,
    TransferegovTransferenciasEspeciaisDataSource as _Especiais,
)
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


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
            name="pause_ms", phase="tecnica", param_type="integer",
            description="Pausa entre páginas, em milissegundos.",
            required=False, default=0, minimum=0,
        ),
        SourceParameterSpec(
            name="api_base_url", phase="tecnica", param_type="string",
            description="Optional API base URL override.",
            required=False, default=None,
        ),
    ]


def _transferegov(datasource_cls, title: str, tables_hint: str) -> ApiDownloadSource:
    params = _technical(datasource_cls.DEFAULT_TIMEOUT) + [
        SourceParameterSpec(
            name="tabelas", phase="coleta", param_type="string_list",
            description=(
                "Tabelas da API PostgREST, uma saída por tabela (padrão: todas). "
                + tables_hint
            ),
            required=False, default=None,
        ),
    ]
    return ApiDownloadSource(
        descriptor=SourceDescriptor(
            source=datasource_cls.DATASET, title=title, mode="transferegov api"
        ),
        datasource_cls=datasource_cls,
        params_schema=params,
    )


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes de gestão pública na ordem canônica."""
    obras_params = _technical(_Obrasgov.DEFAULT_TIMEOUT) + [
        SourceParameterSpec(
            name="tamanho_pagina", phase="tecnica", param_type="integer",
            description="Projetos por página (padrão 100; páginas grandes estouram o tempo da API).",
            required=False, default=_Obrasgov.PAGE_SIZE, minimum=1,
        ),
        SourceParameterSpec(
            name="max_paginas", phase="tecnica", param_type="integer",
            description="Interrompe a leitura após N páginas (padrão: até a página vazia).",
            required=False, default=None, minimum=1,
        ),
    ]
    return [
        _transferegov(
            _Especiais,
            "Transferegov - Transferências Especiais (emendas Pix)",
            "Ex.: plano_acao_especial, empenho_especial, programa_especial.",
        ),
        _transferegov(
            _FundoAFundo,
            "Transferegov - Fundo a Fundo",
            "Ex.: plano_acao, programa, empenho, relatorio_gestao.",
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Obrasgov.DATASET,
                title="Obrasgov - Projetos de investimento",
                mode="obrasgov api",
            ),
            datasource_cls=_Obrasgov,
            params_schema=obras_params,
        ),
    ]
