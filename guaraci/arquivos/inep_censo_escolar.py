"""Censo Escolar da Educação Básica (INEP): tabela de escolas, um zip por ano.

O INEP publica um zip por ano em ``download.inep.gov.br/dados_abertos`` com o
nome ``microdados_censo_escolar_<ano>.zip``; só o de 2025 ganhou um sublinhado
final (``_2025_.zip``). O zip traz a tabela de escolas (infraestrutura, água,
esgoto, energia, internet, alimentação) e, de 2025 em diante, também as de
docente, matrícula, turma, gestor e curso técnico, que esta fonte não exporta.
O nome do CSV de escolas muda de época (``microdados_ed_basica_<ano>.csv`` até
2024, ``Tabela_Escola_<ano>_V2.csv`` em 2025) e a pasta que o contém também,
então o membro é achado por padrão. O CSV sai em ``;`` e cp1252, sem BOM.

De 1995 a 2006 o zip existe, mas traz outro esquema (``CENSOESC_<ano>.CSV``), e
por isso o piso desta fonte é 2007.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Sequence

from guaraci.arquivos.http_files import HttpFile, HttpFileClient, HttpFileDataSource, HttpResource
from guaraci.core.datasource import DataSource

__all__ = ["INEP_CENSO_ESCOLAR", "InepCensoEscolarDataSource", "MIN_YEAR", "year_url"]

INEP_CENSO_ESCOLAR = "inep_censo_escolar"
MIN_YEAR = 2007
_BASE = "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_"
# Primeiro ano com sublinhado final no nome do zip.
_UNDERSCORE_FROM = 2025


def year_url(year: int) -> str:
    return f"{_BASE}{year}{'_' if year >= _UNDERSCORE_FROM else ''}.zip"


def _resources(first: int, last: int) -> tuple:
    return tuple(HttpResource(str(y), year_url(y), f"Censo Escolar {y}") for y in range(first, last + 1))


_SPEC = HttpFile(
    INEP_CENSO_ESCOLAR,
    "INEP Censo Escolar - Tabela de escolas",
    "Microdados do Censo Escolar da Educação Básica (INEP), tabela de escolas por ano: "
    "infraestrutura, água, esgoto, energia, internet e alimentação. Um zip por ano.",
    _resources(MIN_YEAR, 2025),
    separator=";",
    member_pattern=r"(?:^|/)(?:microdados_ed_basica_\d{4}|Tabela_Escola_\d{4}(?:_v\d+)?)\.csv$",
    encoding="cp1252",
    selector="anos",
)


class InepCensoEscolarDataSource(HttpFileDataSource):
    """Um zip por ano; exporta ``inep_censo_escolar_<ano>`` com a tabela de escolas."""

    DATASET = INEP_CENSO_ESCOLAR

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[HttpFileClient] = None,
    ) -> None:
        DataSource.__init__(self, name=INEP_CENSO_ESCOLAR, output_path=output_path)
        self.spec = _SPEC
        self._client = client

    def _select(self, anos: Optional[Sequence[str]]):
        if not anos:
            return list(_resources(MIN_YEAR, datetime.now().year))
        years = [int(a) for a in anos]
        low = [y for y in years if y < MIN_YEAR]
        if low:
            raise ValueError(f"Censo Escolar: ano abaixo de {MIN_YEAR} ({low}) tem outro esquema.")
        return list(_resources_for(years))

    def download(
        self,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, object]:
        if start_year is not None:
            last = end_year if end_year is not None else start_year
            if last < start_year:
                raise ValueError("end_year must be >= start_year.")
            kwargs["indicadores"] = [str(y) for y in range(int(start_year), int(last) + 1)]
        return super().download(**kwargs)


def _resources_for(years: Sequence[int]):
    for y in dict.fromkeys(years):
        yield HttpResource(str(y), year_url(y), f"Censo Escolar {y}")
