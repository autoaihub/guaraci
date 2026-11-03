import io
import struct
import time
import zipfile
from pathlib import Path

import polars as pl
import pytest

from guaraci.inca import IncaClient, IncaClientError, datasource_for


def make_dbf(fields, rows, encoding="cp1252") -> bytes:
    """DBF III mínimo com campos de texto: ``fields`` = [(nome, tamanho)]."""
    record_len = 1 + sum(size for _, size in fields)
    header_len = 32 + 32 * len(fields) + 1
    out = bytearray(struct.pack("<BBBBIHH20x", 3, 126, 10, 13, len(rows), header_len, record_len))
    for name, size in fields:
        out += struct.pack("<11sc4xBB14x", name.encode("ascii"), b"C", size, 0)
    out += b"\r"
    for row in rows:
        out += b" "
        for (_, size), value in zip(fields, row):
            out += value.encode(encoding).ljust(size, b" ")
    out += b"\x1a"
    return bytes(out)


class FakeClient:
    def __init__(self):
        self.calls = []

    def download(self, year, destination, *, local="-1", progress_callback=None):
        self.calls.append((year, local))
        dbf = make_dbf(
            [("SEXO", 1), ("LOCALNAS", 12), ("DTDIAGNO", 10)],
            [("1", "São Paulo", "09/06/2023"), ("2", "Maranhão", "  /  /")],
        )
        with zipfile.ZipFile(destination, "w") as z:
            z.writestr("rhc23.dbf", dbf)
            z.writestr("rhcGeral.def", "def")
        return 1


def test_download_exports_all_columns_with_accents(tmp_path: Path):
    client = FakeClient()
    source = datasource_for("inca_rhc")(str(tmp_path), client=client)
    result = source.download(start_year=2023, output_format="csv")
    out = Path(result["exported_files"][0])
    assert out.name == "inca_rhc_2023.csv"
    frame = pl.read_csv(out, infer_schema=False)
    assert frame.columns == ["SEXO", "LOCALNAS", "DTDIAGNO"]
    assert frame["LOCALNAS"].to_list() == ["São Paulo", "Maranhão"]
    assert client.calls == [(2023, "-1")]
    assert not (tmp_path / "inca_rhc_2023.zip").exists()


def test_keep_raw_and_parquet(tmp_path: Path):
    source = datasource_for("inca_rhc")(str(tmp_path), client=FakeClient())
    result = source.download(start_year=2022, end_year=2023, output_format="parquet", keep_raw=True)
    assert result["downloaded_count"] == 2
    assert (tmp_path / "inca_rhc_2022.zip").exists()
    assert pl.read_parquet(tmp_path / "inca_rhc_2023.parquet").height == 2


