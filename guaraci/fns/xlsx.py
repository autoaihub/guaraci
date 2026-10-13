"""Leitor XLSX mínimo, só com a biblioteca padrão, para planilhas grandes.

O Guaraci não depende de ``openpyxl`` nem de ``fastexcel``. Um XLSX é um zip
de XML; aqui a primeira aba (ou a pedida) é lida em fluxo com ``iterparse``,
linha a linha, e o ``sharedStrings.xml`` fica numa lista (cerca de 55 mil
textos no arquivo de repasses de 2025, com 121 MB de ``sheet1.xml``).

Tudo sai como texto. Número sai como foi gravado (sem o ruído de 17 dígitos
do ponto flutuante); célula formatada como data sai ``dd/mm/aaaa``, porque o
número de série do Excel (``46022``) não diz nada a quem lê o CSV. Células
vazias ficam como ``""`` e a linha é preenchida até a última coluna usada.
"""

from __future__ import annotations

import csv
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET

__all__ = ["XlsxError", "iter_xlsx_rows", "list_sheets", "xlsx_to_csv"]

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_EPOCH = datetime(1899, 12, 30)
# Formatos de data embutidos no Excel (ECMA-376, 18.8.30).
_BUILTIN_DATE_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
_QUOTED = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')
_DATE_TOKENS = re.compile(r"[dmyhs]", re.IGNORECASE)


class XlsxError(ValueError):
    """Arquivo que não é um XLSX legível."""


def _column_index(ref: str) -> int:
    """``"AB12"`` vira 27 (base zero)."""
    index = 0
    for char in ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    strings: List[str] = []
    with archive.open("xl/sharedStrings.xml") as handle:
        for _event, element in ET.iterparse(handle, events=("end",)):
            if element.tag == _MAIN + "si":
                # Texto simples (<t>) ou rico (<r><t>...); o fonético (<rPh>) fica de fora.
                parts = [node.text or "" for node in element.findall(_MAIN + "t")]
                for run in element.findall(_MAIN + "r"):
                    parts.extend(node.text or "" for node in run.findall(_MAIN + "t"))
                strings.append("".join(parts))
                element.clear()
    return strings


def _date_styles(archive: zipfile.ZipFile) -> Set[int]:
    """Índices de estilo (atributo ``s`` da célula) cujo formato é data."""
    if "xl/styles.xml" not in archive.namelist():
        return set()
    root = ET.fromstring(archive.read("xl/styles.xml"))
    custom: Dict[int, bool] = {}
    for fmt in root.iter(_MAIN + "numFmt"):
        code = _QUOTED.sub("", fmt.get("formatCode") or "")
        custom[int(fmt.get("numFmtId", "0"))] = bool(_DATE_TOKENS.search(code))
    styles: Set[int] = set()
    cell_xfs = root.find(_MAIN + "cellXfs")
    if cell_xfs is None:
        return styles
    for position, xf in enumerate(cell_xfs.findall(_MAIN + "xf")):
        fmt_id = int(xf.get("numFmtId", "0"))
        is_date = custom[fmt_id] if fmt_id in custom else fmt_id in _BUILTIN_DATE_IDS
        if is_date:
            styles.add(position)
    return styles


def _sheet_targets(archive: zipfile.ZipFile) -> List[Tuple[str, str]]:
    names = archive.namelist()
    if "xl/workbook.xml" not in names:
        raise XlsxError("xl/workbook.xml not found; not an XLSX workbook.")
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    targets: Dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.iter(_PKG_REL + "Relationship"):
            target = (rel.get("Target") or "").lstrip("/")
            targets[rel.get("Id") or ""] = target if target.startswith("xl/") else "xl/" + target
    result: List[Tuple[str, str]] = []
    for sheet in workbook.iter(_MAIN + "sheet"):
        target = targets.get(sheet.get(_REL + "id") or "")
        if target is None or target not in names:
            continue
        result.append((sheet.get("name") or "", target))
    if not result and "xl/worksheets/sheet1.xml" in names:
        result.append(("Sheet1", "xl/worksheets/sheet1.xml"))
    if not result:
        raise XlsxError("No worksheet found in the workbook.")
    return result


