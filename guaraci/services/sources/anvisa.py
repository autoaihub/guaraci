"""Fontes ANVISA (arquivos de dados abertos) do registro padrão."""

from typing import List

from guaraci.anvisa import ANVISA_FILES, AnvisaClient, datasource_for
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def _params() -> List[SourceParameterSpec]:
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
                "Exporta em CSV UTF-8, Parquet ou SQLite, com todas as colunas "
                "como texto (as datas mudam de formato entre arquivos). Omita "
                "para guardar o arquivo como a ANVISA publica (cp1252, ';')."
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
            default=AnvisaClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
        SourceParameterSpec(
            name="api_base_url",
            phase="tecnica",
            param_type="string",
            description="Optional dados.anvisa.gov.br/dados/ base URL override.",
            required=False,
            default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes ANVISA na ordem do registro de arquivos."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source=spec.key,
                title=spec.title,
                mode="anvisa files",
            ),
            datasource_cls=datasource_for(spec.key),
            params_schema=_params(),
        )
        for spec in ANVISA_FILES.values()
    ]
