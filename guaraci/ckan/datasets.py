"""Especificação de um conjunto CKAN e a leitura do período dos recursos.

Os portais não padronizam nome de recurso nem de arquivo (INSS mistura
``..CAT.202609.ZIP``, ``JUNHO 2023.xlsx`` e ``Juho 2026``), então o período é
tirado do nome e da URL do recurso, nunca gerado. A ordem de busca, da mais
confiável para a menos:

1. ``AAAAMM`` no nome do arquivo da URL, depois no nome do recurso;
2. mês por extenso ou abreviado mais ano ("setembro 2026", "JUN+2026");
3. ``AAAA_MM`` ou ``AAAA-MM``;
4. ``AAAA`` sozinho.

``period_pattern`` (regex com os grupos nomeados ``year`` e, opcionalmente,
``month``) vale antes de tudo isso, para portal que foge do padrão.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional, Tuple
from urllib.parse import unquote, urlsplit

from guaraci.ckan.client import CkanResource

__all__ = ["CkanDataset", "Period", "resource_kind", "resource_period", "url_basename"]

Period = Tuple[int, Optional[int]]  # (ano, mês ou None)

FILE_FORMATS = ("csv", "zip", "xlsx")
_YM = re.compile(r"(?<!\d)((?:19|20)\d{2})(0[1-9]|1[0-2])(?!\d)")
_Y_M = re.compile(r"(?<!\d)((?:19|20)\d{2})[_\-](0[1-9]|1[0-2])(?!\d)")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_WORD_YEAR = re.compile(r"([A-Za-zÀ-ÿ]{3,})[\s_+\-]*(?:de[\s_+\-]*)?((?:19|20)\d{2})(?!\d)")
_MONTHS = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)
    ).lower()


def month_number(word: str) -> Optional[int]:
    """Mês (1 a 12) por nome completo ou abreviatura de 3 letras em português."""
    folded = _fold(word)
    if folded.isdigit():
        number = int(folded)
        return number if 1 <= number <= 12 else None
    for index, name in enumerate(_MONTHS, start=1):
        if folded == name or (len(folded) == 3 and name.startswith(folded)):
            return index
    return None


def url_basename(url: str) -> str:
    """Último segmento do caminho da URL, decodificado (sem query)."""
    return PurePosixPath(unquote(urlsplit(url).path)).name


def resource_kind(resource: CkanResource) -> str:
    """``csv``, ``zip``, ``xlsx`` ou ``outro``: pela extensão da URL, senão pelo ``format``.

    O ``format`` do portal mente (MMA rotula como CSV um link ``.xlsx``), por
    isso a extensão da URL manda.
    """
    suffix = PurePosixPath(urlsplit(resource.url).path).suffix.lower().lstrip(".")
    if suffix in ("csv", "txt"):
        return "csv"
    if suffix in ("zip", "xlsx"):
        return suffix
    if suffix:
        return "outro"
    declared = resource.format.strip().lower()
    return declared if declared in FILE_FORMATS else "outro"


def resource_period(resource: CkanResource, custom: Optional[str] = None) -> Optional[Period]:
    """Período do recurso, ou ``None`` se nome e URL não trazem nenhum."""
    base = url_basename(resource.url)
    name = resource.name
    if custom:
        pattern = re.compile(custom, re.IGNORECASE)
        for text in (name, base):
            found = pattern.search(text)
            if found:
                groups = found.groupdict()
                month = month_number(groups["month"]) if groups.get("month") else None
                return int(groups["year"]), month
    for text in (base, name):
        found = _YM.search(text)
        if found:
            return int(found.group(1)), int(found.group(2))
    for text in (name, base):
        for found in _WORD_YEAR.finditer(text):
            month = month_number(found.group(1))
            if month:
                return int(found.group(2)), month
    for text in (base, name):
        found = _Y_M.search(text)
        if found:
            return int(found.group(1)), int(found.group(2))
    for text in (name, base):
        found = _YEAR.search(text)
        if found:
            return int(found.group(1)), None
    return None


@dataclass(frozen=True)
class CkanDataset:
    """Um conjunto (ou família de conjuntos) CKAN exposto como uma chave do Guaraci.

    ``package_ids`` lista conjuntos conhecidos; ``package_query`` é o ``fq`` do
    ``package_search`` para famílias grandes (por exemplo a organização FHEMIG).
    ``resource_pattern`` e ``exclude_pattern`` são regex sem caixa aplicadas ao
    nome e à URL do recurso. Só entram recursos cujo tipo (ver
    :func:`resource_kind`) é ``file_format``.

    ``period_required`` exige ``anos`` no download (portais com GB por ano).
    ``default_latest`` faz o download sem recorte pegar só o período mais novo
    (com recuo para os anteriores se o mais novo estiver fora do ar).
    ``skip_rows`` descarta linhas de preâmbulo de xlsx antes do cabeçalho.
    """

    key: str
    title: str
    description: str
    base_url: str
    package_ids: Tuple[str, ...] = ()
    package_query: Optional[str] = None
    resource_pattern: Optional[str] = None
    exclude_pattern: Optional[str] = None
    period_pattern: Optional[str] = None
    file_format: str = "csv"
    separator: str = ";"
    encoding: str = "auto"
    member_pattern: Optional[str] = None
    sheet: Optional[str] = None
    browser_user_agent: bool = False
    period_required: bool = False
    default_latest: bool = False
    skip_rows: int = 0

    def __post_init__(self) -> None:
        if self.file_format not in FILE_FORMATS:
            raise ValueError(f"file_format must be one of {FILE_FORMATS}, got '{self.file_format}'.")
        if not self.package_ids and not self.package_query:
            raise ValueError(f"{self.key}: informe package_ids ou package_query.")
        for pattern in (
            self.resource_pattern,
            self.exclude_pattern,
            self.member_pattern,
        ):
            if pattern:
                re.compile(pattern)

    @property
    def has_period(self) -> bool:
        """A chave aceita recorte por ``anos``/``meses``."""
        return self.period_required or self.default_latest or self.period_pattern is not None
