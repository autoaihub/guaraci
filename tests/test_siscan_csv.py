"""SISCAN em CSV (FTP ``SISCAN/SISCAN/``), sem rede.

Cobrem o recorte obrigatório por tabela e ano, o CSV ``;`` com cabeçalho entre
aspas e números sem aspas, o cliente FTP (tamanho, data, truncamento, 550) e o
registro da fonte.
"""

from __future__ import annotations

import ftplib
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.arquivos.http_files import HttpFileClientError, RemoteFile
from guaraci.datasus.siscan_csv import (
    SISCAN_CSV,
    SISCAN_CSV_KEY,
    FtpFileClient,
    SiscanCsvDataSource,
)
from guaraci.services.downloads import DownloadService

_HISTO = (
    '"CO_SEQ_SISCAN_HISTO_MAMA_PACNT";"CO_UF_RESIDENCIA";"CO_MUN_RESIDENCIA";'
    '"CO_IDADE_PACIENTE";"CO_PACIENTE";"SG_SEXO";"SG_UF_RESIDENCIA"\r\n'
    '38225;"28";"280030";"052";52307261;"F";"SE"\r\n'
    '38097;"35";"352042";"051";27324107;"F";"SP"\r\n'
).encode("ascii")


class _Client:
    """Serve bytes por URL no lugar do FTP."""

    def __init__(self, payloads: Dict[str, bytes]) -> None:
        self.payloads = payloads
        self.downloaded: List[str] = []

    def head(self, url: str) -> RemoteFile:
        return RemoteFile(url=url, size=len(self.payloads[url]), last_modified="20260109190013")

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        self.downloaded.append(url)
        destination.write_bytes(self.payloads[url])
        return len(self.payloads[url])


def _all(body: bytes) -> Dict[str, bytes]:
    return {r.url: body for r in SISCAN_CSV.resources}


def test_registra_dez_tabelas_de_2013_a_2025() -> None:
    resources = SISCAN_CSV.resources
    assert len(resources) == 130
    assert resources[0].code == "CITO_COLO_2013"
    assert resources[0].url == (
        "ftp://ftp.datasus.gov.br/dissemin/publicos/SISCAN/SISCAN/SISCAN_CITO_COLO_2013.csv"
    )
    assert resources[-1].url.endswith("SISCAN_MAMOGRAFIA_PACNT_2025.csv")


def test_recorta_tabela_e_ano_e_exporta_texto(tmp_path: Path) -> None:
    client = _Client(_all(_HISTO))
    source = SiscanCsvDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv",
        tabelas=["histo_mama_pacnt"], anos=["2013", 2014],
    )
    assert payload["documents_found"] == 2
    assert [Path(u).name for u in client.downloaded] == [
        "SISCAN_HISTO_MAMA_PACNT_2013.csv", "SISCAN_HISTO_MAMA_PACNT_2014.csv",
    ]
    names = [Path(p).name for p in payload["exported_files"]]
    assert names == [f"{SISCAN_CSV_KEY}_HISTO_MAMA_PACNT_2013.csv",
                     f"{SISCAN_CSV_KEY}_HISTO_MAMA_PACNT_2014.csv"]
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns[0] == "CO_SEQ_SISCAN_HISTO_MAMA_PACNT"
    assert frame["CO_IDADE_PACIENTE"].to_list() == ["052", "051"]
    assert frame["CO_PACIENTE"].to_list() == ["52307261", "27324107"]
    # Sem keep_raw, o CSV publicado sai depois da exportação.
    assert not list(tmp_path.glob(f"{SISCAN_CSV_KEY}__*"))


def test_sem_tabelas_ou_anos_nao_baixa_nada(tmp_path: Path) -> None:
    client = _Client(_all(_HISTO))
    source = SiscanCsvDataSource(output_path=str(tmp_path), client=client)
    with pytest.raises(ValueError, match="tabelas"):
        source.download(output_dir=str(tmp_path), anos=[2020])
    with pytest.raises(ValueError, match="anos"):
        source.download(output_dir=str(tmp_path), tabelas=["HISTO_MAMA"])
    with pytest.raises(ValueError, match="Unknown tabelas"):
        source.download(output_dir=str(tmp_path), tabelas=["SISCOLO"], anos=[2020])
    with pytest.raises(ValueError, match="Unknown anos"):
        source.download(output_dir=str(tmp_path), tabelas=["HISTO_MAMA"], anos=[2012])
    assert client.downloaded == []


