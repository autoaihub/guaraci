"""IBGE population estimates by locality x year (SIDRA aggregate table 6579).

Table 6579 / variable 9324 is "População residente estimada" — the annual TCU
population estimates IBGE publishes per municipality (and every coarser level).
It is the denominator layer for turning DATASUS case/death counts into rates.

Thin subclass of :class:`~guaraci.ibge.sidra.SidraAggregateSource` (it has no
classifications); the fetch/parse/export/manifest logic is shared there.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import SidraAggregateSource


class IbgePopulacaoDataSource(SidraAggregateSource):
    """IBGE population estimates (SIDRA table 6579)."""

    TABLE = "6579"
    VARIABLE = "9324"
    DEFAULT_LEVEL = "municipio"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_populacao", output_path=output_path, client=client)

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )
