"""Fontes de arquivos HTTP de URL fixa (Vigitel, IBAMA, Farmácia Popular)."""

from typing import List

from guaraci.arquivos import FARMACIA_INDICADORES, HTTP_FILES, HttpFileClient, datasource_for
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

_MODES = {
    "vigitel": "svs files",
    "ibama_agrotoxicos_comercializacao": "ibama files",
    "farmacia_popular_indicadores": "demas s3 files",
}


def _params(key: str) -> List[SourceParameterSpec]:
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
                "Exporta em CSV UTF-8, Parquet ou SQLite, com todas as colunas "
                "como texto e nomes de coluna como publicados. Omita para guardar "
                "o arquivo como a fonte publica."
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
            default=HttpFileClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
    ]
    if HTTP_FILES[key].selector == "indicadores":
        params.insert(
            0,
            SourceParameterSpec(
                name="indicadores",
                phase="coleta",
                param_type="string_list",
                description=(
                    "Códigos dos indicadores (um CSV por indicador). Omita para "
                    "baixar todos os 14."
                ),
                required=False,
                default=None,
                allowed_values=list(FARMACIA_INDICADORES),
            ),
        )
    return params


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes de arquivo HTTP na ordem de ``HTTP_FILES``."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODES[spec.key]),
            datasource_cls=datasource_for(spec.key),
            params_schema=_params(spec.key),
        )
        for spec in HTTP_FILES.values()
    ]
