"""Parser da saída ``formato=prn`` do TabNet.

A tabela vem dentro de ``<PRE>``: uma linha de cabeçalho e uma por categoria,
separadas por ``;``, rótulos entre aspas e entidades HTML no texto. Fecham o
bloco a linha ``"Total"`` e uma linha ``&``, que são descartadas. Os valores
saem como publicados (decimal com vírgula, ``...`` para dado não disponível).
"""

from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass, field
from typing import List

__all__ = ["PrnTable", "TabnetNoTableError", "clean_header", "parse_prn"]

_PRE_RE = re.compile(r"<PRE[^>]*>(.*?)</PRE>", re.I | re.S)
_SPACES_RE = re.compile(r"\s+")


class TabnetNoTableError(ValueError):
    """A página não trouxe o bloco ``<PRE>`` da tabela."""


@dataclass
class PrnTable:
    header: List[str]
    rows: List[List[str]] = field(default_factory=list)


def clean_header(name: str) -> str:
    """Nome de coluna como publicado, com espaços internos (há tabulações) unificados."""
    return _SPACES_RE.sub(" ", html.unescape(name)).strip()


def _page_error(page: str) -> str:
    text = _SPACES_RE.sub(" ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()
    return text[-300:]


def parse_prn(page: str) -> PrnTable:
    """Cabeçalho e linhas de dados; sem a linha ``Total`` e sem o ``&`` final."""
    match = _PRE_RE.search(page)
    if not match:
        raise TabnetNoTableError(f"Resposta sem tabela <PRE>: {_page_error(page)!r}")
    lines = [line for line in match.group(1).splitlines() if line.strip()]
    lines = [line for line in lines if line.strip() != "&"]
    if not lines:
        raise TabnetNoTableError("Bloco <PRE> vazio.")
    # O csv.reader lê o texto cru: `&quot;` e `&#59;` não podem virar aspas ou
    # separador antes da divisão em campos. O unescape vale por célula.
    parsed = list(csv.reader(lines, delimiter=";", quotechar='"'))
    header = [clean_header(name) for name in parsed[0]]
    rows = []
    for row in parsed[1:]:
        cells = [html.unescape(value).strip() for value in row]
        if cells and cells[0] == "Total":
            continue
        rows.append(cells)
    return PrnTable(header=header, rows=rows)
