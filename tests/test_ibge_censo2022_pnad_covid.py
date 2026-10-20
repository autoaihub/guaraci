"""Amostra do Censo 2022 (um zip por UF) e PNAD COVID-19 (um zip por mês), sem rede.

Os zips sintéticos imitam os publicados: ``12_AC.zip`` com as quatro tabelas
``*_12_publico.csv`` em ``;`` e CRLF, e ``PNAD_COVID_MM2020.zip`` com um CSV
em vírgula.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.ibge.microdados import IbgeMicrodadosDataSource, RemoteFile
from guaraci.services.downloads import DownloadService


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class _Client:
    def __init__(self, files: Dict[str, bytes]) -> None:
        self.files = files
        self.calls: List[str] = []

    def _payload(self, path: str) -> bytes:
        for suffix, data in self.files.items():
            if path.endswith(suffix):
                return data
        raise AssertionError(f"unexpected path {path}")

    def head(self, path: str) -> RemoteFile:
        self.calls.append(f"HEAD {path}")
        return RemoteFile(url=f"https://x/{path}", size=len(self._payload(path)), last_modified=None)

    def download(self, path: str, destination: Path, **_kwargs) -> int:
        self.calls.append(f"GET {path}")
        data = self._payload(path)
        destination.write_bytes(data)
        return len(data)


def _censo_zip(cod: str) -> bytes:
    return _zip({
        f"Pessoas_{cod}_publico.csv": f"P0010;P0020;V0001\r\n{cod};0001;007,5\r\n".encode(),
        f"Domicilios_{cod}_publico.csv": f"D0010;D0020\r\n{cod};01\r\n".encode(),
        f"Familia_{cod}_publico.csv": f"F0010;F0020\r\n{cod};02\r\n".encode(),
        f"Mortalidade_{cod}_publico.csv": f"M0010 ;M0110\r\n{cod};2\r\n".encode(),
    })


def _run(tmp_path: Path, key: str, client: _Client, **kwargs) -> dict:
    source = IbgeMicrodadosDataSource(output_path=str(tmp_path), dataset=key, client=client)
    return source.download(output_dir=str(tmp_path), **kwargs)


def test_censo2022_one_zip_per_uf_and_one_file_per_uf_and_table(tmp_path):
    client = _Client({"csv/12_AC.zip": _censo_zip("12"), "csv/16_AP.zip": _censo_zip("16")})
    result = _run(
        tmp_path, "ibge_censo2022_amostra", client, start_year=2022,
        ufs=["ap", "AC"], tabelas=["mortalidade", "pessoas"], output_format="csv",
    )
    names = [Path(p).name for p in result["exported_files"]]
    # Ordem do registro: UF pelo código, tabela pela ordem publicada.
    assert names == [
        "ibge_censo2022_amostra_2022_AC_pessoas.csv",
        "ibge_censo2022_amostra_2022_AC_mortalidade.csv",
        "ibge_censo2022_amostra_2022_AP_pessoas.csv",
        "ibge_censo2022_amostra_2022_AP_mortalidade.csv",
    ]
    assert [c for c in client.calls if c.startswith("GET")] == [
        "GET Censos/Censo_Demografico_2022/Microdados_e_Areas_de_Ponderacao/"
        "Microdados_de_acesso_Publico/csv/12_AC.zip",
        "GET Censos/Censo_Demografico_2022/Microdados_e_Areas_de_Ponderacao/"
        "Microdados_de_acesso_Publico/csv/16_AP.zip",
    ]
    pessoas = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert pessoas.rows() == [("12", "0001", "007,5")]
    mortalidade = pl.read_csv(result["exported_files"][1], infer_schema=False)
    assert mortalidade.columns == ["M0010", "M0110"]  # nome publicado, só com strip
    assert result["ufs"] == ["AC", "AP"]
    assert result["editions"] == [2022]
    assert result["documents_found"] == 4
    assert result["encodings"]["2022/AC/pessoas"] == "utf-8"
    assert not list(tmp_path.glob("*.zip"))


def test_censo2022_requires_ufs_and_rejects_unknown(tmp_path):
    client = _Client({})
    with pytest.raises(ValueError, match="ufs is required"):
        _run(tmp_path, "ibge_censo2022_amostra", client, start_year=2022)
    with pytest.raises(ValueError, match="Unknown ufs"):
        _run(tmp_path, "ibge_censo2022_amostra", client, start_year=2022, ufs=["XX"])
    with pytest.raises(ValueError, match="does not apply"):
        _run(tmp_path, "ibge_censo2022_amostra", client, start_year=2022, ufs="AC", meses="05")
    assert client.calls == []


def test_pnad_covid19_months_default_to_all_and_accept_unpadded(tmp_path):
    csv = b"Ano,UF,V1013,B0011\r\n2020,11,5,2\r\n"
    files = {
        f"PNAD_COVID_{m}2020.zip": _zip({f"PNAD_COVID_{m}2020.csv": csv})
        for m in ("05", "06", "07", "08", "09", "10", "11")
    }
    client = _Client(files)
    result = _run(tmp_path, "ibge_pnad_covid19", client, start_year=2020, meses=[7], output_format="parquet")
    (exported,) = result["exported_files"]
    assert Path(exported).name == "ibge_pnad_covid19_2020_07_microdados.parquet"
    assert pl.read_parquet(exported).rows() == [("2020", "11", "5", "2")]
    assert result["meses"] == ["07"]

    everything = _run(tmp_path, "ibge_pnad_covid19", _Client(files), start_year=2020)
    assert everything["documents_found"] == 7
    assert everything["meses"] == ["05", "06", "07", "08", "09", "10", "11"]

    with pytest.raises(ValueError, match="Unknown meses"):
        _run(tmp_path, "ibge_pnad_covid19", client, start_year=2020, meses=["12"])
    with pytest.raises(ValueError, match="does not apply"):
        _run(tmp_path, "ibge_pnad_covid19", client, start_year=2020, ufs=["AC"])


def test_ufs_on_survey_without_recorte_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="does not apply"):
        _run(tmp_path, "ibge_pns", _Client({}), start_year=2019, ufs=["AC"])


def test_registry_declares_recorte_params():
    service = DownloadService()
    censo = service.get_source_schema("ibge_censo2022_amostra")
    covid = service.get_source_schema("ibge_pnad_covid19")
    censo_params = {p["name"]: p for p in censo["params"]}
    covid_params = {p["name"]: p for p in covid["params"]}
    assert censo_params["ufs"]["required"] is True
    assert "SP" in censo_params["ufs"]["allowed_values"]
    assert "mortalidade" in censo_params["tabelas"]["allowed_values"]
    assert "meses" not in censo_params
    assert covid_params["meses"]["required"] is False
    assert covid_params["meses"]["allowed_values"][0] == "05"
    assert "ufs" not in covid_params
    assert covid_params["start_year"]["minimum"] == covid_params["start_year"]["maximum"] == 2020
