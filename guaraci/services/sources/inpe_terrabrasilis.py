"""Fontes INPE TerraBrasilis (DETER e PRODES via WFS) do registro padrao."""

from functools import partial
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.inpe.terrabrasilis import (
    BIOMAS,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    EXPORT_FORMATS,
    MIN_YEAR,
    TerraBrasilisDataSource,
    current_year,
)
from guaraci.services.downloads import (
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def _specs(family: str, *, with_biomas: bool) -> List[SourceParameterSpec]:
    floor = MIN_YEAR[family]
    last = current_year() + 1
    specs = [
        SourceParameterSpec(
            name="output_dir", phase="tecnica", param_type="string",
            description="Output directory for downloaded files.",
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="output_format", phase="exportacao", param_type="string",
            description=(
                "Exporta em CSV UTF-8 (padrão), Parquet ou SQLite, com todas as "
                "colunas como texto e sem geometria."
            ),
            required=False, default=None, allowed_values=EXPORT_FORMATS,
        ),
        SourceParameterSpec(
            name="start_year", phase="coleta", param_type="integer",
            description=(
                f"Ano inicial (desde {floor}, confirmado ao vivo). Omitido, "
                "baixa a camada inteira."
            ),
            required=False, default=None, minimum=floor, maximum=last,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final, inclusivo (padrão: sem limite superior).",
            required=False, default=None, minimum=floor, maximum=last,
        ),
    ]
    if with_biomas:
        specs.append(SourceParameterSpec(
            name="biomas", phase="coleta", param_type="string_list",
            description=(
                "Biomas (um CSV por bioma). Valores: " + ", ".join(BIOMAS)
                + ". Omitido, baixa todos."
            ),
            required=False, default=None, allowed_values=BIOMAS,
        ))
    specs.extend([
        SourceParameterSpec(
            name="keep_raw", phase="tecnica", param_type="boolean",
            description="Mantém o CSV intermediário ao exportar para Parquet ou SQLite.",
            required=False, default=False,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="Segundos por requisição ao WFS.",
            required=False, default=DEFAULT_TIMEOUT, minimum=1, maximum=600,
        ),
        SourceParameterSpec(
            name="page_size", phase="tecnica", param_type="integer",
            description="Feições por página do WFS (count).",
            required=False, default=DEFAULT_PAGE_SIZE, minimum=1, maximum=50000,
        ),
    ])
    return specs


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes TerraBrasilis na ordem canonica."""
    items = [
        ("inpe_deter_amazonia", "INPE DETER Amazônia (alertas de desmatamento)", False),
        ("inpe_deter_cerrado", "INPE DETER Cerrado (alertas de desmatamento)", False),
        ("inpe_prodes", "INPE PRODES (desmatamento anual consolidado)", True),
    ]
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=key, title=title, mode="inpe terrabrasilis wfs"),
            datasource_cls=partial(_make, key),
            params_schema=_specs(key, with_biomas=with_biomas),
        )
        for key, title, with_biomas in items
    ]


def _make(family: str, output_path=None) -> TerraBrasilisDataSource:
    return TerraBrasilisDataSource(family, output_path=output_path)
