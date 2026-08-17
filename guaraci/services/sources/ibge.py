"""Fontes IBGE (SIDRA) do registro padrao."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_ibge_params


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes IBGE na ordem canonica."""
    current_year = datetime.now().year
    last_year = current_year - 1
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="ibge_populacao",
                title="IBGE População Estimada",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgePopulacaoDataSource,
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
                    description="Optional export format for the population table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial das estimativas de população "
                        "(IBGE SIDRA tabela 6579, desde 2001)."
                    ),
                    required=False,
                    default=last_year,
                    minimum=2001,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final das estimativas de população.",
                    required=False,
                    default=last_year,
                    minimum=2001,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Nível territorial: municipio, uf, regiao ou brasil."
                    ),
                    required=False,
                    default=_downloads.IbgePopulacaoDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva o JSON bruto da resposta.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.IbgePopulacaoDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional IBGE API base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_ibge_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="ibge_pib_municipios",
                title="IBGE PIB dos Municípios",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgePibMunicipiosDataSource,
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
                    description="Optional export format for the GDP table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial do PIB municipal (IBGE SIDRA 5938, desde 2002).",
                    required=False,
                    default=last_year,
                    minimum=2002,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final do PIB municipal.",
                    required=False,
                    default=last_year,
                    minimum=2002,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description="Nível territorial: municipio, uf, regiao ou brasil.",
                    required=False,
                    default="municipio",
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva o JSON bruto da resposta.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.IbgePibMunicipiosDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional IBGE API base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_ibge_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="ibge_populacao_idade_sexo",
                title="IBGE População por Idade e Sexo (Censo)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgePopulacaoIdadeSexoDataSource,
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
                    description="Optional export format for the age/sex table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial (população por idade/sexo do Censo, "
                        "IBGE SIDRA 9514; referência 2022)."
                    ),
                    required=False,
                    default=2022,
                    minimum=2010,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final.",
                    required=False,
                    default=2022,
                    minimum=2010,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description="Nível territorial: uf, municipio, regiao ou brasil.",
                    required=False,
                    default="uf",
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="sexo",
                    phase="coleta",
                    param_type="string",
                    description="Recorte de sexo: ambos, homens, mulheres ou total.",
                    required=False,
                    default="ambos",
                    allowed_values=["ambos", "homens", "mulheres", "total"],
                ),
                SourceParameterSpec(
                    name="faixa_etaria",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte de idade: quinquenal (grupos de 5 anos), "
                        "total ou todos (todas as idades detalhadas)."
                    ),
                    required=False,
                    default="quinquenal",
                    allowed_values=["quinquenal", "total", "todos"],
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva o JSON bruto da resposta.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="timeout",
                    phase="tecnica",
                    param_type="integer",
                    description="HTTP timeout in seconds.",
                    required=False,
                    default=_downloads.IbgePopulacaoIdadeSexoDataSource.DEFAULT_TIMEOUT,
                    minimum=1,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description="Optional IBGE API base URL override.",
                    required=False,
                    default=None,
                ),
            ],
            normalize_params=_normalize_ibge_params,
        ),
    ]
