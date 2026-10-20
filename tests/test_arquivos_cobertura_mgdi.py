"""Cobertura vacinal por residência (parquet no FTP) e grupos MGDI novos, sem rede.

Cobrem o parquet tipado saindo como texto (a taxa decimal não pode virar float), o
``SIZE``/``MDTM`` no lugar do HEAD em ``ftp://`` e o registro dos 57 indicadores.
"""

from __future__ import annotations

import ftplib
import io
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from guaraci.arquivos import HTTP_FILES, HttpFileClient
from guaraci.arquivos.http_files import HttpFileClientError
from guaraci.services.downloads import DownloadService
from tests.test_arquivos_http import _Client, _source, _zip

COBERTURA = "pni_cobertura_vacinal_residencia"

NOVOS_MGDI = {
    "mgdi_cancer_colo_mama": 8,
    "mgdi_cirurgias_especialistas": 3,
    "mgdi_equidade": 22,
    "mgdi_residencias_saude": 10,
    "mgdi_rnds": 7,
    "mgdi_saude_bucal_fluoretacao": 7,
}


def _parquet() -> bytes:
    frame = pl.DataFrame(
        {
            "CO_ANO": ["2023", "2023"],
            "CO_UF": ["SP", "SP"],
            "CO_MUNICIPIO": ["351350", "351350"],
            "NU_IMUNO": ["Polio Injetável (VIP)", "Hepatite B (< 30 Dias)"],
            "QT_DOSE": pl.Series([1048, 7], dtype=pl.Int32),
            "NU_POPULACAO": pl.Series([1304, 0], dtype=pl.Int32),
            "NU_TAXA_COBERTURA": pl.Series(
                [Decimal("0.80"), Decimal("130.50")], dtype=pl.Decimal(18, 2)
            ),
            "DT_CARGA": ["01/07/2026", "01/07/2026"],
        }
    )
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def test_cobertura_aponta_o_parquet_do_ftp_datasus() -> None:
    spec = HTTP_FILES[COBERTURA]
    (resource,) = spec.resources
    assert spec.file_format == "parquet"
    assert resource.url == (
        "ftp://ftp.datasus.gov.br/dissemin/publicos/Dados_Abertos/SIPNIBD/"
        "Cobertura_Residencia.parquet"
    )
    schema = DownloadService().get_source_schema(COBERTURA)
    assert "indicadores" not in {p["name"] for p in schema["params"]}


@pytest.mark.parametrize("fmt", ["csv", "parquet", "sqlite"])
def test_cobertura_exporta_tudo_como_texto(tmp_path: Path, fmt: str) -> None:
    url = HTTP_FILES[COBERTURA].resources[0].url
    payload = _source(tmp_path, COBERTURA, _Client({url: _parquet()})).download(
        output_dir=str(tmp_path), output_format=fmt
    )
    (exported,) = payload["exported_files"]
    assert Path(exported).name == f"{COBERTURA}.{fmt}"
    assert not (tmp_path / "Cobertura_Residencia.parquet").exists()
    if fmt == "csv":
        frame = pl.read_csv(exported, infer_schema=False)
    elif fmt == "parquet":
        frame = pl.read_parquet(exported)
    else:
        import sqlite3

        with sqlite3.connect(exported) as conn:
            rows = conn.execute(
                f"SELECT NU_TAXA_COBERTURA, typeof(QT_DOSE) FROM {COBERTURA}"
            ).fetchall()
        assert rows == [("0.80", "text"), ("130.50", "text")]
        return
    assert all(dtype == pl.String for dtype in frame.dtypes)
    assert frame["NU_TAXA_COBERTURA"].to_list() == ["0.80", "130.50"]
    assert frame["NU_IMUNO"].to_list() == ["Polio Injetável (VIP)", "Hepatite B (< 30 Dias)"]
    assert frame["CO_MUNICIPIO"][0] == "351350"


def test_cobertura_sem_formato_guarda_o_parquet_como_publicado(tmp_path: Path) -> None:
    url = HTTP_FILES[COBERTURA].resources[0].url
    body = _parquet()
    payload = _source(tmp_path, COBERTURA, _Client({url: body})).download(
        output_dir=str(tmp_path)
    )
    assert payload["exported_files"] == []
    assert (tmp_path / "Cobertura_Residencia.parquet").read_bytes() == body


