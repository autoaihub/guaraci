"""Fontes OpenDataSUS manuais (curadas) do registro padrao.

As fontes geradas automaticamente vivem em ``opendatasus_registry.py`` e sao
mescladas com dedup em ``DownloadService._default_sources``.
"""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    DownloadSource,
    OpenDataSUSDownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_opendatasus_params
from guaraci.utils.mapping import UF_DICT


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes OpenDataSUS manuais na ordem canonica."""
    current_year = datetime.now().year
    last_year = current_year - 1
    uf_values = sorted(set(UF_DICT.values()))
    return [
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="doses_aplicadas_pni",
                title="Doses Aplicadas PNI",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS (endpoint anual).",
                    required=True,
                    default=last_year,
                    minimum=2020,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS (endpoint anual).",
                    required=True,
                    default=last_year,
                    minimum=2020,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Filtro opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched per year in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="resource_id",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional explicit resource id (CKAN mode). "
                        "Ignored in DEMAS mode."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br | CKAN: .../api/3/action)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset=_downloads.OpenDataSUSDataSource.DEFAULT_DATASET,
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="zikavirus",
                title="Arboviroses Zikavirus",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="zikavirus",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="febre_amarela",
                title="Arboviroses Febre Amarela",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(1994, last_year),
                    minimum=1994,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(1994, last_year),
                    minimum=1994,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="febre_amarela",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="dengue",
                title="Arboviroses Dengue",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="dengue",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="chikungunya",
                title="Arboviroses Chikungunya",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="chikungunya",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="srag_demas",
                title="SRAG (Vigilância Epidemiológica da Gripe)",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="srag_demas",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="sindrome_gripal_leve",
                title="Síndrome Gripal Leve",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="sindrome_gripal_leve",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="mpox",
                title="Mpox",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="mpox",
            normalize_params=_normalize_opendatasus_params,
        ),
        OpenDataSUSDownloadSource(
            descriptor=SourceDescriptor(
                source="esavi",
                title="ESAVI - Eventos Adversos Pós-Vacinação",
                mode="opendatasus api",
            ),
            datasource_cls=_downloads.OpenDataSUSDataSource,
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
                    description="Optional export format for processed datasets.",
                    required=False,
                    default=None,
                    allowed_values=EXPORT_FORMAT_VALUES,
                ),
                SourceParameterSpec(
                    name="start_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano inicial para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="end_year",
                    phase="coleta",
                    param_type="integer",
                    description="Ano final para consulta na API OpenDataSUS.",
                    required=True,
                    default=max(2016, last_year),
                    minimum=2016,
                    maximum=current_year,
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="refinamento",
                    param_type="string",
                    description=(
                        "Refinamento opcional local: data final (YYYY-MM-DD) "
                        "dentro do intervalo start_year/end_year."
                    ),
                    required=False,
                    default=None,
                ),
                SourceParameterSpec(
                    name="uf",
                    phase="refinamento",
                    param_type="string",
                    description="Refinamento local opcional por UF.",
                    required=False,
                    default=None,
                    allowed_values=uf_values,
                ),
                SourceParameterSpec(
                    name="keep_raw",
                    phase="tecnica",
                    param_type="boolean",
                    description="Se true, salva snapshot bruto JSONL além da exportação.",
                    required=False,
                    default=False,
                ),
                SourceParameterSpec(
                    name="batch_size",
                    phase="tecnica",
                    param_type="integer",
                    description="Page size for OpenDataSUS API pagination.",
                    required=False,
                    default=1000,
                    minimum=1,
                    maximum=1000,
                ),
                SourceParameterSpec(
                    name="max_pages",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Maximum number of pages fetched in OpenDataSUS API. "
                        "Increase for broader coverage in large periods."
                    ),
                    required=False,
                    default=_downloads.OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                    minimum=1,
                    maximum=200000,
                ),
                SourceParameterSpec(
                    name="api_base_url",
                    phase="tecnica",
                    param_type="string",
                    description=(
                        "Optional OpenDataSUS API base URL override "
                        "(DEMAS: apidadosabertos.saude.gov.br)."
                    ),
                    required=False,
                    default=None,
                ),
            ],
            fixed_dataset="esavi",
            normalize_params=_normalize_opendatasus_params,
        ),
    ]
