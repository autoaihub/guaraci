import struct
import zipfile
from pathlib import Path

import polars as pl
import pytest

from guaraci.inca import IncaClient, IncaClientError, datasource_for
from guaraci.inca.rhc import parse_status


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

    def download(self, year, destination, *, local="todosho_sp", progress_callback=None):
        self.calls.append((year, local))
        dbf = make_dbf(
            [("SEXO", 1), ("LOCALNAS", 12), ("DTDIAGNO", 10)],
            [("1", "São Paulo", "09/06/2023"), ("2", "Maranhão", "  /  /")],
        )
        with zipfile.ZipFile(destination, "w") as z:
            z.writestr("rhc23.dbf", dbf)
            z.writestr("rhcGeral.def", "def")
        return 1


def test_parse_status_reads_single_quoted_json():
    assert parse_status("{'status':'1'}") == 1
    assert parse_status("{'status':'2'}") == 2
    with pytest.raises(IncaClientError):
        parse_status("<html>")


def test_download_exports_all_columns_with_accents(tmp_path: Path):
    client = FakeClient()
    source = datasource_for("inca_rhc")(str(tmp_path), client=client)
    result = source.download(start_year=2023, output_format="csv")
    out = Path(result["exported_files"][0])
    assert out.name == "inca_rhc_2023.csv"
    frame = pl.read_csv(out, infer_schema=False)
    assert frame.columns == ["SEXO", "LOCALNAS", "DTDIAGNO"]
    assert frame["LOCALNAS"].to_list() == ["São Paulo", "Maranhão"]
    assert client.calls == [(2023, "todosho_sp")]
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


def test_client_polls_until_ready(monkeypatch, tmp_path: Path):
    client = IncaClient(poll_seconds=0, sleep=lambda _s: None)
    states = iter([1, 1, 2])
    monkeypatch.setattr(client, "_ensure_session", lambda local: None)
    monkeypatch.setattr(client, "_post_status", lambda local, year, token: next(states))

    class Response:
        headers = {"Content-Type": "application/octet-stream"}

        def __init__(self):
            self._chunks = [b"PK-data", b""]

        def read(self, _n):
            return self._chunks.pop(0)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(client, "_open", lambda request: Response())
    target = tmp_path / "x.zip"
    assert client.download(2023, target) == 7
    assert target.read_bytes() == b"PK-data"
    assert any(c.name == "downloadToken" for c in client._jar)


def test_client_times_out_when_never_ready(monkeypatch, tmp_path: Path):
    client = IncaClient(max_wait_seconds=1, poll_seconds=0, sleep=lambda _s: None)
    monkeypatch.setattr(client, "_ensure_session", lambda local: None)
    monkeypatch.setattr(client, "_post_status", lambda local, year, token: 1)
    with pytest.raises(IncaClientError):
        client.download(2023, tmp_path / "x.zip")


def test_schema_exposes_year_window():
    from guaraci.services.downloads import DownloadService

    schema = DownloadService().get_source_schema("inca_rhc")
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "output_format", "keep_raw"} <= names
