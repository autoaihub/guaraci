"""Fontes INPE (Queimadas) do registro padrao."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.inpe.queimadas import UF_TO_STATE
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_inpe_queimadas_params


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes INPE na ordem canonica."""
    current_year = datetime.now().year
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="inpe_queimadas",
                title="INPE Queimadas (Focos de Incêndio)",
                mode="inpe queimadas api",
            ),
            datasource_cls=_downloads.InpeQueimadasDataSource,
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
                    description="Optional export format for the fire-spot detections.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial (desde "
                        f"{_downloads.InpeQueimadasDataSource.MIN_YEAR}, "
                        "confirmado ao vivo)."
                    ),
                    required=True,
                    default=None,
                    minimum=_downloads.InpeQueimadasDataSource.MIN_YEAR,
                    maximum=current_year + 1,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (padrão: igual a start_year).",
                    required=False,
                    default=None,
                    minimum=_downloads.InpeQueimadasDataSource.MIN_YEAR,
                    maximum=current_year + 1,
                ),
                SourceParameterSpec(
                    name="months",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Meses (1-12) opcionais para granularidade mensal. Muda "
                        "para o produto 'mensal/Brasil' do INPE (disponível "
                        "apenas a partir de 2023, com colunas diferentes do "
                        "produto anual - inclui risco_fogo, frp, precipitacao). "
                        "Quando informado, o parâmetro 'dataset' é ignorado."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="dataset",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "referencia_anual = Brasil_sat_ref (produto de "
                        "referência, um satélite); todos_satelites = "
                        "Brasil_todos_sats (todos os satélites que o INPE "
                        "ingere). Ignorado quando 'months' é informado."
                    ),
                    required=False,
                    default=_downloads.InpeQueimadasDataSource.DEFAULT_DATASET,
                    allowed_values=list(
                        _downloads.InpeQueimadasDataSource.VALID_DATASETS
                    ),
                ),
                SourceParameterSpec(
                    name="states",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Filtro opcional por UF (aplicado após o download, "
                        "coluna 'estado'; o arquivo baixado é sempre Brasil "
                        "inteiro). Aceita sigla (ex.: 'SP') ou nome completo."
                    ),
                    required=False,
                    default=None,
                    allowed_values=sorted(UF_TO_STATE.keys()),
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva os arquivos brutos além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.InpeQueimadasDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional INPE Queimadas file-server base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_inpe_queimadas_params,
        ),
    ]
