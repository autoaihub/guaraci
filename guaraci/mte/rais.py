"""RAIS (MTE/PDET): vínculos e estabelecimentos, um 7z por região ou por ano.

Origem: ``ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/AAAA/``, com
``RAIS_VINC_PUB_<região>.7z`` (regiões ``CENTRO_OESTE``, ``MG_ES_RJ``, ``NI``,
``NORDESTE``, ``NORTE``, ``SP``, ``SUL``; de 54 KB a 1,1 GB cada, cerca de 4 GB por
ano) e ``RAIS_ESTAB_PUB.7z`` (90 a 140 MB).

Piso 2023. O leiaute mudou entre 2022 e 2023 e se mantém igual em 2023, 2024 e
2025 (conferido ao vivo em 2026-10-23, pelo arquivo ``NI`` dos três anos e pelo
``ESTAB`` de 2023 e 2025):

- até 2022 o texto sai em ``;`` com cabeçalho de nomes curtos (60 colunas nos
  vínculos, 24 nos estabelecimentos);
- de 2023 em diante sai em ``,`` com aspas, decimal com ponto, cabeçalho
  ``<nome> - Código`` (62 colunas nos vínculos, 23 nos estabelecimentos), latin-1.

Os anos de 2010 a 2017 vêm por UF e os de 2018 a 2022 trazem o leiaute antigo, e por
isso ficam fora. A RAIS pública não traz CPF, nome nem PIS: vínculo por CBO, CNAE,
município, faixa e valor de remuneração; o estabelecimento traz CEP (``CEP Estab``)
e não traz CNPJ.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from guaraci.arquivos.http_files import HttpFileClient
from guaraci.mte.pdet import (
    FTP_ROOT,
    FtpLister,
    PdetDataSource,
    PdetItem,
    ProgressCallback,
)
from guaraci.mte.sevenzip import SevenZipExtractor

__all__ = [
    "MIN_YEAR",
    "RAIS_FILES",
    "RAIS_REGIOES",
    "RaisDataSource",
    "RaisFile",
    "datasource_for",
]

MIN_YEAR = 2023
_BASE = f"{FTP_ROOT}/RAIS"
RAIS_REGIOES = ("CENTRO_OESTE", "MG_ES_RJ", "NI", "NORDESTE", "NORTE", "SP", "SUL")


class RaisFile:
    def __init__(
        self, key: str, title: str, description: str, columns: int, pattern: str
    ) -> None:
        self.key = key
        self.title = title
        self.description = description
        self.columns = columns
        self.pattern = pattern


RAIS_FILES: Dict[str, RaisFile] = {
    spec.key: spec
    for spec in (
        RaisFile(
            "mte_rais_vinculos",
            "MTE RAIS - Vínculos",
            "Vínculos de emprego formal declarados na RAIS, um registro por vínculo, desde "
            "2023 (mesmo leiaute de 62 colunas). Um arquivo por região; o ano completo passa "
            "de 4 GB comprimidos. Traz CBO, CNAE, município, faixas e valores de remuneração, "
            "sem CPF, nome ou PIS. Texto como o MTE publica.",
            62,
            r"RAIS_VINC_PUB_(?P<regiao>[A-Z_]+)\.7z",
        ),
        RaisFile(
            "mte_rais_estabelecimentos",
            "MTE RAIS - Estabelecimentos",
            "Estabelecimentos da RAIS, um registro por estabelecimento, desde 2023 (mesmo "
            "leiaute de 23 colunas): CNAE, município, natureza jurídica, tamanho, quantidade "
            "de vínculos e CEP; sem CNPJ. Texto como o MTE publica.",
            23,
            r"RAIS_ESTAB_PUB\.7z",
        ),
    )
}


class RaisDataSource(PdetDataSource):
    """Um CSV por região e ano (vínculos) ou por ano (estabelecimentos)."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = HttpFileClient.DEFAULT_TIMEOUT
    SEPARATOR = ","

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[HttpFileClient] = None,
        lister: Optional[FtpLister] = None,
        extractor: Optional[SevenZipExtractor] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in RAIS_FILES:
            raise ValueError(f"Unknown RAIS dataset '{key}'. Known: {sorted(RAIS_FILES)}")
        super().__init__(key, output_path, client=client, lister=lister, extractor=extractor)
        self.spec = RAIS_FILES[key]
        self.EXPECTED_COLUMNS = self.spec.columns

    @staticmethod
    def _years(
        anos: Optional[Sequence[object]], start_year: Optional[int], end_year: Optional[int]
    ) -> List[int]:
        if anos:
            try:
                years = sorted({int(a) for a in anos})
            except (TypeError, ValueError) as exc:
                raise ValueError(f"'anos' deve ser numérico: {exc}") from exc
        elif start_year is not None or end_year is not None:
            first = int(start_year) if start_year is not None else int(end_year)  # type: ignore[arg-type]
            last = int(end_year) if end_year is not None else first
            if last < first:
                raise ValueError("end_year must be >= start_year.")
            years = list(range(first, last + 1))
        else:
            raise ValueError(
                "A RAIS tem GB por ano; informe 'anos' (ou start_year/end_year) para escolher."
            )
        low = [y for y in years if y < MIN_YEAR]
        if low:
            raise ValueError(
                f"RAIS: o leiaute de {low} é anterior ao de {MIN_YEAR} e não é exportado; "
                f"o piso é {MIN_YEAR}."
            )
        return years

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        anos: Optional[Sequence[object]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        regioes: Optional[Sequence[str]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        years = self._years(anos, start_year, end_year)
        wanted: Optional[List[str]] = None
        if regioes:
            wanted = [str(r).strip().upper() for r in regioes]
            unknown = sorted(set(wanted) - set(RAIS_REGIOES))
            if unknown:
                raise ValueError(f"Unknown regioes {unknown}. Known: {list(RAIS_REGIOES)}")
        warnings: List[str] = []
        pattern = re.compile(self.spec.pattern, re.IGNORECASE)
        items: List[PdetItem] = []
        for year in years:
            folder = f"{_BASE}/{year}"
            names = self.lister().names(folder)
            if not names:
                warnings.append(f"{year}: pasta da RAIS ainda não publicada no FTP do MTE.")
                continue
            found = 0
            for name in sorted(names):
                match = pattern.fullmatch(name)
                if match is None:
                    continue
                region = match.groupdict().get("regiao")
                if region is not None and wanted is not None and region.upper() not in wanted:
                    continue
                found += 1
                suffix = f"_{region.upper()}" if region else ""
                items.append(
                    PdetItem(f"{year}{suffix}", f"{folder}/{name}", f"{self.spec.key} {year}{suffix}")
                )
            if not found:
                warnings.append(f"{year}: nenhum arquivo casa com o pedido.")
        return self._run(
            items,
            output_format=output_format,
            keep_raw=keep_raw,
            output_dir=output_dir,
            timeout=timeout,
            progress_callback=progress_callback,
            warnings=warnings,
        )


def latest_year() -> int:
    """Ano mais recente que pode existir (a RAIS do ano Y sai no ano Y+1)."""
    return datetime.now().year


def datasource_for(key: str) -> type:
    if key not in RAIS_FILES:
        raise KeyError(key)
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (RaisDataSource,), {"DATASET": key})
