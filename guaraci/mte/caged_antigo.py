"""CAGED antigo (MTE/PDET): estoque mensal de 2007 a 2019 e ajustes de 2002 a 2019.

Origem: ``ftp://ftp.mtps.gov.br/pdet/microdados/CAGED/AAAA/CAGEDEST_MMAAAA.7z`` (um 7z por
mês, de 20 a 33 MB) e ``CAGED_AJUSTES``: um 7z por ano de 2002 a 2009
(``2002a2009/CAGEDEST_AJUSTES_AAAA.7z``) e um por mês de 2010 a 2019
(``AAAA/CAGEDEST_AJUSTES_MMAAAA.7z``). Cada 7z tem um único TXT em ``;``. O leiaute muda
com a época (40 a 42 colunas no estoque, 37 a 43 nos ajustes), então a contagem de colunas
não é conferida e o cabeçalho sai como o MTE publica. O Novo CAGED (2020 em diante) fica
nas chaves ``mte_novo_caged_*``. Sem CPF, nome ou PIS.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from guaraci.arquivos.http_files import HttpFileClient
from guaraci.mte.caged import month_range, parse_day
from guaraci.mte.pdet import (
    FTP_ROOT,
    FtpLister,
    PdetDataSource,
    PdetItem,
    ProgressCallback,
    match_name,
)
from guaraci.mte.sevenzip import SevenZipExtractor

__all__ = [
    "AJUSTES_ANUAIS_ATE",
    "CAGED_ANTIGO_FILES",
    "CagedAntigoDataSource",
    "CagedAntigoFile",
    "datasource_for",
]

_BASE = f"{FTP_ROOT}/CAGED"
_BASE_AJUSTES = f"{FTP_ROOT}/CAGED_AJUSTES"
AJUSTES_ANUAIS_ATE = 2009
_NOTE = (
    "Microdado desidentificado (sem CPF, nome ou PIS); traz município, CNAE, CBO, sexo, "
    "idade e salário. Texto como o MTE publica."
)


class CagedAntigoFile:
    def __init__(
        self, key: str, title: str, description: str, min_year: int, max_year: int
    ) -> None:
        self.key = key
        self.title = title
        self.description = description
        self.min_year = min_year
        self.max_year = max_year


CAGED_ANTIGO_FILES: Dict[str, CagedAntigoFile] = {
    spec.key: spec
    for spec in (
        CagedAntigoFile(
            "mte_caged_antigo",
            "MTE CAGED antigo - Movimentações 2007-2019",
            "Admissões e desligamentos do emprego formal celetista de 2007 a 2019, um registro "
            "por movimentação, no leiaute anterior ao Novo CAGED (de 40 a 42 colunas conforme "
            "o ano). Um arquivo por mês. " + _NOTE,
            2007,
            2019,
        ),
        CagedAntigoFile(
            "mte_caged_antigo_ajustes",
            "MTE CAGED antigo - Ajustes 2002-2019",
            "Movimentações do CAGED antigo declaradas fora do prazo (ajustes), no leiaute do "
            "estoque mensal. Um arquivo por ano de 2002 a 2009 e um por mês de 2010 a 2019. "
            + _NOTE,
            2002,
            2019,
        ),
    )
}


class CagedAntigoDataSource(PdetDataSource):
    """Um CSV por mês (ou por ano, nos ajustes até 2009). Subclasses fixam ``DATASET``."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = HttpFileClient.DEFAULT_TIMEOUT
    SEPARATOR = ";"

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
        if key not in CAGED_ANTIGO_FILES:
            raise ValueError(
                f"Unknown CAGED antigo dataset '{key}'. Known: {sorted(CAGED_ANTIGO_FILES)}"
            )
        super().__init__(key, output_path, client=client, lister=lister, extractor=extractor)
        self.spec = CAGED_ANTIGO_FILES[key]

    def _requested(
        self,
        anos: Optional[Sequence[object]],
        meses: Optional[Sequence[object]],
        start_date: Optional[object],
        end_date: Optional[object],
    ) -> List[Tuple[int, int]]:
        if start_date is not None or end_date is not None:
            first = parse_day(start_date if start_date is not None else end_date)
            last = parse_day(end_date if end_date is not None else start_date)
            if last < first:
                raise ValueError("end_date must be on or after start_date.")
            months = month_range(first, last)
        elif anos:
            try:
                years = sorted({int(a) for a in anos})
                wanted = {int(m) for m in meses or ()} or set(range(1, 13))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"'anos' e 'meses' devem ser números: {exc}") from exc
            if any(m < 1 or m > 12 for m in wanted):
                raise ValueError("'meses' deve ter valores de 1 a 12.")
            months = [(y, m) for y in years for m in sorted(wanted)]
        else:
            raise ValueError("Informe 'anos' (ou start_date/end_date): são cerca de 25 MB por mês.")
        out = [
            ym for ym in months if ym[0] < self.spec.min_year or ym[0] > self.spec.max_year
        ]
        if out:
            raise ValueError(
                f"{self.spec.key} cobre {self.spec.min_year} a {self.spec.max_year}; "
                f"pedido: {out[0][0]}."
            )
        return months

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        anos: Optional[Sequence[object]] = None,
        meses: Optional[Sequence[object]] = None,
        start_date: Optional[object] = None,
        end_date: Optional[object] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        months = self._requested(anos, meses, start_date, end_date)
        ajustes = self.spec.key.endswith("_ajustes")
        warnings: List[str] = []
        items: List[PdetItem] = []
        seen_years = set()
        for year, month in months:
            annual = ajustes and year <= AJUSTES_ANUAIS_ATE
            if annual:
                if year in seen_years:
                    continue
                seen_years.add(year)
                folder = f"{_BASE_AJUSTES}/2002a2009"
                pattern = rf"CAGEDEST_AJUSTES_{year}\.7z"
                code = f"{year}"
            else:
                code = f"{year}{month:02d}"
                folder = f"{_BASE_AJUSTES if ajustes else _BASE}/{year}"
                stem = "CAGEDEST_AJUSTES" if ajustes else "CAGEDEST"
                pattern = rf"{stem}_{month:02d}{year}\.7z"
            name = match_name(self.lister().names(folder), pattern)
            if name is None:
                warnings.append(f"{code}: arquivo inexistente no FTP do MTE ({folder}).")
                continue
            items.append(PdetItem(code, f"{folder}/{name}", f"{self.spec.key} {code}"))
        return self._run(
            items,
            output_format=output_format,
            keep_raw=keep_raw,
            output_dir=output_dir,
            timeout=timeout,
            progress_callback=progress_callback,
            warnings=warnings,
        )


def datasource_for(key: str) -> type:
    if key not in CAGED_ANTIGO_FILES:
        raise KeyError(key)
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (CagedAntigoDataSource,), {"DATASET": key})


