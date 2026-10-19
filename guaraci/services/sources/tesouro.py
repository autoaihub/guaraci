"""Fontes do Tesouro Nacional (SICONFI) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.tesouro import SiconfiDcaDespesaFuncaoDataSource as _Dca
from guaraci.tesouro.rreo import SiconfiRreoSaudeDataSource as _Rreo

#: Último ano completo publicado, conferido ao vivo em 2026-10-19 (DCA com 625 linhas de SP em 2025 e nenhuma em 2026; RREO de 2026 ainda sem o 6o bimestre).
#: Padrão de ``start_year``: a coleta sem ano fica leve. Microdados pesados
#: (PNAD, PNS, POF, PeNSE) ficam sem padrão de propósito.
ANO_PADRAO = 2025


def _normalize_siconfi_params(params):
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
    funcao = normalized.get("funcao")
    if isinstance(funcao, str):
        normalized["funcao"] = funcao.strip().lower() or _Dca.DEFAULT_FUNCAO
    return normalized


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes do Tesouro (SICONFI) na ordem canônica."""
    current_year = datetime.now().year
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Dca.DATASET,
                title="SICONFI DCA - Despesa por Função (Saúde)",
                mode="siconfi api",
            ),
            datasource_cls=_Dca,
            params_schema=[
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
                    description=f"Exercício inicial (desde {_Dca.MIN_YEAR}, confirmado ao vivo; padrão {ANO_PADRAO}).",
                    required=True, default=ANO_PADRAO,
                    minimum=_Dca.MIN_YEAR, maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year", phase="coleta", param_type="integer",
                    description="Exercício final (padrão: igual a start_year).",
                    required=False, default=None,
                    minimum=_Dca.MIN_YEAR, maximum=current_year,
                ),
                SourceParameterSpec(
                    name="uf", phase="coleta", param_type="string_list",
                    description=(
                        "Siglas de UF para filtrar os entes (município e estado). "
                        "Sem uf nem entes, varre os ~5,6 mil entes (uma requisição "
                        "por ente e ano)."
                    ),
                    required=False, default=None,
                ),
                SourceParameterSpec(
                    name="entes", phase="coleta", param_type="string_list",
                    description="Códigos IBGE dos entes (ex.: 3550308). Tem precedência sobre uf.",
                    required=False, default=None,
                ),
                SourceParameterSpec(
                    name="funcao", phase="coleta", param_type="string",
                    description=(
                        "Código da função orçamentária, filtro local sobre a conta "
                        "(padrão 10 = Saúde). 'todas' desliga o filtro."
                    ),
                    required=False, default=_Dca.DEFAULT_FUNCAO,
                ),
                SourceParameterSpec(
                    name="keep_raw", phase="tecnica", param_type="boolean",
                    description="Se true, guarda as respostas da API (JSONL, sem filtro de função).",
                    required=False, default=False,
                ),
                SourceParameterSpec(
                    name="timeout", phase="tecnica", param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False, default=_Dca.DEFAULT_TIMEOUT, minimum=1,
                ),
                SourceParameterSpec(
                    name="pause_ms", phase="tecnica", param_type="integer",
                    description="Pausa entre requisições, em milissegundos, para a varredura nacional.",
                    required=False, default=0, minimum=0,
                ),
                SourceParameterSpec(
                    name="api_base_url", phase="tecnica", param_type="string",
                    description="Optional SICONFI API base URL override.",
                    required=False, default=None,
                ),
            ],
            normalize_params=_normalize_siconfi_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=_Rreo.DATASET,
                title="SICONFI RREO - Despesa em Saúde (Anexo 02)",
                mode="siconfi api",
            ),
            datasource_cls=_Rreo,
            params_schema=[
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
                    description=f"Exercício inicial (desde {_Rreo.MIN_YEAR}, confirmado ao vivo; padrão {ANO_PADRAO}).",
                    required=True, default=ANO_PADRAO,
                    minimum=_Rreo.MIN_YEAR, maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year", phase="coleta", param_type="integer",
                    description="Exercício final (padrão: igual a start_year).",
                    required=False, default=None,
                    minimum=_Rreo.MIN_YEAR, maximum=current_year,
                ),
                SourceParameterSpec(
                    name="periodos", phase="coleta", param_type="string_list",
                    description="Bimestres de 1 a 6 (padrão: todos).",
                    required=False, default=None,
                ),
                SourceParameterSpec(
                    name="uf", phase="coleta", param_type="string_list",
                    description="Siglas de UF para filtrar os entes (município e estado).",
                    required=False, default=None,
                ),
                SourceParameterSpec(
                    name="entes", phase="coleta", param_type="string_list",
                    description="Códigos IBGE dos entes (ex.: 3550308). Tem precedência sobre uf.",
                    required=False, default=None,
                ),
                SourceParameterSpec(
                    name="conta", phase="coleta", param_type="string",
                    description="Função do Anexo 02 mantida (filtro local; padrão Saúde, vazio desliga).",
                    required=False, default=_Rreo.DEFAULT_CONTA,
                ),
                SourceParameterSpec(
                    name="keep_raw", phase="tecnica", param_type="boolean",
                    description="Se true, guarda as respostas da API (JSONL, sem filtro).",
                    required=False, default=False,
                ),
                SourceParameterSpec(
                    name="timeout", phase="tecnica", param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False, default=_Rreo.DEFAULT_TIMEOUT, minimum=1,
                ),
                SourceParameterSpec(
                    name="pause_ms", phase="tecnica", param_type="integer",
                    description="Pausa entre requisições, em milissegundos.",
                    required=False, default=0, minimum=0,
                ),
                SourceParameterSpec(
                    name="api_base_url", phase="tecnica", param_type="string",
                    description="Optional SICONFI API base URL override.",
                    required=False, default=None,
                ),
            ],
            normalize_params=_normalize_siconfi_params,
        ),
    ]