def test_year_before_floor_is_an_error(tmp_path: Path):
    source = datasource_for("inca_rhc")(str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        source.download(start_year=1980, output_format="csv")


ACTION = "/RHCWeb/pages/TabuladorHospitalar/consultar.xhtml;jsessionid=ABC"
PAGE_HTML = (
    f'<form id="formDownloadTabulador" name="formDownloadTabulador" method="post" '
    f'action="{ACTION}"><input type="hidden" name="javax.faces.ViewState" '
    'id="j_id1:javax.faces.ViewState:2" value="VS0" /></form>'
)


def partial(body: str = "", view_state: str = "") -> str:
    update = (
        f'<update id="j_id1:javax.faces.ViewState:0"><![CDATA[{view_state}]]></update>'
        if view_state
        else ""
    )
    return f'<?xml version="1.0"?><partial-response><changes>{body}{update}</changes></partial-response>'


YEARS_XML = partial(
    "".join(
        f'<update id="x"><![CDATA[<input name="formDownloadTabulador:anos" type="checkbox" '
        f'value="{y}" />]]></update>'
        for y in (2021, 2022, 2023)
    ),
    "VS1",
)
POLL_XML = partial(
    '<update id="formDownloadTabulador"><![CDATA[<script id="formDownloadTabulador:j_idt392" '
    'type="text/javascript">atualizarDownload = function() {};</script>]]></update>',
    "VS2",
)
READY_XML = partial(
    '<update id="formDownloadTabulador"><![CDATA[<button id="formDownloadTabulador:btDownload">'
    "Download</button>]]></update>",
    "VS3",
)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/xml;charset=UTF-8"):
        self.headers = {"Content-Type": content_type}
        self._stream = io.BytesIO(body)

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class FakeOpener:
    """Entrega as respostas em ordem e guarda cada requisição (URL e corpo)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=None):
        body = request.data.decode() if request.data else ""
        self.requests.append((request.full_url, body))
        return self.responses.pop(0)


def zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("rhc2023.dbf", b"dbf")
    return buffer.getvalue()


def make_client(responses) -> tuple:
    client = IncaClient(poll_seconds=0, sleep=lambda _s: None, max_attempts=1)
    opener = FakeOpener(responses)
    client._opener = opener
    return client, opener


def page():
    return FakeResponse(PAGE_HTML.encode(), "text/html;charset=UTF-8")


def test_client_polls_until_button_and_downloads_zip(tmp_path: Path):
    payload = zip_bytes()
    client, opener = make_client([
        page(),
        FakeResponse(YEARS_XML.encode()),
        FakeResponse(POLL_XML.encode()),
        FakeResponse(POLL_XML.encode()),
        FakeResponse(READY_XML.encode()),
        FakeResponse(payload, "application/zip"),
    ])
    target = tmp_path / "x.zip"
    assert client.download(2023, target) == len(payload)
    assert target.read_bytes() == payload
    assert not (tmp_path / "x.zip.part").exists()
    urls = [url for url, _ in opener.requests]
    assert urls[0].startswith("https://app.inca.gov.br/RHCWeb/pages/TabuladorHospitalar/")
    assert all(url == "https://app.inca.gov.br" + ACTION for url in urls[1:])
    bodies = [body for _, body in opener.requests]
    assert "formDownloadTabulador%3Aestado=-1" in bodies[1]
    assert "formDownloadTabulador%3Aanos=2023" in bodies[2]
    assert "formDownloadTabulador%3Aformato=DBF" in bodies[2]
    assert "javax.faces.ViewState=VS1" in bodies[2]
    assert "formDownloadTabulador%3Aj_idt392=" in bodies[3]
    assert "javax.faces.ViewState=VS2" in bodies[4]
    assert "btDownload" in bodies[5] and "javax.faces.ViewState=VS3" in bodies[5]


def test_client_downloads_at_once_when_file_is_ready(tmp_path: Path):
    client, opener = make_client([
        page(),
        FakeResponse(YEARS_XML.encode()),
        FakeResponse(READY_XML.encode()),
        FakeResponse(zip_bytes(), "application/zip"),
    ])
    assert client.download(2022, tmp_path / "x.zip") > 0
    assert len(opener.requests) == 4


def test_client_rejects_year_outside_published_range(tmp_path: Path):
    client, _ = make_client([page(), FakeResponse(YEARS_XML.encode())])
    with pytest.raises(IncaClientError) as info:
        client.download(1990, tmp_path / "x.zip")
    assert info.value.category == "not_found"
    assert "2021-2023" in str(info.value)


def test_client_explains_when_the_page_has_no_download_form(tmp_path: Path):
    html = b"<html><body>Realizar Login</body></html>"
    client, _ = make_client([FakeResponse(html, "text/html")])
    with pytest.raises(IncaClientError) as info:
        client.download(2023, tmp_path / "x.zip")
    assert info.value.category == "parse"
    assert "RHCWeb" in str(info.value)
    assert "RHCNet" in (info.value.hint or "")


def test_client_times_out_when_never_ready(tmp_path: Path):
    client, _ = make_client([page(), FakeResponse(YEARS_XML.encode())] + [
        FakeResponse(POLL_XML.encode()) for _ in range(500)
    ])
    client.max_wait_seconds = 1
    client._sleep = lambda _s: time.sleep(0.01)
    with pytest.raises(IncaClientError) as info:
        client.download(2023, tmp_path / "x.zip")
    assert info.value.category == "timeout"


def test_client_rejects_html_instead_of_zip_and_cleans_part(tmp_path: Path):
    client, _ = make_client([
        page(),
        FakeResponse(YEARS_XML.encode()),
        FakeResponse(READY_XML.encode()),
        FakeResponse(b"<html>login</html>", "text/html"),
    ])
    with pytest.raises(IncaClientError):
        client.download(2023, tmp_path / "x.zip")
    assert list(tmp_path.iterdir()) == []


def test_schema_exposes_year_window():
    from guaraci.services.downloads import DownloadService

    schema = DownloadService().get_source_schema("inca_rhc")
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "output_format", "keep_raw"} <= names
