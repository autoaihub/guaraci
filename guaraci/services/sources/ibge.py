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
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="ibge_nascidos_vivos_rc",
                title="IBGE Nascidos Vivos (Registro Civil)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeNascidosVivosRcDataSource,
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
                    description="Optional export format for the live births table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial dos nascidos vivos (IBGE SIDRA tabela 2680, "
                        "registro civil, desde 2003)."
                    ),
                    required=False,
                    default=last_year,
                    minimum=2003,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final dos nascidos vivos.",
                    required=False,
                    default=last_year,
                    minimum=2003,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Nível territorial: municipio, uf, regiao ou brasil. "
                        "Com mes != total, apenas uf/regiao/brasil são aceitos "
                        "(municipal x todos os meses excede o limite da SIDRA)."
                    ),
                    required=False,
                    default=_downloads.IbgeNascidosVivosRcDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="mes",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte de mês do nascimento: total (padrão, igual à "
                        "tabela anual 2679) ou all (quebra mensal; requer "
                        "level != municipio)."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
                ),
                SourceParameterSpec(
                    name="sexo",
                    phase="coleta",
                    param_type="string",
                    description="Recorte de sexo: total (padrão), ambos, homens ou mulheres.",
                    required=False,
                    default="total",
                    allowed_values=["total", "ambos", "homens", "mulheres"],
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
                    default=_downloads.IbgeNascidosVivosRcDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_obitos_rc",
                title="IBGE Óbitos (Registro Civil)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeObitosRcDataSource,
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
                    description="Optional export format for the deaths table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial dos óbitos (IBGE SIDRA tabela 2681, "
                        "registro civil, desde 2003)."
                    ),
                    required=False,
                    default=last_year,
                    minimum=2003,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final dos óbitos.",
                    required=False,
                    default=last_year,
                    minimum=2003,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Nível territorial: municipio, uf, regiao ou brasil. "
                        "Com mes != total, apenas uf/regiao/brasil são aceitos "
                        "(municipal x todos os meses excede o limite da SIDRA)."
                    ),
                    required=False,
                    default=_downloads.IbgeObitosRcDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="mes",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte de mês de ocorrência: total (padrão, igual à "
                        "tabela anual 2684) ou all (quebra mensal; requer "
                        "level != municipio)."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
                ),
                SourceParameterSpec(
                    name="sexo",
                    phase="coleta",
                    param_type="string",
                    description="Recorte de sexo: total (padrão), ambos, homens ou mulheres.",
                    required=False,
                    default="total",
                    allowed_values=["total", "ambos", "homens", "mulheres"],
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
                    default=_downloads.IbgeObitosRcDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_area_territorial",
                title="IBGE Área Territorial e Densidade",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeAreaTerritorialDataSource,
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
                    description="Optional export format for the area/density table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano da tabela (IBGE SIDRA 4714, área/densidade/população, "
                        "referência do Censo 2022 — único período publicado)."
                    ),
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (deve ser igual a start_year, 2022).",
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description="Nível territorial: municipio, uf, regiao ou brasil.",
                    required=False,
                    default=_downloads.IbgeAreaTerritorialDataSource.DEFAULT_LEVEL,
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
                    default=_downloads.IbgeAreaTerritorialDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_casamentos",
                title="IBGE Casamentos (Registro Civil)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeCasamentosDataSource,
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
                    description="Optional export format for the marriages table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial dos casamentos (IBGE SIDRA tabela 4406, "
                        "registro civil, desde 2013)."
                    ),
                    required=False,
                    default=last_year,
                    minimum=2013,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final dos casamentos.",
                    required=False,
                    default=last_year,
                    minimum=2013,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Nível territorial: municipio, uf, regiao ou brasil. "
                        "Com mes != total, apenas uf/regiao/brasil são aceitos "
                        "(municipal x todos os meses excede o limite da SIDRA)."
                    ),
                    required=False,
                    default=_downloads.IbgeCasamentosDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="mes",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte de mês do registro: total (padrão) ou all "
                        "(quebra mensal; requer level != municipio)."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
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
                    default=_downloads.IbgeCasamentosDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_divorcios",
                title="IBGE Divórcios (Registro Civil)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeDivorciosDataSource,
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
                    description="Optional export format for the divorces table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano inicial dos divórcios (IBGE SIDRA tabela 5937, "
                        "registro civil, desde 2014)."
                    ),
                    required=False,
                    default=last_year,
                    minimum=2014,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final dos divórcios.",
                    required=False,
                    default=last_year,
                    minimum=2014,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Nível territorial: municipio, uf, regiao ou brasil. "
                        "Com idade_marido/idade_mulher/tempo_decorrido != total, "
                        "apenas uf/regiao/brasil são aceitos (municipal x quebra "
                        "detalhada excede o limite da SIDRA)."
                    ),
                    required=False,
                    default=_downloads.IbgeDivorciosDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="idade_marido",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte por grupo de idade do marido na sentença: "
                        "total (padrão) ou all."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
                ),
                SourceParameterSpec(
                    name="idade_mulher",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte por grupo de idade da mulher na sentença: "
                        "total (padrão) ou all."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
                ),
                SourceParameterSpec(
                    name="tempo_decorrido",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte por tempo transcorrido entre casamento e "
                        "sentença: total (padrão) ou all."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
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
                    default=_downloads.IbgeDivorciosDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_saneamento_agua",
                title="IBGE Saneamento: Abastecimento de Água (Censo 2022)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeSaneamentoAguaDataSource,
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
                    description="Optional export format for the water supply table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano da tabela (IBGE SIDRA 6803, abastecimento de água, "
                        "referência do Censo 2022, único período publicado)."
                    ),
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (deve ser igual a start_year, 2022).",
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description="Nível territorial: municipio, uf, regiao ou brasil.",
                    required=False,
                    default=_downloads.IbgeSaneamentoAguaDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="detalhe",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte da forma de abastecimento de água: total "
                        "(padrão, 1 linha por localidade) ou all (18 categorias "
                        "detalhadas; requer level != municipio)."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
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
                    default=_downloads.IbgeSaneamentoAguaDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_saneamento_esgoto",
                title="IBGE Saneamento: Esgotamento Sanitário (Censo 2022)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeSaneamentoEsgotoDataSource,
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
                    description="Optional export format for the sewage table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano da tabela (IBGE SIDRA 6805, esgotamento sanitário, "
                        "referência do Censo 2022, único período publicado)."
                    ),
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (deve ser igual a start_year, 2022).",
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description="Nível territorial: municipio, uf, regiao ou brasil.",
                    required=False,
                    default=_downloads.IbgeSaneamentoEsgotoDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="detalhe",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte do tipo de esgotamento sanitário: total "
                        "(padrão, 1 linha por localidade) ou all (10 categorias "
                        "detalhadas; requer level != municipio)."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
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
                    default=_downloads.IbgeSaneamentoEsgotoDataSource.DEFAULT_TIMEOUT,
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
                source="ibge_saneamento_lixo",
                title="IBGE Saneamento: Destino do Lixo (Censo 2022)",
                mode="ibge api",
            ),
            datasource_cls=_downloads.IbgeSaneamentoLixoDataSource,
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
                    description="Optional export format for the garbage disposal table.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description=(
                        "Ano da tabela (IBGE SIDRA 6892, destino do lixo, "
                        "referência do Censo 2022, único período publicado)."
                    ),
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final (deve ser igual a start_year, 2022).",
                    required=False,
                    default=2022,
                    minimum=2022,
                    maximum=2022,
                ),
                SourceParameterSpec(
                    name="level",
                    phase="coleta",
                    param_type="string",
                    description="Nível territorial: municipio, uf, regiao ou brasil.",
                    required=False,
                    default=_downloads.IbgeSaneamentoLixoDataSource.DEFAULT_LEVEL,
                    allowed_values=["municipio", "uf", "regiao", "brasil"],
                ),
                SourceParameterSpec(
                    name="detalhe",
                    phase="coleta",
                    param_type="string",
                    description=(
                        "Recorte do destino do lixo: total (padrão, 1 linha "
                        "por localidade) ou all (8 categorias detalhadas; "
                        "aceito também em level=municipio, confirmado ao vivo)."
                    ),
                    required=False,
                    default="total",
                    allowed_values=["total", "all"],
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
                    default=_downloads.IbgeSaneamentoLixoDataSource.DEFAULT_TIMEOUT,
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