def test_pula_arquivo_de_mesmo_tamanho(tmp_path: Path) -> None:
    client = _Client(_all(_HISTO))
    source = SiscanCsvDataSource(output_path=str(tmp_path), client=client)
    source.download(output_dir=str(tmp_path), tabelas=["CITO_MAMA"], anos=[2025])
    again = source.download(output_dir=str(tmp_path), tabelas=["CITO_MAMA"], anos=[2025])
    assert again["skipped_count"] == 1
    assert len(client.downloaded) == 1


class _FakeFtp:
    """Imita o ``ftplib.FTP`` o bastante para o ``FtpFileClient``."""

    files: Dict[str, bytes] = {}
    size_override: Dict[str, int] = {}

    def __init__(self, host: str, timeout: int = 0) -> None:
        self.host = host

    def __enter__(self) -> "_FakeFtp":
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def login(self) -> None:
        pass

    def set_pasv(self, value: bool) -> None:
        pass

    def voidcmd(self, cmd: str) -> str:
        return "200 ok"

    def _get(self, path: str) -> bytes:
        if path not in self.files:
            raise ftplib.error_perm("550 File not found")
        return self.files[path]

    def size(self, path: str) -> int:
        return self.size_override.get(path, len(self._get(path)))

    def sendcmd(self, cmd: str) -> str:
        self._get(cmd.split(" ", 1)[1])
        return "213 20260109190013"

    def retrbinary(self, cmd: str, callback, blocksize: int = 8192) -> str:
        data = self._get(cmd.split(" ", 1)[1])
        for start in range(0, len(data), 4):
            callback(data[start:start + 4])
        return "226 done"


_PATH = "/dissemin/publicos/SISCAN/SISCAN/SISCAN_HISTO_MAMA_2025.csv"
_URL = f"ftp://ftp.datasus.gov.br{_PATH}"


@pytest.fixture
def fake_ftp(monkeypatch):
    monkeypatch.setattr(_FakeFtp, "files", {_PATH: _HISTO})
    monkeypatch.setattr(_FakeFtp, "size_override", {})
    return _FakeFtp


def test_cliente_ftp_head_e_download(tmp_path: Path, fake_ftp) -> None:
    client = FtpFileClient(ftp_factory=fake_ftp)
    remote = client.head(_URL)
    assert remote.size == len(_HISTO)
    assert remote.last_modified == "20260109190013"
    seen: List[int] = []
    dest = tmp_path / "x.csv"
    assert client.download(_URL, dest, progress_callback=seen.append) == len(_HISTO)
    assert dest.read_bytes() == _HISTO
    assert seen[-1] == len(_HISTO)
    assert not (tmp_path / "x.csv.part").exists()


def test_cliente_ftp_rejeita_truncado_e_inexistente(tmp_path: Path, fake_ftp) -> None:
    fake_ftp.size_override[_PATH] = len(_HISTO) + 10
    client = FtpFileClient(ftp_factory=fake_ftp, max_attempts=1)
    with pytest.raises(HttpFileClientError, match="truncated"):
        client.download(_URL, tmp_path / "x.csv")
    assert not list(tmp_path.iterdir())
    with pytest.raises(HttpFileClientError) as info:
        client.head(_URL.replace("2025", "2012"))
    assert info.value.retryable is False


def test_fonte_registrada_com_padrao_pequeno() -> None:
    schema = DownloadService().get_source_schema(SISCAN_CSV_KEY)
    params = {p["name"]: p for p in schema["params"]}
    assert params["tabelas"]["required"] and params["anos"]["required"]
    assert params["tabelas"]["default"] == ["HISTO_MAMA"]
    assert params["anos"]["default"] == ["2025"]
    assert len(params["tabelas"]["allowed_values"]) == 10
    assert "states" not in params and "start_year" not in params
