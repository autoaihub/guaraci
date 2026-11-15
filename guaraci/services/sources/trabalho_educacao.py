"""Fontes da leva 7 de trabalho e educação: indicadores INEP e tabelas do Censo Escolar.

RAIS e CAGED históricos ficam em ``mte_historico``; IDEB de escola e de Brasil/UFs
(``inep_ideb.EXTRA_SPECS``) também saem daqui.
"""

from dataclasses import replace
from typing import List

from guaraci.arquivos import inep_ideb, inep_indicadores
from guaraci.arquivos.inep_censo_escolar import (
    INEP_CENSO_ESCOLAR_TABELAS,
    MIN_TABELAS_YEAR,
    latest_year,
    tabela_datasource_for,
)
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import ApiDownloadSource, DownloadSource, SourceDescriptor
from guaraci.services.sources import inep
from guaraci.services.sources import tesouro
from guaraci.services.sources.arquivos import http_file_source
from guaraci.tesouro.anexos import SiconfiDcaAnexosDataSource, SiconfiRreoAnexosDataSource


def _censo_params() -> List[SourceParameterSpec]:
    last = max(latest_year(), MIN_TABELAS_YEAR)
    params: List[SourceParameterSpec] = []
    for spec in inep.build_sources()[0].params_schema():
        if spec.name in ("start_year", "end_year"):
            spec = replace(spec, minimum=MIN_TABELAS_YEAR, maximum=last)
            spec = replace(
                spec,
                description=(
                    f"Ano (desde {MIN_TABELAS_YEAR}, o primeiro zip com esta tabela)."
                    if spec.name == "start_year"
                    else "Ano final (padrão: igual a start_year)."
                ),
            )
        params.append(spec)
    return params


def _siconfi_params(base_key: str, cls: type, anexos_help: str) -> List[SourceParameterSpec]:
    """Parâmetros da fonte SICONFI existente, com ``anexos`` no lugar do filtro de função."""
    base = next(s for s in tesouro.build_sources() if s.descriptor.source == base_key)
    params: List[SourceParameterSpec] = []
    for spec in base.params_schema():
        if spec.name in ("funcao", "conta"):
            continue
        if spec.name in ("start_year", "end_year"):
            spec = replace(spec, minimum=cls.MIN_YEAR)
        if spec.name == "start_year":
            spec = replace(
                spec,
                description=f"Exercício inicial (desde {cls.MIN_YEAR}; padrão {tesouro.ANO_PADRAO}).",
            )
        if spec.name == "keep_raw":
            spec = replace(spec, description="Se true, guarda as respostas da API (JSONL).")
        params.append(spec)
    params.insert(
        -4,
        SourceParameterSpec(
            name="anexos", phase="coleta", param_type="string_list",
            description=anexos_help, required=False, default=None,
        ),
    )
    return params


def build_sources() -> List[DownloadSource]:
    sources: List[DownloadSource] = [
        http_file_source(spec, inep_indicadores.MODES[spec.key], inep_indicadores.DATASOURCES[spec.key])
        for spec in inep_indicadores.SPECS
    ]
    sources.extend(
        http_file_source(spec, inep_ideb.MODES[spec.key]) for spec in inep_ideb.EXTRA_SPECS
    )
    sources.extend(
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=key, title=meta[1], mode="inep files"),
            datasource_cls=tabela_datasource_for(key),
            params_schema=_censo_params(),
        )
        for key, meta in INEP_CENSO_ESCOLAR_TABELAS.items()
    )
    sources.extend(
        [
            ApiDownloadSource(
                descriptor=SourceDescriptor(
                    source=SiconfiDcaAnexosDataSource.DATASET,
                    title="SICONFI DCA - Todos os anexos",
                    mode="siconfi api",
                ),
                datasource_cls=SiconfiDcaAnexosDataSource,
                params_schema=_siconfi_params(
                    "siconfi_dca_despesa_funcao",
                    SiconfiDcaAnexosDataSource,
                    "Anexos mantidos (ex.: I-AB, I-C, I-D, I-E, I-F, I-G, I-HI), filtro local; "
                    "omita para todos.",
                ),
                normalize_params=tesouro._normalize_siconfi_params,
            ),
            ApiDownloadSource(
                descriptor=SourceDescriptor(
                    source=SiconfiRreoAnexosDataSource.DATASET,
                    title="SICONFI RREO - Todos os anexos",
                    mode="siconfi api",
                ),
                datasource_cls=SiconfiRreoAnexosDataSource,
                params_schema=_siconfi_params(
                    "siconfi_rreo_saude",
                    SiconfiRreoAnexosDataSource,
                    "Anexos mantidos (ex.: 01, 02, 03, 04, 06, 07, 09, 10 - RPPS, 11, 13, 14), "
                    "filtro local; omita para todos.",
                ),
                normalize_params=tesouro._normalize_siconfi_params,
            ),
        ]
    )
    return sources
