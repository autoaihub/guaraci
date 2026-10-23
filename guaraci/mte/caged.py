"""Novo CAGED (MTE/PDET): movimentações, fora de prazo e exclusões, um 7z por mês.

Origem: ``ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/AAAA/AAAAMM/``, com
``CAGEDMOVAAAAMM.7z`` (51 MB), ``CAGEDFORAAAAMM.7z`` e ``CAGEDEXCAAAAMM.7z``. A
série começa em 2020-01 e a defasagem é de cerca de um mês (202608 saiu em
2026-09-29). Cada 7z tem um único TXT em ``;``, UTF-8, com cabeçalho em
minúsculas sem separador entre palavras (``competênciamov``, ``saldomovimentação``).

Leiaute conferido ao vivo (2026-10-23): MOV e FOR têm 28 colunas idênticas
(2020-01, 2021-06 e 2026-08); EXC tem 30, as mesmas mais ``competênciaexc`` e
``indicadordeexclusão``. Não há CPF, nome nem PIS: o arquivo é desidentificado
(município, CNAE subclasse, CBO, sexo, idade, salário). FOR existe desde 2020-02
e EXC desde 2020-04; o mês sem o arquivo vira aviso.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

from guaraci.arquivos.http_files import HttpFileClient
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
    "CAGED_FILES",
    "CagedFile",
    "MIN_YEAR",
    "NovoCagedDataSource",
    "datasource_for",
]

MIN_YEAR = 2020
_BASE = f"{FTP_ROOT}/NOVO CAGED"
_NOTE = (
    "Microdado desidentificado (sem CPF, nome ou PIS); traz município, CNAE subclasse, "
    "CBO, sexo, idade e salário. Texto como o MTE publica."
)


class CagedFile:
    def __init__(self, key: str, prefix: str, title: str, description: str, columns: int) -> None:
        self.key = key
        self.prefix = prefix
        self.title = title
        self.description = description
        self.columns = columns


CAGED_FILES: Dict[str, CagedFile] = {
    spec.key: spec
    for spec in (
        CagedFile(
            "mte_novo_caged_movimentacoes",
            "CAGEDMOV",
            "MTE Novo CAGED - Movimentações",
            "Admissões e desligamentos do emprego formal celetista informados no prazo, um "
            "registro por movimentação, desde 2020-01 (eSocial, CAGED e Empregador Web). "
            + _NOTE,
            28,
        ),
        CagedFile(
            "mte_novo_caged_fora_prazo",
            "CAGEDFOR",
            "MTE Novo CAGED - Movimentações fora do prazo",
            "Movimentações do Novo CAGED declaradas fora do prazo, no mesmo leiaute das "
            "movimentações; a competência de declaração fica em 'competênciadec'. " + _NOTE,
            28,
        ),
        CagedFile(
            "mte_novo_caged_exclusoes",
            "CAGEDEXC",
            "MTE Novo CAGED - Exclusões",
            "Movimentações do Novo CAGED excluídas posteriormente pelo declarante, no leiaute "
            "das movimentações mais 'competênciaexc' e 'indicadordeexclusão'. " + _NOTE,
            30,
        ),
    )
}


def parse_day(value: object) -> date:
    """Data em ``AAAA-MM-DD`` ou ``DD/MM/AAAA``."""
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida '{value}': use AAAA-MM-DD ou DD/MM/AAAA.")


def month_range(first: date, last: date) -> List[Tuple[int, int]]:
    months: List[Tuple[int, int]] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


class NovoCagedDataSource(PdetDataSource):
    """Um CSV por mês e arquivo: ``<chave>_AAAAMM.csv``. Subclasses fixam ``DATASET``."""

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
        if key not in CAGED_FILES:
            raise ValueError(f"Unknown Novo CAGED dataset '{key}'. Known: {sorted(CAGED_FILES)}")
        super().__init__(key, output_path, client=client, lister=lister, extractor=extractor)
        self.spec = CAGED_FILES[key]
        self.EXPECTED_COLUMNS = self.spec.columns

    def _requested_months(
        self,
        anos: Optional[Sequence[object]],
        meses: Optional[Sequence[object]],
        start_date: Optional[object],
        end_date: Optional[object],
    ) -> Optional[List[Tuple[int, int]]]:
        """Meses pedidos, ou ``None`` quando nada foi pedido (vale o último publicado)."""
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
            return None
        low = [ym for ym in months if ym[0] < MIN_YEAR]
        if low:
            raise ValueError(f"Novo CAGED começa em {MIN_YEAR}-01; pedido: {low[0][0]}.")
        return months

    def _published_months(self, years: Sequence[int]) -> List[Tuple[int, int]]:
        found: List[Tuple[int, int]] = []
        for year in years:
            for name in self.lister().names(f"{_BASE}/{year}"):
                if re.fullmatch(rf"{year}(0[1-9]|1[0-2])", name):
                    found.append((year, int(name[4:])))
        return sorted(found)

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
        months = self._requested_months(anos, meses, start_date, end_date)
        warnings: List[str] = []
        if months is None:
            latest_year = datetime.now().year
            published = self._published_months([latest_year]) or self._published_months(
                [latest_year - 1]
            )
            if not published:
                raise ValueError("Nenhum mês do Novo CAGED encontrado no FTP do MTE.")
            months = [published[-1]]
            published_set = {published[-1]}
        else:
            published_set = set(self._published_months(sorted({y for y, _ in months})))
        items: List[PdetItem] = []
        for year, month in months:
            code = f"{year}{month:02d}"
            if (year, month) not in published_set:
                warnings.append(f"{code}: mês ainda não publicado no FTP do MTE.")
                continue
            folder = f"{_BASE}/{year}/{code}"
            name = match_name(
                self.lister().names(folder), rf"{self.spec.prefix}{code}\.7z"
            )
            if name is None:
                warnings.append(f"{code}: sem {self.spec.prefix}{code}.7z (arquivo inexistente).")
                continue
            items.append(PdetItem(code, f"{folder}/{name}", f"{self.spec.prefix} {code}"))
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
    """Subclasse com ``DATASET`` fixo, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    if key not in CAGED_FILES:
        raise KeyError(key)
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (NovoCagedDataSource,), {"DATASET": key})
