"""IBGE territorial area / density — SIDRA table 4714.

"População Residente, Área territorial e Densidade demográfica." Verified
live 2026-08-17 via ``GET /api/v3/agregados/4714/metadados``: the table has
**no classifications** and publishes a **single period, 2022** (census
reference — ``periodicidade.inicio == periodicidade.fim == 2022``), at
levels N1/N2/N3/N6 (Brasil/Região/UF/Município). No other territorial-area
SIDRA table was found with a longer run (table 1301, "Área e Densidade
demográfica da unidade territorial", is likewise a single period — 2010 —
so 4714 is preferred as the current one).

The table bundles three variables: população residente (93), área da
unidade territorial em km² (6318) and densidade demográfica (614). SIDRA
accepts a ``|``-joined variable list in the same request (confirmed live:
``.../variaveis/93|614|6318`` returns all three), and
:class:`~guaraci.ibge.sidra.SidraAggregateSource` already treats ``VARIABLE``
as an opaque string forwarded verbatim to the client and fans the response
out per returned variable id — so no client/base-class change was needed to
pull all three in one request.

Reference total (Brasil, 2022, verified live 2026-08-17): área territorial
8 510 417.771 km².

This is the spatial denominator layer (area/density) for rate
standardisation, paired with ``ibge_populacao``/``ibge_populacao_idade_sexo``.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import SidraAggregateSource

CENSUS_YEAR = 2022


class IbgeAreaTerritorialDataSource(SidraAggregateSource):
    """Municipal/UF/regional area, population and density — SIDRA table 4714."""

    TABLE = "4714"
    VARIABLE = "93|614|6318"
    DEFAULT_LEVEL = "municipio"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_area_territorial", output_path=output_path, client=client)

    def download(
        self,
        *,
        start_year: object = CENSUS_YEAR,
        end_year: object = CENSUS_YEAR,
        level: str = DEFAULT_LEVEL,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0 = self._parse_year(start_year, "start_year")
        y1 = self._parse_year(end_year, "end_year")
        if y0 != CENSUS_YEAR or y1 != CENSUS_YEAR:
            raise ValueError(
                f"SIDRA table 4714 only publishes period {CENSUS_YEAR} (census "
                f"reference; verified live). Set start_year=end_year={CENSUS_YEAR}."
            )
        return self._collect(
            start_year=y0,
            end_year=y1,
            level=level,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )
