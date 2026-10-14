import zipfile
from pathlib import Path

import pytest

from guaraci.prf.acidentes import PrfClient, datasource_for, parse_page

PAGE = """
<table><tr><td><p>Documento CSV de Acidentes 2025 (Agrupados por ocorr&ecirc;ncia)</p></td>
<td><a href="https://drive.google.com/file/d/AAA/view?usp=sharing/download">Baixar planilha</a>
<a href="https://drive.google.com/file/d/ZZZ/view"></a></td></tr>
<tr><td>Documento CSV de Acidentes 2025 (Agrupados por pessoa)</td>
<td><a href="https://drive.google.com/file/d/BBB/view">Baixar planilha</a></td></tr>
<tr><td>Documento CSV de Acidentes 2025 (Agrupados por pessoa - Todas as causas e tipos de acidentes)</td>
<td><a href="https://drive.google.com/file/d/CCC/view">Baixar planilha</a></td></tr>
<tr><td>Documento CSV de multas 2025</td>
<td><a href="https://drive.google.com/file/d/DDD/view">Baixar planilha</a></td></tr></table>
"""


def test_parse_page_keeps_only_the_two_groupings():
    assert parse_page(PAGE) == {("ocorrencia", 2025): "AAA", ("pessoa", 2025): "BBB"}


def test_confirm_url_follows_the_drive_warning_form():
    body = (
        '<form action="https://drive.usercontent.google.com/download" method="get">'
        '<input type="hidden" name="id" value="X"><input type="hidden" name="confirm" value="t">'
        '<input type="hidden" name="uuid" value="u&amp;1"></form>'
    )
    url = PrfClient._confirm_url(body, "https://drive.google.com/uc")
    assert url == "https://drive.usercontent.google.com/download?id=X&confirm=t&uuid=u%261"


class FakeClient:
    def discover(self):
        return {("ocorrencia", 2025): "AAA"}

    def download(self, file_id, destination, *, progress_callback=None):
        csv = '"id";"municipio";"km"\n1;"SÃO PAULO";"146,1"\n'.encode("latin-1")
        with zipfile.ZipFile(destination, "w") as z:
            z.writestr("datatran2025.csv", csv)
        return 1


def test_download_exports_utf8_text_columns(tmp_path: Path):
    source = datasource_for("prf_acidentes_ocorrencias")(str(tmp_path), client=FakeClient())
    result = source.download(start_year=2025, output_format="csv")
    out = Path(result["exported_files"][0])
    assert out.name == "prf_acidentes_ocorrencias_2025.csv"
    text = out.read_text(encoding="utf-8")
    assert "SÃO PAULO" in text and "146,1" in text
    assert not (tmp_path / "prf_acidentes_ocorrencias_2025.zip").exists()