def list_sheets(path: Path) -> List[str]:
    """Nomes das abas, na ordem do ``workbook.xml``."""
    try:
        with zipfile.ZipFile(path) as archive:
            return [name for name, _target in _sheet_targets(archive)]
    except zipfile.BadZipFile as exc:
        raise XlsxError(f"{Path(path).name} is not a valid XLSX (zip) file.") from exc


def _format_number(raw: str) -> str:
    if "." not in raw and "E" not in raw and "e" not in raw:
        return raw
    try:
        value = float(raw)
    except ValueError:
        return raw
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def _format_date(raw: str) -> str:
    try:
        moment = _EPOCH + timedelta(days=float(raw))
    except (ValueError, OverflowError):
        return raw
    if moment.hour == moment.minute == moment.second == 0:
        return moment.strftime("%d/%m/%Y")
    return moment.strftime("%d/%m/%Y %H:%M:%S")


def _cell_text(cell: ET.Element, strings: List[str], dates: Set[int]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(_MAIN + "t"))
    value = cell.find(_MAIN + "v")
    raw = value.text if value is not None and value.text is not None else ""
    if raw == "":
        return ""
    if kind == "s":
        try:
            return strings[int(raw)]
        except (ValueError, IndexError) as exc:
            raise XlsxError(f"Invalid shared string index '{raw}'.") from exc
    if kind == "b":
        return "TRUE" if raw == "1" else "FALSE"
    if kind in ("str", "e"):
        return raw
    if int(cell.get("s", "0") or 0) in dates:
        return _format_date(raw)
    return _format_number(raw)


def iter_xlsx_rows(path: Path, sheet: Optional[str] = None) -> Iterator[List[str]]:
    """Linhas da aba (a primeira, se ``sheet`` não for dado), todas como texto."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise XlsxError(f"{Path(path).name} is not a valid XLSX (zip) file.") from exc
    with archive:
        sheets = _sheet_targets(archive)
        if sheet is None:
            target = sheets[0][1]
        else:
            matches = [t for n, t in sheets if n == sheet]
            if not matches:
                raise XlsxError(f"Sheet '{sheet}' not found. Available: {[n for n, _ in sheets]}")
            target = matches[0]
        strings = _shared_strings(archive)
        dates = _date_styles(archive)
        width = 0
        with archive.open(target) as handle:
            for _event, row in ET.iterparse(handle, events=("end",)):
                if row.tag != _MAIN + "row":
                    continue
                cells: Dict[int, str] = {}
                for position, cell in enumerate(row.findall(_MAIN + "c")):
                    ref = cell.get("r")
                    column = _column_index(ref) if ref else position
                    cells[column] = _cell_text(cell, strings, dates)
                row.clear()
                if not cells:
                    continue
                width = max(width, max(cells) + 1)
                yield [cells.get(i, "") for i in range(width)]


def xlsx_to_csv(path: Path, target: Path, sheet: Optional[str] = None) -> int:
    """Grava a aba como CSV UTF-8 (vírgula, aspas só onde precisa). Devolve as linhas de dados.

    A primeira linha é o cabeçalho, com ``strip()`` em cada nome. Linhas mais
    curtas que ele são completadas com vazio; mais longas só passam se o
    excedente estiver vazio.
    """
    header_width = 0
    count = 0
    with open(target, "w", encoding="utf-8", newline="") as sink:
        writer = csv.writer(sink, lineterminator="\n")
        for number, row in enumerate(iter_xlsx_rows(path, sheet), start=1):
            if number == 1:
                row = [name.strip() for name in row]
                header_width = len(row)
            else:
                if len(row) > header_width and any(row[header_width:]):
                    raise XlsxError(f"Row {number} has data beyond the {header_width} header columns.")
                row = (row + [""] * header_width)[:header_width]
                count += 1
            writer.writerow(row)
    return count
