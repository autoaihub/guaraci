"""Repasses fundo a fundo do FNS e leitor XLSX, sem rede.

Os casos que valem teste são os que dariam dado plausível e errado: separador
`;` lido como coluna única, acento cp1252 corrompido, BOM virando parte do
nome da primeira coluna, data serial do Excel sem conversão e zero à esquerda
perdido por inferência de tipo.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl
import pytest

from guaraci.fns import FnsRepassesDataSource, discover_links, iter_xlsx_rows, xlsx_to_csv
from guaraci.fns.repasses import RemoteFile
from guaraci.fns.xlsx import XlsxError
from guaraci.services.downloads import DownloadService

BASE = "https://portalfns.saude.gov.br/"
PAGE = f"""
<html><body>
<a href="{BASE}idg_download/repasse-faf-com-populacao-2026-acumulado-ate-julho/">REPASSE FAF COM POPULA&#199;&#195;O &#8211; 2026 (acumulado at&#233; julho)</a>
<a href="{BASE}wp-content/uploads/2026/01/REPASSE-FAF-COM-POPULACAO-2025.xlsx">REPASSE FAF COM POPULAÇÃO &#8211; 2025</a>
<a href="/idg_download/repasse-faf-com-populacao-2024/" target="_blank">REPASSE FAF COM POPULAÇÃO &#8211; 2024</a>
<a href="{BASE}wp-content/uploads/2023/01/REPASSE-FAF-COM-POPULACAO-v4-2022.csv">REPASSE FAF COM <b>POPULAÇÃO</b> &#8211; 2022</a>
<a href="{BASE}wp-content/uploads/2021/12/REPASSE-FAF-COM-POPULACAO-2020.csv">REPASSE FAF COM POPULAÇÃO – 2020</a>
<a href="{BASE}wp-content/uploads/outro.csv">REPASSE FAF SEM POPULAÇÃO - 2022</a>
<a href="{BASE}wp-content/uploads/outro2.csv">Relatório 2022</a>
</body></html>
"""

HEADER = [
    "BLOCO", "GRUPO", "ESTRATÉGIA", "UF", "MUNICIPIO", "CO_MUNICIPIO_IBGE", "QT_POPULACAO",
    "NU_ANO_REFERENCIA_IBGE", "CNPJ", "ENTIDADE", "BANCO", "AGENCIA", "CONTA", "TP_REPASSE",
    "TP_REPASSE_ESTADO", "ST_FAF", "ST_HU", "DT_ULTIMA_LIBERACAO", "VL_BRUTO", "VL_LIQUIDO",
    "VL_SALDO_CONTA", "DT_SALDO_CONTA",
]


def _row(**over) -> list:
    base = {
        "BLOCO": "Assistência Farmacêutica", "GRUPO": "G", "ESTRATÉGIA": "E", "UF": "BA",
        "MUNICIPIO": "SÃO PAULO", "CO_MUNICIPIO_IBGE": "029279", "QT_POPULACAO": "27672",
        "NU_ANO_REFERENCIA_IBGE": "2021", "CNPJ": "00411656000150", "ENTIDADE": "FMS, SAUDE",
        "BANCO": "001", "AGENCIA": "007919", "CONTA": "000000415286", "TP_REPASSE": "MUNICIPAL",
        "TP_REPASSE_ESTADO": "N", "ST_FAF": "S", "ST_HU": "N", "DT_ULTIMA_LIBERACAO": "28/12/2020",
        "VL_BRUTO": "133459,06", "VL_LIQUIDO": "133459,06", "VL_SALDO_CONTA": "-15,5",
        "DT_SALDO_CONTA": "31/12/2020",
    }
    base.update(over)
    return [base[name] for name in HEADER]


def _csv_bytes(delimiter: str, encoding: str, quoted: bool) -> bytes:
    def cell(value: str) -> str:
        return f'"{value}"' if quoted else value

    lines = [delimiter.join(cell(h) for h in HEADER)]
    lines.append(delimiter.join(cell(v) for v in _row()))
    lines.append(delimiter.join(cell(v) for v in _row(MUNICIPIO="LONDRINA")))
    return ("\r\n".join(lines) + "\r\n").encode(encoding)


def _xlsx(path: Path, rows: list, *, extra_sheet: bool = False) -> None:
    """XLSX mínimo: textos compartilhados, números, uma data (estilo 1) e célula vazia."""
    shared: list = []

    def sid(text: str) -> int:
        if text not in shared:
            shared.append(text)
        return shared.index(text)

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;")

    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if value is None:
                continue
            if isinstance(value, tuple) and value[0] == "date":
                cells.append(f'<c r="{ref}" s="1"><v>{value[1]}</v></c>')
            elif isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{sid(value)}</v></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sheet = f'<worksheet {ns}><sheetData>{"".join(body)}</sheetData></worksheet>'
    sst = f'<sst {ns}>' + "".join(f"<si><t>{esc(s)}</t></si>" for s in shared) + "</sst>"
    styles = (
        f'<styleSheet {ns}><numFmts count="1"><numFmt numFmtId="167" formatCode="dd\\/mm\\/yyyy"/></numFmts>'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="167"/></cellXfs></styleSheet>'
    )
    sheets = '<sheet name="Dados" sheetId="1" r:id="rId1"/>'
    rels = '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
    if extra_sheet:
        sheets += '<sheet name="Nota" sheetId="2" r:id="rId2"/>'
        rels += '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
    workbook = (
        f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets></workbook>"
    )
    rels_xml = f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        if extra_sheet:
            z.writestr("xl/worksheets/sheet2.xml", f'<worksheet {ns}><sheetData/></worksheet>')


class _Client:
    """Serve a listagem e os bytes de cada URL no lugar do portal."""

    listing_url = BASE + "downloads/"

    def __init__(self, files: dict) -> None:
        self.files = files  # url da listagem -> (url final, bytes)
        self.downloads = 0

    def listing_html(self) -> str:
        return PAGE

    def head(self, url: str) -> RemoteFile:
        final, payload = self.files[url]
        return RemoteFile(url=final, size=len(payload), last_modified=None)

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        self.downloads += 1
        payload = next(p for u, p in self.files.values() if u == url)
        destination.write_bytes(payload)
        return len(payload)


def test_discover_links_handles_the_three_link_shapes():
    links = discover_links(PAGE, BASE + "downloads/")
    assert sorted(links) == [2020, 2022, 2024, 2025, 2026]
    assert links[2024] == BASE + "idg_download/repasse-faf-com-populacao-2024/"  # relativo resolvido
    assert links[2025].endswith("POPULACAO-2025.xlsx")
    assert links[2022].endswith("v4-2022.csv")  # o ano vem do texto, não do nome do arquivo


def test_xlsx_reader_dates_numbers_and_sparse_cells(tmp_path):
    path = tmp_path / "a.xlsx"
    _xlsx(path, [
        ["A", "B", "C", "D"],
        ["x & y", 355030, ("date", 46022), None],
        ["z", 0.1 + 0.2, ("date", 45000.5), "fim"],
    ], extra_sheet=True)
    rows = list(iter_xlsx_rows(path))
    assert rows[0] == ["A", "B", "C", "D"]
    assert rows[1] == ["x & y", "355030", "31/12/2025", ""]
    assert rows[2] == ["z", "0.30000000000000004", "15/03/2023 12:00:00", "fim"]
    with pytest.raises(XlsxError):
        list(iter_xlsx_rows(path, "Inexistente"))
    bad = tmp_path / "b.xlsx"
    bad.write_bytes(b"nao e zip")
    with pytest.raises(XlsxError):
        list(iter_xlsx_rows(bad))


def _service_files(tmp_path):
    xlsx = tmp_path / "src.xlsx"
    _xlsx(xlsx, [
        [h for h in HEADER],
        _row(CO_MUNICIPIO_IBGE=355030, QT_POPULACAO=11904961, NU_ANO_REFERENCIA_IBGE=2025,
             DT_ULTIMA_LIBERACAO=("date", 46022), VL_BRUTO=236836.54, VL_LIQUIDO=100000,
             VL_SALDO_CONTA="0", DT_SALDO_CONTA=("date", 46022)),
    ])
    return {
        BASE + "wp-content/uploads/2021/12/REPASSE-FAF-COM-POPULACAO-2020.csv": (
            BASE + "wp-content/uploads/2021/12/REPASSE-FAF-COM-POPULACAO-2020.csv",
            _csv_bytes(",", "cp1252", True)),
        BASE + "wp-content/uploads/2023/01/REPASSE-FAF-COM-POPULACAO-v4-2022.csv": (
            BASE + "wp-content/uploads/2023/01/REPASSE-FAF-COM-POPULACAO-v4-2022.csv",
            _csv_bytes(";", "cp1252", False)),
        BASE + "idg_download/repasse-faf-com-populacao-2024/": (
            BASE + "wp-content/uploads/2025/01/REPASSE_FAF_COM_POPULACAO-2024.csv",
            b"\xef\xbb\xbf" + _csv_bytes(";", "utf-8", False)),
        BASE + "wp-content/uploads/2026/01/REPASSE-FAF-COM-POPULACAO-2025.xlsx": (
            BASE + "wp-content/uploads/2026/01/REPASSE-FAF-COM-POPULACAO-2025.xlsx",
            xlsx.read_bytes()),
    }


def test_download_exports_one_utf8_csv_per_year_all_text(tmp_path):
    client = _Client(_service_files(tmp_path))
    out = tmp_path / "out"
    payload = FnsRepassesDataSource(output_path=str(out), client=client).download(
        start_year=2020, end_year=2025, output_format="csv")
    assert payload["years"] == [2020, 2022, 2024, 2025]
    assert payload["downloaded_count"] == 4 and payload["failed_count"] == 0
    assert "2021" in payload["export_warning"] and "2023" in payload["export_warning"]
    assert [Path(p).name for p in payload["exported_files"]] == [
        f"fns_repasses_fundo_a_fundo_{y}.csv" for y in (2020, 2022, 2024, 2025)]
    assert not [p for p in out.iterdir() if "_original" in p.name]  # bruto removido
    for path in map(Path, payload["exported_files"]):
        frame = pl.read_csv(path, infer_schema=False)
        assert frame.columns[0] == "BLOCO"  # sem BOM
        assert len(frame.columns) == 22
    csv_2020 = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert csv_2020["ESTRATÉGIA"][0] == "E"
    row = pl.read_csv(payload["exported_files"][1], infer_schema=False).row(0, named=True)
    assert row["BLOCO"] == "Assistência Farmacêutica"  # acento cp1252 preservado
    assert row["CO_MUNICIPIO_IBGE"] == "029279"  # zero à esquerda
    assert row["VL_SALDO_CONTA"] == "-15,5" and row["VL_BRUTO"] == "133459,06"
    assert row["DT_ULTIMA_LIBERACAO"] == "28/12/2020"
    assert row["ENTIDADE"] == "FMS, SAUDE"  # vírgula dentro do campo sobrevive
    assert pl.read_csv(payload["exported_files"][2], infer_schema=False)["MUNICIPIO"].to_list() == [
        "SÃO PAULO", "LONDRINA"]
    x = pl.read_csv(payload["exported_files"][3], infer_schema=False).row(0, named=True)
    assert x["DT_ULTIMA_LIBERACAO"] == "31/12/2025" and x["VL_BRUTO"] == "236836.54"
    assert x["VL_LIQUIDO"] == "100000" and x["CO_MUNICIPIO_IBGE"] == "355030"


def test_unchanged_file_is_not_downloaded_again(tmp_path):
    client = _Client(_service_files(tmp_path))
    ds = FnsRepassesDataSource(output_path=str(tmp_path / "out"), client=client)
    ds.download(start_year=2022, output_format="csv", keep_raw=True)
    assert client.downloads == 1
    again = ds.download(start_year=2022, output_format="csv", keep_raw=True)
    assert client.downloads == 1 and again["skipped_count"] == 1 and again["downloaded_count"] == 0


def test_year_without_file_and_bad_range_fail_clearly(tmp_path):
    ds = FnsRepassesDataSource(output_path=str(tmp_path), client=_Client({}))
    with pytest.raises(ValueError, match="No FNS repasses file"):
        ds.download(start_year=2010)
    with pytest.raises(ValueError, match="Invalid year range"):
        ds.download(start_year=2001)


def test_ragged_row_stops_the_conversion(tmp_path):
    files = _service_files(tmp_path)
    key = BASE + "wp-content/uploads/2023/01/REPASSE-FAF-COM-POPULACAO-v4-2022.csv"
    final, payload = files[key]
    files[key] = (final, payload + b"so;tres;campos\r\n")
    ds = FnsRepassesDataSource(output_path=str(tmp_path / "out"), client=_Client(files))
    with pytest.raises(ValueError, match="has 3 fields"):
        ds.download(start_year=2022, output_format="csv")


def test_source_is_registered_with_year_params():
    schema = DownloadService().get_source_schema("fns_repasses_fundo_a_fundo")
    assert schema["mode"] == "fns files"
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "output_format", "keep_raw", "timeout"} <= names


def test_xlsx_pula_linhas_com_todas_as_celulas_vazias(tmp_path):
    path = tmp_path / "v.xlsx"
    _xlsx(path, [
        ["A", "B"],
        ["1", "2"],
        ["", ""],
        [None, None],
        ["  ", ""],
        ["3", ""],
    ])
    assert list(iter_xlsx_rows(path)) == [["A", "B"], ["1", "2"], ["3", ""]]
    target = tmp_path / "v.csv"
    assert xlsx_to_csv(path, target) == 2
    assert target.read_text(encoding="utf-8") == "A,B\n1,2\n3,\n"


def test_csv_com_erro_de_conversao_nao_deixa_csv_final_nem_part(tmp_path):
    files = _service_files(tmp_path)
    key = BASE + "wp-content/uploads/2023/01/REPASSE-FAF-COM-POPULACAO-v4-2022.csv"
    final, payload = files[key]
    files[key] = (final, payload + b"so;tres;campos\r\n")
    out = tmp_path / "out"
    ds = FnsRepassesDataSource(output_path=str(out), client=_Client(files))
    with pytest.raises(ValueError, match="has 3 fields"):
        ds.download(start_year=2022, output_format="csv")
    assert not (out / "fns_repasses_fundo_a_fundo_2022.csv").exists()
    assert list(out.glob("*.part")) == []


@pytest.mark.parametrize(
    "error",
    [TimeoutError("t"), ConnectionResetError(10054, "reset"), OSError(104, "socket")],
)
def test_erros_de_socket_viram_erro_retentavel(tmp_path, monkeypatch, error):
    from guaraci.fns.repasses import FnsClient, FnsClientError

    def boom(*_a, **_k):
        raise error

    monkeypatch.setattr("guaraci.fns.repasses.urlopen", boom)
    client = FnsClient(max_attempts=1)
    for call in (
        lambda: client.head("https://x/a.csv"),
        lambda: client.listing_html(),
        lambda: client.download("https://x/a.csv", tmp_path / "a.csv"),
    ):
        with pytest.raises(FnsClientError) as info:
            call()
        assert info.value.retryable is True


def test_incomplete_read_no_download_e_retentado(tmp_path, monkeypatch):
    import http.client

    from guaraci.fns.repasses import FnsClient

    class Resp:
        headers: dict = {}

        def __init__(self, broken: bool) -> None:
            self.broken = broken
            self.sent = False

        def read(self, size=-1):
            if self.broken:
                raise http.client.IncompleteRead(b"ab", 10)
            if self.sent:
                return b""
            self.sent = True
            return b"a,b\n"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    calls = []

    def fake(*_a, **_k):
        calls.append(1)
        return Resp(broken=len(calls) == 1)

    monkeypatch.setattr("guaraci.fns.repasses.urlopen", fake)
    assert FnsClient(max_attempts=2).download("https://x/a.csv", tmp_path / "a.csv") == 4
    assert len(calls) == 2


class _FakeResponse:
    def __init__(self, body: bytes, length: int) -> None:
        self.headers = {"Content-Length": str(length)}
        self._body = body

    def read(self, size=-1):
        body, self._body = self._body, b""
        return body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_truncado_contra_content_length_e_erro_retentavel_sem_part(tmp_path, monkeypatch):
    from guaraci.fns.repasses import FnsClient, FnsClientError

    monkeypatch.setattr(
        "guaraci.fns.repasses.urlopen", lambda *_a, **_k: _FakeResponse(b"a,b\n", 100)
    )
    destination = tmp_path / "a.csv"
    with pytest.raises(FnsClientError, match="truncated: 4 of 100") as info:
        FnsClient(max_attempts=1).download("https://x/a.csv", destination)
    assert info.value.retryable is True
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_byte_invalido_na_conversao_vira_aviso_com_a_contagem(tmp_path):
    files = _service_files(tmp_path)
    key = BASE + "wp-content/uploads/2023/01/REPASSE-FAF-COM-POPULACAO-v4-2022.csv"
    final, payload = files[key]
    files[key] = (final, payload.replace(b"LONDRINA", b"LOND\x81RINA"))  # 0x81 não existe em cp1252
    out = tmp_path / "out"
    result = FnsRepassesDataSource(output_path=str(out), client=_Client(files)).download(
        start_year=2022, output_format="csv"
    )
    assert len(result["exported_files"]) == 1
    assert "1 caracteres" in result["export_warning"]
    assert "U+FFFD" in result["export_warning"]
    assert "_2022_original.csv" in result["export_warning"]
