"""Fontes CKAN federais (MMA e INSS) e o construtor genérico ``ckan_api_source``.

``ckan_api_source`` também serve aos portais estaduais (Pacote G): recebe uma
:class:`~guaraci.ckan.datasets.CkanDataset` e devolve a fonte pronta.
O registro deste módulo em ``sources/__init__.py`` é do orquestrador.
"""

from typing import List

from guaraci.ckan import CkanClient, CkanDataset, ckan_datasource_for
from guaraci.ckan.federal import CKAN_FEDERAL
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

DEFAULT_MODE = "ckan files"


def _params(spec: CkanDataset) -> List[SourceParameterSpec]:
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
            description=(
                "Exporta em CSV UTF-8, Parquet ou SQLite, com todas as colunas como texto e "
                "nomes de coluna como publicados (um arquivo por recurso ou por membro do zip). "
                "Omita para guardar o arquivo como o portal publica."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description="Se true, mantém o arquivo original além da exportação.",
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="HTTP timeout in seconds.",
            required=False,
            default=CkanClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
        SourceParameterSpec(
            name="recursos",
            phase="coleta",
            param_type="string_list",
            description=(
                "Trechos do id, nome ou URL do recurso; só os que casam são baixados. "
                "Omita para o padrão da chave."
            ),
            required=False,
            default=None,
        ),
    ]
    if spec.has_period:
        if spec.period_required:
            anos_text = "Anos a baixar (obrigatório). Os arquivos são grandes: peça poucos por vez."
        elif spec.default_latest:
            anos_text = "Anos a baixar. Sem 'anos' nem 'meses', baixa só o período mais novo."
        else:
            anos_text = "Anos a baixar. Omita para todos os recursos."
        params[:0] = [
            SourceParameterSpec(
                name="anos",
                phase="coleta",
                param_type="string_list",
                description=anos_text,
                required=spec.period_required,
                default=None,
            ),
            SourceParameterSpec(
                name="meses",
                phase="coleta",
                param_type="string_list",
                description=(
                    "Meses (01 a 12) dentro dos anos pedidos. Omita para o ano inteiro."
                ),
                required=False,
                default=None,
                allowed_values=[f"{m:02d}" for m in range(1, 13)],
            ),
        ]
        params.extend(
            [
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial da janela (alternativa a 'anos').",
                    required=False,
                    default=None,
                    minimum=1900,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final da janela (padrão: igual a start_year).",
                    required=False,
                    default=None,
                    minimum=1900,
                ),
            ]
        )
    return params


def ckan_api_source(spec: CkanDataset, mode: str = DEFAULT_MODE) -> ApiDownloadSource:
    """Fonte da API para uma spec CKAN (``anos``/``meses`` só quando a spec tem período)."""
    return ApiDownloadSource(
        descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=mode),
        datasource_cls=ckan_datasource_for(spec),
        params_schema=_params(spec),
    )


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes CKAN federais (MMA e INSS) na ordem de ``CKAN_FEDERAL``."""
    return [ckan_api_source(spec) for spec in CKAN_FEDERAL.values()]
