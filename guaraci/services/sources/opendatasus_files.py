"""Fontes de bulk-file do portal dadosabertos.saude.gov.br (SRAG, SISAGUA).

Transporte diferente do OpenDataSUS "record-oriented" (CKAN datastore /
DEMAS paginado): aqui cada "dataset" e um pacote com poucos *resources* que
sao arquivos inteiros (CSV/Parquet) hospedados num bucket S3 publico. Ver
``guaraci/opendatasus/portal_files.py`` e ``docs/PLANO_NOVAS_FONTES.md``
(Fase A) para o mecanismo de descoberta (scrape em 2 saltos) e os fatos
verificados ao vivo em 2026-08-17.

SIOPS ficou de fora deste primeiro corte: o dataset ``/dataset/siops`` do
portal so expõe um PDF de metadados via S3 (não são dados tabulares), e a
API própria (``siops-consulta-publica-api.saude.gov.br``) não publica
Swagger/OpenAPI descobrível (``/swagger-resources`` retorna ``[]``; todos os
caminhos padrão de springdoc/OpenAPI testados devolveram 404). Registrado
como pendencia em ``docs/handoffs/_QUADRO.md`` em vez de forçar uma
integração as cegas.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.opendatasus.portal_files import PortalFileDataSource
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    DownloadSource,
    PortalFileDownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_portal_files_params


def _params_schema(
    *,
    min_year: "int | None",
    default_start_year: int,
    default_end_year: int,
    large_dataset_note: str = "",
    cumulative: bool = False,
    max_year: "int | None" = None,
) -> List[SourceParameterSpec]:
    current_year = datetime.now().year
    # Banco histórico congelado: o teto é o último ano publicado, não o ano
    # corrente, para a interface não oferecer anos que nunca existirão.
    year_ceiling = max_year if max_year is not None else current_year + 1
    description_suffix = f" {large_dataset_note}" if large_dataset_note else ""
    if cumulative:
        description_suffix += (
            " Dataset cumulativo sem particionamento por ano no portal "
            "(verificado ao vivo 2026-08-17): start_year/end_year sao aceitos "
            "mas nao filtram nada."
        )
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
                "Optional export format to convert the downloaded raw "
                "resource (CSV/Parquet) into. Omit to keep the resource's "
                "original format as-is."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year",
            phase="coleta",
            param_type="integer",
            description=f"Ano inicial (ano epidemiologico/referencia).{description_suffix}",
            required=False,
            default=default_start_year,
            **({"minimum": min_year} if min_year is not None else {}),
            maximum=year_ceiling,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ano final (ano epidemiologico/referencia).",
            required=False,
            default=default_end_year,
            **({"minimum": min_year} if min_year is not None else {}),
            maximum=year_ceiling,
        ),
        SourceParameterSpec(
            name="resource_filter",
            phase="refinamento",
            param_type="string",
            description=(
                "Filtro opcional (substring, case-insensitive) pelo nome do "
                "resource no portal, alem do filtro por ano."
            ),
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description=(
                "Se true, preserva o arquivo bruto baixado mesmo apos uma "
                "conversao via output_format (util para datasets grandes: "
                "por padrao o bruto e descartado apos a conversao)."
            ),
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="HTTP timeout in seconds for portal/S3 requests.",
            required=False,
            default=PortalFileDataSource.DEFAULT_TIMEOUT,
            minimum=1,
        ),
        SourceParameterSpec(
            name="api_base_url",
            phase="tecnica",
            param_type="string",
            description="Optional dadosabertos.saude.gov.br base URL override.",
            required=False,
            default=None,
        ),
    ]


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes de bulk-file do portal na ordem canonica."""
    current_year = datetime.now().year
    return [
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="srag_arquivos",
                title="SRAG - Bancos Anuais (2019-2026)",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2019,
                default_start_year=current_year,
                default_end_year=current_year,
            ),
            fixed_dataset="srag_arquivos",
            normalize_params=_normalize_portal_files_params,
        ),
        *(
            PortalFileDownloadSource(
                descriptor=SourceDescriptor(
                    source=f"srag_arquivos_{first}_{last}",
                    title=f"SRAG - Bancos Históricos ({first}-{last})",
                    mode="opendatasus files",
                ),
                datasource_cls=PortalFileDataSource,
                params_schema=_params_schema(
                    min_year=first,
                    max_year=last,
                    default_start_year=first,
                    default_end_year=last,
                ),
                fixed_dataset=f"srag_arquivos_{first}_{last}",
                normalize_params=_normalize_portal_files_params,
            )
            # Bancos congelados do SINAN Influenza, anteriores ao SIVEP-Gripe
            # atual. O layout de colunas difere do banco de 2019 em diante.
            for first, last in ((2009, 2012), (2013, 2018))
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_controle_mensal_parametros_basicos",
                title="SISAGUA - Controle Mensal - Parametros Basicos",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2014,  # verificado ao vivo 2026-08-17 (recursos anuais 2014-2026)
                default_start_year=current_year,
                default_end_year=current_year,
                large_dataset_note=(
                    "ATENCAO: dataset GRANDE (potencialmente milhoes de "
                    "linhas por ano) - prefira um recorte de ano por vez."
                ),
            ),
            fixed_dataset="sisagua_controle_mensal_parametros_basicos",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_controle_semestral",
                title="SISAGUA - Controle Semestral",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2014,  # verificado ao vivo 2026-08-17 (recursos anuais desde 2014)
                default_start_year=current_year,
                default_end_year=current_year,
            ),
            fixed_dataset="sisagua_controle_semestral",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_vigilancia_parametros_basicos",
                title="SISAGUA - Vigilancia - Parametros Basicos",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2014,  # verificado ao vivo 2026-08-17 (recursos anuais desde 2014)
                default_start_year=current_year,
                default_end_year=current_year,
            ),
            fixed_dataset="sisagua_vigilancia_parametros_basicos",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_tratamento_agua",
                title="SISAGUA - Tratamento de Agua",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-17: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
            ),
            fixed_dataset="sisagua_tratamento_agua",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_populacao_abastecida",
                title="SISAGUA - Populacao Abastecida",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-17: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
            ),
            fixed_dataset="sisagua_populacao_abastecida",
            normalize_params=_normalize_portal_files_params,
        ),
        # Remaining 9 SISAGUA packages (slugs confirmados ao vivo 2026-08-18).
        # Every one is cumulative (no year partitioning in the resource
        # name) except "plano de amostragem", which is year-segmented like
        # the other "controle mensal" packages above.
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_controle_mensal_demais_parametros",
                title="SISAGUA - Controle Mensal - Demais Parametros",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
                large_dataset_note=(
                    "ATENCAO: dataset GRANDE (potencialmente milhoes de "
                    "linhas, ~138MB comprimido)."
                ),
            ),
            fixed_dataset="sisagua_controle_mensal_demais_parametros",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_controle_mensal_amostras_fora_do_padrao",
                title="SISAGUA - Controle Mensal - Amostras Fora do Padrao",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
                large_dataset_note=(
                    "ATENCAO: dataset GRANDE (potencialmente milhoes de "
                    "linhas, ~43MB comprimido)."
                ),
            ),
            fixed_dataset="sisagua_controle_mensal_amostras_fora_do_padrao",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_controle_mensal_plano_amostragem",
                title="SISAGUA - Controle Mensal - Plano de Amostragem",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2014,  # verificado ao vivo 2026-08-18 (recursos anuais 2014-2026)
                default_start_year=current_year,
                default_end_year=current_year,
                large_dataset_note=(
                    "ATENCAO: dataset GRANDE (potencialmente milhoes de "
                    "linhas por ano) - prefira um recorte de ano por vez."
                ),
            ),
            fixed_dataset="sisagua_controle_mensal_plano_amostragem",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_controle_mensal_infraestrutura_operacional",
                title="SISAGUA - Controle Mensal - Infraestrutura Operacional",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
                large_dataset_note=(
                    "ATENCAO: dataset GRANDE (potencialmente milhoes de "
                    "linhas, ~39MB comprimido)."
                ),
            ),
            fixed_dataset="sisagua_controle_mensal_infraestrutura_operacional",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_vigilancia_demais_parametros",
                title="SISAGUA - Vigilancia - Demais Parametros",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
                large_dataset_note=(
                    "Dataset GRANDE (potencialmente milhoes de linhas, "
                    "~98MB comprimido)."
                ),
            ),
            fixed_dataset="sisagua_vigilancia_demais_parametros",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_vigilancia_cianobacterias_e_cianotoxinas",
                title="SISAGUA - Vigilancia - Cianobacterias e Cianotoxinas",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
            ),
            fixed_dataset="sisagua_vigilancia_cianobacterias_e_cianotoxinas",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_pontos_de_captacao",
                title="SISAGUA - Pontos de Captacao",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
                large_dataset_note=(
                    "~53MB comprimido (verificado ao vivo 2026-08-18)."
                ),
            ),
            fixed_dataset="sisagua_pontos_de_captacao",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_cadastro_carro_pipa_procedencia",
                title="SISAGUA - Cadastro Carro Pipa - Procedencia",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
            ),
            fixed_dataset="sisagua_cadastro_carro_pipa_procedencia",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sisagua_cadastro_carro_pipa_populacao",
                title="SISAGUA - Cadastro Carro Pipa - Populacao",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=None,  # verificado ao vivo 2026-08-18: sem particionamento por ano
                default_start_year=current_year,
                default_end_year=current_year,
                cumulative=True,
            ),
            fixed_dataset="sisagua_cadastro_carro_pipa_populacao",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="sesai_tuberculose",
                title="SIASI - Tuberculose na Saude Indigena",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2022,  # único ano publicado (verificado ao vivo 2026-09-24)
                default_start_year=2022,
                default_end_year=current_year,
            ),
            fixed_dataset="sesai_tuberculose",
            normalize_params=_normalize_portal_files_params,
        ),
        PortalFileDownloadSource(
            descriptor=SourceDescriptor(
                source="enani_2019",
                title="ENANI-2019 - Estudo Nacional de Alimentacao e Nutricao Infantil",
                mode="opendatasus files",
            ),
            datasource_cls=PortalFileDataSource,
            params_schema=_params_schema(
                min_year=2019,
                max_year=2019,
                default_start_year=2019,
                default_end_year=2019,
                large_dataset_note=(
                    "223 MB comprimidos e cerca de 2,9 GB abertos, em 26 bancos "
                    "(verificado ao vivo 2026-09-24)."
                ),
            ),
            fixed_dataset="enani_2019",
            normalize_params=_normalize_portal_files_params,
        ),
    ]


# Fontes do portal sem particionamento por ano: o portal republica um arquivo
# só, com o estado atual. O orquestrador as guarda como instantâneo mensal em
# vez de pedir o mesmo arquivo uma vez por ano. Um teste confere que este
# conjunto bate com as fontes declaradas ``cumulative=True`` acima.
CUMULATIVE_SOURCES = frozenset(
    {
        "sisagua_tratamento_agua",
        "sisagua_populacao_abastecida",
        "sisagua_controle_mensal_demais_parametros",
        "sisagua_controle_mensal_amostras_fora_do_padrao",
        "sisagua_controle_mensal_infraestrutura_operacional",
        "sisagua_vigilancia_demais_parametros",
        "sisagua_vigilancia_cianobacterias_e_cianotoxinas",
        "sisagua_pontos_de_captacao",
        "sisagua_cadastro_carro_pipa_procedencia",
        "sisagua_cadastro_carro_pipa_populacao",
    }
)
