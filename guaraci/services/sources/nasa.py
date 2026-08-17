"""Fontes NASA (POWER, FIRMS, GPM IMERG) do registro padrao."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import (
    _normalize_nasa_firms_params,
    _normalize_nasa_gpm_params,
    _normalize_nasa_power_params,
)


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes NASA na ordem canonica."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="nasa_power",
                title="NASA POWER (Clima)",
                mode="nasa power api",
            ),
            datasource_cls=_downloads.NasaPowerDataSource,
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
                    description="Optional export format for the climate series.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="latitude",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Latitude do ponto (-90 a 90, decimal). "
                        "Ex.: -23.55 para São Paulo."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="longitude",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Longitude do ponto (-180 a 180, decimal). "
                        "Ex.: -46.63 para São Paulo."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Data inicial (YYYY-MM-DD). Cobertura diária do "
                        "POWER desde 1981."
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
                    name="parameters",
                    phase="coleta",
                    param_type="string_list",
                    description="Variáveis climáticas NASA POWER a coletar.",
                    required=False,
                    default=list(_downloads.NasaPowerDataSource.DEFAULT_PARAMETERS),
                    allowed_values=list(
                        _downloads.NasaPowerDataSource.SUPPORTED_PARAMETERS.keys()
                    ),
                ),
                SourceParameterSpec(
                    name="temporal",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Resolução temporal: daily (diário) ou "
                        "monthly (mensal)."
                    ),
                    required=False,
                    default=_downloads.NasaPowerDataSource.DEFAULT_TEMPORAL,
                    allowed_values=list(_downloads.NasaPowerDataSource.VALID_TEMPORAL),
                ),
                SourceParameterSpec(
                    name="community",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Comunidade POWER: AG (agroclima), "
                        "RE (energia renovável), SB (edificações)."
                    ),
                    required=False,
                    default=_downloads.NasaPowerDataSource.DEFAULT_COMMUNITY,
                    allowed_values=list(_downloads.NasaPowerDataSource.VALID_COMMUNITIES),
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description=(
                        "Se true, salva o JSON bruto da resposta além "
                        "da exportação."
                    ),
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.NasaPowerDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional NASA POWER API base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_nasa_power_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="nasa_firms",
                title="NASA FIRMS (Focos de Incêndio)",
                mode="nasa firms api",
            ),
            datasource_cls=_downloads.NasaFirmsDataSource,
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
                    description="Optional export format for the detections.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="coleta",
                    param_type="string",
                    description="Data inicial (YYYY-MM-DD).",
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Data final (YYYY-MM-DD). Janelas longas são "
                        "fatiadas em blocos de até 10 dias."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="product",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Produto de satélite FIRMS, a 'source' da API (NRT = "
                        "quase tempo real; SP = processamento padrão/arquivo)."
                    ),
                    required=False,
                    default=_downloads.NasaFirmsDataSource.DEFAULT_PRODUCT,
                    allowed_values=list(_downloads.NasaFirmsDataSource.VALID_PRODUCTS),
                ),
                SourceParameterSpec(
                    name="country",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Código ISO de 3 letras do país (padrão BRA). "
                        "Ignorado quando 'area' é informado."
                    ),
                    required=False,
                    default=_downloads.NasaFirmsDataSource.DEFAULT_COUNTRY,
                ),
                SourceParameterSpec(
                    name="area",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Caixa delimitadora opcional 'oeste,sul,leste,norte' "
                        "ou 'world'; tem precedência sobre 'country'."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva o CSV bruto além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.NasaFirmsDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional NASA FIRMS API base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_nasa_firms_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="nasa_gpm",
                title="NASA GPM IMERG (Precipitação)",
                mode="nasa gpm api",
            ),
            datasource_cls=_downloads.NasaGpmDataSource,
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
                    name="latitude",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Latitude do ponto (-90 a 90, decimal). "
                        "Ex.: -23.55 para São Paulo."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="longitude",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Longitude do ponto (-180 a 180, decimal). "
                        "Ex.: -46.63 para São Paulo."
                    ),
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Data inicial (YYYY-MM-DD). Uma requisição OPeNDAP "
                        "por dia; janela limitada a ~1 ano."
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
                    description="Variável IMERG (diária GPM_3IMERGDF V07).",
                    required=False,
                    default=_downloads.NasaGpmDataSource.DEFAULT_VARIABLE,
                    allowed_values=list(_downloads.NasaGpmDataSource.VALID_VARIABLES),
                ),
                SourceParameterSpec(
                    name="product",
                    phase="coleta",
                    param_type="string",
                    description="Produto temporal IMERG (apenas 'daily' por ora).",
                    required=False,
                    default=_downloads.NasaGpmDataSource.DEFAULT_PRODUCT,
                    allowed_values=list(_downloads.NasaGpmDataSource.VALID_PRODUCTS),
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva as respostas OPeNDAP brutas.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.NasaGpmDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional GES DISC OPeNDAP base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_nasa_gpm_params,
        ),
    ]
