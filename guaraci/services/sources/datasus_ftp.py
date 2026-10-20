"""Fontes DATASUS construidas a partir dos specs genericos de FTP (fase 5)."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.datasus.ftp import specs as ftp_specs
from guaraci.datasus.siscan_csv import (
    SISCAN_CSV,
    SISCAN_CSV_ANOS,
    SISCAN_CSV_TABELAS,
    FtpFileClient,
    SiscanCsvDataSource,
)
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    DatasusDownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_ftp_params
from guaraci.utils.mapping import UF_DICT


def _build_ftp_source(spec, *, last_year: int, uf_values: List[str]) -> "DatasusDownloadSource":
    """Build a ``DatasusDownloadSource`` adapter for one phase-5 FTP system spec.

    The schema is derived from the spec's dimensions: every source exposes
    ``start_year``/``end_year``; only systems with selectable groups expose
    ``groups``; only state-level systems expose ``states``.
    """
    # The in-progress current year is collectable (partial); only genuinely
    # future years are out of range. ``last_year`` is ``current_year - 1`` at
    # the call site, so reconstruct ``current_year`` here for the schema cap.
    current_year = last_year + 1
    ceiling = min(current_year, spec.max_year or current_year)
    default_year = min(last_year, spec.max_year or last_year, spec.default_year or last_year)
    schema = [
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
            description="Starting year for file discovery.",
            required=True,
            default=default_year,
            minimum=spec.min_year,
            maximum=ceiling,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ending year for file discovery.",
            required=True,
            default=default_year,
            minimum=spec.min_year,
            maximum=ceiling,
        ),
    ]
    if spec.groups:
        schema.append(
            SourceParameterSpec(
                name="groups",
                phase="coleta",
                param_type="string_list",
                description=f"{spec.title} groups to download.",
                required=False,
                default=list(spec.default_groups),
                allowed_values=list(spec.groups),
            )
        )
    if spec.has_state:
        schema.append(
            SourceParameterSpec(
                name="states",
                phase="coleta",
                param_type="string_list",
                description="UF filter list.",
                required=False,
                default=None,
                allowed_values=uf_values,
            )
        )

    def _factory(output_path=None, _spec=spec):
        return _downloads.FtpDataSource(_spec, output_path=output_path)

    return DatasusDownloadSource(
        descriptor=SourceDescriptor(source=spec.name, title=spec.title, mode="datasus ftp"),
        datasource_cls=_factory,
        params_schema=schema,
        normalize_params=_normalize_ftp_params,
    )


def _build_siscan_csv_source() -> "ApiDownloadSource":
    """SISCAN em CSV: arquivo por tabela e ano, sem a descoberta por UF do DBC.

    O padrão é a menor combinação útil (histopatológico de mama do último ano,
    12 MB); a citologia de colo de um único ano passa de 2 GB.
    """
    schema = [
        SourceParameterSpec(
            name="tabelas",
            phase="coleta",
            param_type="string_list",
            description=(
                "Tabelas do SISCAN (obrigatório). CITO_COLO e MAMOGRAFIA, e suas versões "
                "_PACNT, têm de 0,5 a 2,1 GB por ano; as de mama e histopatológico, "
                "menos de 13 MB."
            ),
            required=True,
            default=["HISTO_MAMA"],
            allowed_values=list(SISCAN_CSV_TABELAS),
        ),
        SourceParameterSpec(
            name="anos",
            phase="coleta",
            param_type="string_list",
            description="Anos de competência a baixar (obrigatório), de 2013 a 2025.",
            required=True,
            default=[str(SISCAN_CSV_ANOS[-1])],
            allowed_values=[str(a) for a in SISCAN_CSV_ANOS],
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
            description="FTP timeout in seconds.",
            required=False,
            default=FtpFileClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
    ]
    return ApiDownloadSource(
        descriptor=SourceDescriptor(
            source=SISCAN_CSV.key, title=SISCAN_CSV.title, mode="datasus ftp csv"
        ),
        datasource_cls=SiscanCsvDataSource,
        params_schema=schema,
    )


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes FTP genericas na ordem dos specs (ALL_SPECS)."""
    current_year = datetime.now().year
    last_year = current_year - 1
    uf_values = sorted(set(UF_DICT.values()))
    return [
        *(
            _build_ftp_source(spec, last_year=last_year, uf_values=uf_values)
            for spec in ftp_specs.ALL_SPECS
        ),
        _build_siscan_csv_source(),
    ]
