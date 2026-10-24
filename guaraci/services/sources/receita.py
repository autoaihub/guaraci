"""Fontes da Receita Federal: CNPJ aberto por WebDAV."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.receita.cnpj import (
    CNPJ_FILES,
    CNPJ_TABELAS,
    MIN_COMPETENCIA,
    PARTES,
    datasource_for,
)
from guaraci.receita.webdav import DEFAULT_TOKEN, ReceitaWebDavClient
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

_MODE = "receita webdav files"


def _common() -> List[SourceParameterSpec]:
    return [
        SourceParameterSpec(
            name="competencia",
            phase="coleta",
            param_type="string",
            description=(
                f"Competência `AAAA-MM` (desde {MIN_COMPETENCIA}). Omita para a mais recente "
                "que traz todos os arquivos pedidos."
            ),
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="token",
            phase="tecnica",
            param_type="string",
            description=(
                "Token do compartilhamento público do Nextcloud da Receita (usuário do WebDAV, "
                "senha vazia). O padrão vale hoje; se a Receita trocar o link, passe o novo."
            ),
            required=False,
            default=DEFAULT_TOKEN,
        ),
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
                "Exporta em CSV UTF-8, Parquet ou SQLite (um arquivo por parte), com todas as "
                "colunas como texto e os nomes do leiaute oficial. Omita para guardar o zip "
                "como a Receita publica."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description="Se true, mantém o zip original além da exportação.",
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="Timeout de rede em segundos.",
            required=False,
            default=ReceitaWebDavClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
    ]


def _params(key: str) -> List[SourceParameterSpec]:
    spec = CNPJ_FILES[key]
    extra: List[SourceParameterSpec] = []
    if spec.tabelas:
        extra.append(
            SourceParameterSpec(
                name="tabelas",
                phase="coleta",
                param_type="string_list",
                description="Tabelas de domínio (uma saída cada). Omita para as seis.",
                required=False,
                default=None,
                allowed_values=list(CNPJ_TABELAS),
            )
        )
    elif spec.multipart:
        extra.append(
            SourceParameterSpec(
                name="partes",
                phase="coleta",
                param_type="string_list",
                description=(
                    "Partes do cadastro (0 a 9). Cada competência soma de 6 a 8 GB comprimidos "
                    "nas três famílias; a parte 0 de estabelecimentos tem mais de 2 GB. Omita "
                    "para todas."
                ),
                required=False,
                default=None,
                allowed_values=[str(n) for n in PARTES],
            )
        )
    return [*extra, *_common()]


def build_sources() -> List[DownloadSource]:
    """Cinco fontes do CNPJ da Receita (WebDAV)."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODE),
            datasource_cls=datasource_for(spec.key),
            params_schema=_params(spec.key),
        )
        for spec in CNPJ_FILES.values()
    ]