def test_missing_year_is_an_error(tmp_path: Path):
    source = datasource_for("prf_acidentes_ocorrencias")(str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        source.download(start_year=2024, output_format="csv")


def test_schema_exposes_year_window():
    from guaraci.services.downloads import DownloadService

    names = {p["name"] for p in DownloadService().get_source_schema("prf_acidentes_pessoas")["params"]}
    assert {"start_year", "end_year", "output_format"} <= names


# --- transporte: truncamento, zip esperado, erros de socket, .part -------------------------


class _Resp:
    """Resposta de urlopen do Drive: bytes em fluxo, Content-Type e Content-Length opcional."""

    def __init__(self, data: bytes, length=None, content_type="application/zip") -> None:
        import io

        self._buf = io.BytesIO(data)
        self.headers = {"Content-Type": content_type}
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.url = "https://drive.google.com/uc"

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def close(self) -> None:
        pass

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _zip_bytes() -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("datatran2025.csv", b'"id";"km"\n1;"146,1"\n')
    return buffer.getvalue()


def test_download_truncado_pelo_content_length_e_erro_retentavel(tmp_path: Path, monkeypatch):
    from guaraci.prf.acidentes import PrfClientError

    payload = _zip_bytes()
    monkeypatch.setattr(
        "guaraci.prf.acidentes.urlopen",
        lambda *_a, **_k: _Resp(payload[:-4], length=len(payload)),
    )
    destination = tmp_path / "a.zip"
    with pytest.raises(PrfClientError) as info:
        PrfClient(max_attempts=1).download("AAA", destination)
    assert info.value.retryable is True and "truncated" in str(info.value)
    assert not destination.exists()
    assert not (tmp_path / "a.zip.part").exists()


def test_download_sem_content_length_exige_zip_valido(tmp_path: Path, monkeypatch):
    from guaraci.prf.acidentes import PrfClientError

    monkeypatch.setattr(
        "guaraci.prf.acidentes.urlopen", lambda *_a, **_k: _Resp(_zip_bytes()[:30])
    )
    with pytest.raises(PrfClientError, match="zip válido"):
        PrfClient(max_attempts=1).download("AAA", tmp_path / "a.zip")
    assert not (tmp_path / "a.zip").exists()


def test_download_completo_passa(tmp_path: Path, monkeypatch):
    payload = _zip_bytes()
    monkeypatch.setattr(
        "guaraci.prf.acidentes.urlopen", lambda *_a, **_k: _Resp(payload, length=len(payload))
    )
    assert PrfClient(max_attempts=1).download("AAA", tmp_path / "a.zip") == len(payload)
    assert zipfile.is_zipfile(tmp_path / "a.zip")


@pytest.mark.parametrize(
    "error",
    [TimeoutError("t"), ConnectionResetError(10054, "reset"), OSError(104, "socket")],
)
def test_erros_de_socket_viram_erro_retentavel(tmp_path: Path, monkeypatch, error):
    from guaraci.prf.acidentes import PrfClientError

    def boom(*_a, **_k):
        raise error

    monkeypatch.setattr("guaraci.prf.acidentes.urlopen", boom)
    client = PrfClient(max_attempts=1)
    with pytest.raises(PrfClientError) as download:
        client.download("AAA", tmp_path / "a.zip")
    with pytest.raises(PrfClientError) as discover:
        client.discover()
    assert download.value.retryable is True and discover.value.retryable is True


def test_incomplete_read_no_meio_do_fluxo_e_retentado(tmp_path: Path, monkeypatch):
    import http.client

    payload = _zip_bytes()
    calls = []

    class Broken(_Resp):
        def read(self, size: int = -1) -> bytes:
            raise http.client.IncompleteRead(b"ab", 10)

    def fake(*_a, **_k):
        calls.append(1)
        return Broken(b"") if len(calls) == 1 else _Resp(payload, length=len(payload))

    monkeypatch.setattr("guaraci.prf.acidentes.urlopen", fake)
    assert PrfClient(max_attempts=2).download("AAA", tmp_path / "a.zip") == len(payload)
    assert len(calls) == 2


def test_zip_que_nao_e_zip_nao_vira_csv(tmp_path: Path):
    class NotZipClient(FakeClient):
        def download(self, file_id, destination, *, progress_callback=None):
            destination.write_bytes('"id";"km"\n1;"146,1"\n'.encode("latin-1"))
            return 1

    source = datasource_for("prf_acidentes_ocorrencias")(str(tmp_path), client=NotZipClient())
    with pytest.raises(ValueError, match="should be a zip"):
        source.download(start_year=2025, output_format="csv")
    assert list(tmp_path.glob("*.csv")) == []


def test_exportacao_que_falha_nao_deixa_arquivo_final_nem_part(tmp_path: Path, monkeypatch):
    import polars as pl

    def broken_sink(self, path, *args, **kwargs):
        Path(path).write_text("parcial")
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(pl.LazyFrame, "sink_csv", broken_sink)
    source = datasource_for("prf_acidentes_ocorrencias")(str(tmp_path), client=FakeClient())
    with pytest.raises(RuntimeError, match="disco cheio"):
        source.download(start_year=2025, output_format="csv")
    assert not (tmp_path / "prf_acidentes_ocorrencias_2025.csv").exists()
    assert list(tmp_path.glob("*.part")) == []
    assert list(tmp_path.glob("*.tmp.csv")) == []
