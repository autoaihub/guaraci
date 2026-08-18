"""Fonte ANA / SNIRH HidroWebService (telemetria hidrológica) do registro padrao."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_ana_hidro_params


def build_sources() -> List[DownloadSource]:
    """Retorna a fonte ANA HidroWebService na ordem canonica."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="ana_hidro",
                title="ANA HidroWebService (Estações Telemétricas)",
                mode="ana hidro api",
            ),
            datasource_cls=_downloads.AnaHidroDataSource,
            params_schema=[
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
                    description="Optional export format for the series.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="station_ids",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Códigos das estações telemétricas ANA/SNIRH "
                        "(obrigatório; não há varredura automática — é "
                        "preciso saber a estação de antemão)."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Data inicial (YYYY-MM-DD). Internamente fatiada em "
                        "blocos de até 30 dias por requisição (limite da "
                        "API telemétrica)."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="coleta",
                    param_type="string",
                    description="Data final (YYYY-MM-DD).",
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="variable",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Variável hidrológica de interesse: chuvas, vazoes "
                        "ou cotas (nível). A API retorna as leituras "
                        "combinadas por estação; este campo apenas rotula "
                        "a requisição/saída."
                    ),
                    required=True,
                    default=None,
                    allowed_values=list(
                        _downloads.AnaHidroDataSource.VALID_VARIABLES
                    ),
                ),
                SourceParameterSpec(
                    name="detail",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "adotada = leituras consistidas; detalhada = "
                        "inclui também os dados brutos dos sensores."
                    ),
                    required=False,
                    default=_downloads.AnaHidroDataSource.DEFAULT_DETAIL,
                    allowed_values=list(
                        _downloads.AnaHidroDataSource.VALID_DETAILS
                    ),
                ),
                SourceParameterSpec(
                    name="tipo_filtro_data",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Critério de filtro de data da API: DATA_LEITURA ou "
                        "DATA_ULTIMA_ATUALIZACAO."
                    ),
                    required=False,
                    default=_downloads.AnaHidroDataSource.DEFAULT_TIPO_FILTRO_DATA,
                    allowed_values=list(
                        _downloads.AnaHidroDataSource.VALID_TIPO_FILTRO_DATA
                    ),
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva o JSON bruto das respostas.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.AnaHidroDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional ANA HidroWebService base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_ana_hidro_params,
        ),
    ]