class _FakeFtp:
    calls: list = []
    refuse = False

    def __init__(self, host: str, timeout: int) -> None:
        self.calls.append(("connect", host))

    def __enter__(self) -> "_FakeFtp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def login(self) -> None:
        self.calls.append(("login",))

    def voidcmd(self, cmd: str) -> str:
        self.calls.append(("cmd", cmd))
        if cmd.startswith("MDTM"):
            return "213 20260804115615"
        return "200 ok"

    def size(self, path: str) -> int:
        if self.refuse:
            raise ftplib.error_perm("550 not found")
        return 5090134


def test_head_ftp_usa_size_e_mdtm(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeFtp.calls = []
    _FakeFtp.refuse = False
    monkeypatch.setattr(ftplib, "FTP", _FakeFtp)
    remote = HttpFileClient(timeout_seconds=5).head(HTTP_FILES[COBERTURA].resources[0].url)
    assert remote.size == 5090134
    assert remote.last_modified == "Tue, 04 Aug 2026 11:56:15 GMT"
    assert ("connect", "ftp.datasus.gov.br") in _FakeFtp.calls
    assert (
        "cmd",
        "MDTM /dissemin/publicos/Dados_Abertos/SIPNIBD/Cobertura_Residencia.parquet",
    ) in _FakeFtp.calls


def test_head_ftp_arquivo_ausente_nao_repete(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeFtp.calls = []
    _FakeFtp.refuse = True
    monkeypatch.setattr(ftplib, "FTP", _FakeFtp)
    with pytest.raises(HttpFileClientError) as info:
        HttpFileClient(timeout_seconds=5, max_attempts=3).head(
            "ftp://ftp.datasus.gov.br/x/nada.parquet"
        )
    assert info.value.category == "not_found"
    assert [c for c in _FakeFtp.calls if c[0] == "connect"] == [("connect", "ftp.datasus.gov.br")]


@pytest.mark.parametrize("key,total", sorted(NOVOS_MGDI.items()))
def test_mgdi_novos_registram_um_csv_por_indicador(key: str, total: int) -> None:
    resources = HTTP_FILES[key].resources
    assert len(resources) == total
    assert all(r.url == f"https://demas-dados-abertos.s3.amazonaws.com/csv/{r.code}.csv.zip" for r in resources)
    assert all(r.title for r in resources)
    schema = DownloadService().get_source_schema(key)
    names = {p["name"]: p for p in schema["params"]}
    assert set(names["indicadores"]["allowed_values"]) == {r.code for r in resources}


def test_mgdi_novos_nao_repetem_codigo_de_outra_fonte() -> None:
    novos = [r.code for key in NOVOS_MGDI for r in HTTP_FILES[key].resources]
    assert len(novos) == len(set(novos)) == 57
    antigos = {
        r.code
        for key, spec in HTTP_FILES.items()
        if key not in NOVOS_MGDI and spec.selector == "indicadores"
        for r in spec.resources
    }
    assert not antigos & set(novos)


def test_mgdi_cancer_exporta_o_indicador_pedido(tmp_path: Path) -> None:
    key = "mgdi_cancer_colo_mama"
    body = (
        "co_anomes,co_ibge,vl_indicador_calculado_mun,no_municipio,sg_granularidade\n"
        "202607,355030,\"1.234,5\",São Paulo,MN\n"
    ).encode("utf-8")
    payloads = {r.url: _zip({f"{r.code}.csv": body}) for r in HTTP_FILES[key].resources}
    client = _Client(payloads)
    payload = _source(tmp_path, key, client).download(
        output_dir=str(tmp_path), output_format="csv", indicadores=["ccmec25a64"]
    )
    assert client.downloads == 1
    (exported,) = payload["exported_files"]
    assert Path(exported).name == "mgdi_cancer_colo_mama_ccmec25a64.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame["vl_indicador_calculado_mun"][0] == "1.234,5"
    assert frame["no_municipio"][0] == "São Paulo"
