"""Fontes de camadas geográficas via WFS (SGB e FUNAI) do registro padrão."""

from functools import partial
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.geo.wfs import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    EXPORT_FORMATS,
    WFS_FAMILIES,
    WfsDataSource,
    WfsFamily,
)
from guaraci.services.downloads import (
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)


def _params(family: WfsFamily) -> List[SourceParameterSpec]:
    names = [layer.name for layer in family.layers]
    specs = [
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
                "Exporta em CSV UTF-8 (padrão), Parquet ou SQLite, com todas as colunas "
                "como texto e a geometria em WKT."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMATS,
        ),
    ]
    if len(names) > 1:
        specs.append(
            SourceParameterSpec(
                name="camadas",
                phase="coleta",
                param_type="string_list",
                description=(
                    "Camadas (um arquivo por camada). Valores: "
                    + ", ".join(names)
                    + ". Omitido, baixa todas."
                ),
                required=False,
                default=None,
                allowed_values=names,
            )
        )
    specs.extend(
        [
            SourceParameterSpec(
                name="cql_filter",
                phase="coleta",
                param_type="string",
                description=(
                    "Filtro CQL aplicado no servidor, por exemplo uf='RO'. Omitido, baixa a "
                    "camada inteira."
                ),
                required=False,
                default=None,
            ),
            SourceParameterSpec(
                name="keep_raw",
                phase="tecnica",
                param_type="boolean",
                description="Mantém o CSV intermediário ao exportar para Parquet ou SQLite.",
                required=False,
                default=False,
            ),
            SourceParameterSpec(
                name="timeout",
                phase="tecnica",
                param_type="integer",
                description="Segundos por requisição ao WFS.",
                required=False,
                default=DEFAULT_TIMEOUT,
                minimum=1,
                maximum=900,
            ),
            SourceParameterSpec(
                name="page_size",
                phase="tecnica",
                param_type="integer",
                description="Feições por página do WFS (maxFeatures).",
                required=False,
                default=DEFAULT_PAGE_SIZE,
                minimum=1,
                maximum=50000,
            ),
        ]
    )
    return specs


def _make(family: str, output_path=None) -> WfsDataSource:
    return WfsDataSource(family, output_path=output_path)


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes WFS na ordem do registro."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=family.key, title=family.title, mode="geo wfs"),
            datasource_cls=partial(_make, family.key),
            params_schema=_params(family),
        )
        for family in WFS_FAMILIES.values()
    ]
