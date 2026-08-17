"""Fontes DATASUS construidas a partir dos specs genericos de FTP (fase 5)."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.datasus.ftp import specs as ftp_specs
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    DownloadSource,
    PysusDownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_ftp_params
from guaraci.utils.mapping import UF_DICT


def _build_ftp_source(spec, *, last_year: int, uf_values: List[str]) -> "PysusDownloadSource":
    """Build a ``PysusDownloadSource`` adapter for one phase-5 FTP system spec.

    The schema is derived from the spec's dimensions: every source exposes
    ``start_year``/``end_year``; only systems with selectable groups expose
    ``groups``; only state-level systems expose ``states``.
    """
    # The in-progress current year is collectable (partial); only genuinely
    # future years are out of range. ``last_year`` is ``current_year - 1`` at
    # the call site, so reconstruct ``current_year`` here for the schema cap.
    current_year = last_year + 1
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
            default=last_year,
            minimum=spec.min_year,
            maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ending year for file discovery.",
            required=True,
            default=last_year,
            minimum=spec.min_year,
            maximum=current_year,
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

    return PysusDownloadSource(
        descriptor=SourceDescriptor(source=spec.name, title=spec.title, mode="datasus ftp"),
        datasource_cls=_factory,
        params_schema=schema,
        normalize_params=_normalize_ftp_params,
    )



def build_sources() -> List[DownloadSource]:
    """Retorna as fontes FTP genericas na ordem dos specs (ALL_SPECS)."""
    current_year = datetime.now().year
    last_year = current_year - 1
    uf_values = sorted(set(UF_DICT.values()))
    return [
        _build_ftp_source(spec, last_year=last_year, uf_values=uf_values)
        for spec in ftp_specs.ALL_SPECS
    ]
