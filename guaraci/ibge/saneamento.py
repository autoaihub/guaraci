"""IBGE saneamento domiciliar (Censo 2022) -- SIDRA tabelas 6803 / 6805 / 6892.

Domicilios particulares permanentes ocupados por forma de abastecimento de
agua, tipo de esgotamento sanitario e destino do lixo. All three verified
live 2026-08-25 via ``GET /api/v3/agregados/<tabela>/metadados``:

* Single period, 2022 (census reference); levels N1/N2/N3/N6 only (no
  N7/N8/N9/N13/N14).
* Same universe variable, 381 ("Domicilios particulares permanentes
  ocupados"), across all three tables -- the "Total" category of each
  table's single classification returns the same national count (Brasil
  2022: 72 456 368 domicilios), which is the smoke-test reference.
* Each table carries exactly one classification (no month/sex axis like the
  registro civil tables), with a "Total" category plus a fixed set of
  sub-categories (some of which are themselves subtotals, e.g. "Possui
  ligacao a rede geral, mas utiliza principalmente outra forma").

This is the determinant-social layer that pairs with the 14 SISAGUA sources
and with the arbovirus datasets: household water/sanitation access is a
known confounder for water-borne and vector-borne disease burden.

Combinatorics, tested live 2026-08-25 against ``N6[all]`` (5570
municipalities), year 2022, single classification set to ``all``:

* Table 6803 (agua, 18 categorias) -> **HTTP 500** (SIDRA aggregate limit).
* Table 6805 (esgoto, 10 categorias) -> **HTTP 500**.
* Table 6892 (lixo, 8 categorias) -> 200 OK (~5.4 MB) -- the only one of the
  three that fits under the limit at full municipal detail.

So ``detalhe="all"`` is rejected up front for agua/esgoto when
``level="municipio"`` (mirroring the guard in
:mod:`guaraci.ibge.registro_civil`); it is allowed for lixo since it is
confirmed to work. All three default ``detalhe="total"`` (a single row per
locality), matching the other IBGE sources' safe-by-default shape.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import SidraAggregateSource

CENSUS_YEAR = 2022


class _SaneamentoDomiciliarSource(SidraAggregateSource):
    """Shared single-classification ``detalhe`` handling for the three tables."""

    VARIABLE = "381"
    DEFAULT_LEVEL = "municipio"
    CLASSIFICACAO_ID: str = ""
    CATEGORIA_TOTAL: str = ""
    # Only the lixo table (8 categories) is confirmed live to stay under the
    # SIDRA municipal x full-classification limit; agua (18) and esgoto (10)
    # both 500 at level=municipio, detalhe=all.
    MUNICIPAL_ALL_ALLOWED = False

    def download(
        self,
        *,
        start_year: object = CENSUS_YEAR,
        end_year: object = CENSUS_YEAR,
        level: str = DEFAULT_LEVEL,
        detalhe: str = "total",
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
                f"SIDRA table {self.TABLE} only publishes period {CENSUS_YEAR} "
                "(Censo 2022 reference; verified live). Set start_year=end_year="
                f"{CENSUS_YEAR}."
            )
        level_key = str(level).strip().lower()
        detalhe_norm = str(detalhe).strip().lower()
        if detalhe_norm == "total":
            token = self.CATEGORIA_TOTAL
        elif detalhe_norm in ("all", "todos"):
            token = "all"
            if not self.MUNICIPAL_ALL_ALLOWED and level_key in ("municipio", "n6"):
                raise ValueError(
                    "Parameter 'detalhe'='all' is not supported together with "
                    f"level='municipio' for table {self.TABLE} (SIDRA rejects "
                    "the combinatorial request -- confirmed live). Use "
                    "level='uf'/'regiao'/'brasil' for the detailed breakdown, "
                    "or keep detalhe='total' for the municipal one."
                )
        else:
            raise ValueError(f"Unsupported detalhe '{detalhe}'. Allowed: total, all")
        classificacao = f"{self.CLASSIFICACAO_ID}[{token}]"
        return self._collect(
            start_year=y0,
            end_year=y1,
            level=level,
            classificacao=classificacao,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgeSaneamentoAguaDataSource(_SaneamentoDomiciliarSource):
    """Households by main water supply -- SIDRA table 6803, var 381.

    "Existencia de ligacao a rede geral de distribuicao de agua e principal
    forma de abastecimento de agua." Reference total (Brasil, 2022,
    detalhe=total, verified live 2026-08-25): 72 456 368 domicilios.
    """

    TABLE = "6803"
    CLASSIFICACAO_ID = "1821"
    CATEGORIA_TOTAL = "72129"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_saneamento_agua", output_path=output_path, client=client)


class IbgeSaneamentoEsgotoDataSource(_SaneamentoDomiciliarSource):
    """Households by sanitary sewage type -- SIDRA table 6805, var 381.

    "Tipo de esgotamento sanitario." Reference total (Brasil, 2022,
    detalhe=total, verified live 2026-08-25): 72 456 368 domicilios.
    """

    TABLE = "6805"
    CLASSIFICACAO_ID = "11558"
    CATEGORIA_TOTAL = "46292"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_saneamento_esgoto", output_path=output_path, client=client)


class IbgeSaneamentoLixoDataSource(_SaneamentoDomiciliarSource):
    """Households by garbage disposal -- SIDRA table 6892, var 381.

    "Destino do lixo." Reference total (Brasil, 2022, detalhe=total,
    verified live 2026-08-25): 72 456 368 domicilios. The only one of the
    three saneamento tables where detalhe='all' also works at level=municipio
    (confirmed live: 200 OK, ~5.4 MB for 5570 municipalities x 8 categories).
    """

    TABLE = "6892"
    CLASSIFICACAO_ID = "67"
    CATEGORIA_TOTAL = "10972"
    MUNICIPAL_ALL_ALLOWED = True

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_saneamento_lixo", output_path=output_path, client=client)
