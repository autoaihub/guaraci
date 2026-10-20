"""Fontes ambientais de arquivo HTTP (INPE AQ1km e SISAM), sem rede.

Os CSV sintéticos imitam o cabeçalho real de cada fonte, conferido ao vivo em
2026-10-20: nomes com acento e espaço, decimal como publicado e, no SISAM, o zip
de membro único por ano com recorte obrigatório.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from guaraci.arquivos import HTTP_FILES
from guaraci.services.downloads import DownloadService
from tests.test_arquivos_http import _Client, _source, _url, _zip

AQ = "inpe_area_queimada_biomas"
SISAM = "inpe_sisam"

_AQ_CSV = (
    "Ano,Mês,Amazônia,Caatinga,Cerrado,Mata Atlântica,Pampa,Pantanal,Total mensal\r\n"
    "2002,09,60039,12640,73926,9016,307,6724,162652\r\n"
    "Total anual,,80157,27983,113518,12616,358,1542,236174\r\n"
).encode("utf-8")
_SISAM_CSV = (
    "datahora,uf_nome,municipio_nome,longitude,latitude,co_ppb,no2_ppb,o3_ppb,"
    "pm25_ugm3,so2_ugm3,precipitacao_mmdia,temperatura_c,umidade_relativa_percentual,"
    "vento_direcao_grau,vento_velocidade_ms\n"
    "2018-01-01 00:00:00,ACRE,ACRELÂNDIA,-67.05,-9.82,120.1,0.5,10.2,5.3,0.1,2.0,"
    "24.1,90.0,180.0,1.2\n"
).encode("utf-8")




def test_area_queimada_mantem_linha_de_total_anual_como_texto(tmp_path: Path) -> None:
    client = _Client({_url(AQ): _AQ_CSV})
    payload = _source(tmp_path, AQ, client).download(
        output_dir=str(tmp_path), output_format="csv"
    )
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns[1] == "Mês" and frame.columns[-1] == "Total mensal"
    assert frame["Mês"].to_list() == ["09", None]
    assert frame["Ano"][1] == "Total anual"
    assert "km²" in HTTP_FILES[AQ].description


def test_sisam_registra_um_zip_por_ano_de_2000_a_2019() -> None:
    resources = HTTP_FILES[SISAM].resources
    assert [r.code for r in resources] == [str(a) for a in range(2000, 2020)]
    assert resources[0].url == (
        "https://dataserver-coids.inpe.br/queimadas/queimadas/sisam/dados_sisam-2000.zip"
    )
    description = HTTP_FILES[SISAM].description
    assert "MODELO" in description and "2019" in description


def test_sisam_exporta_so_o_ano_pedido(tmp_path: Path) -> None:
    payloads = {
        r.url: _zip({f"task_9045.dados_sisam.{r.code}.csv": _SISAM_CSV})
        for r in HTTP_FILES[SISAM].resources
    }
    client = _Client(payloads)
    payload = _source(tmp_path, SISAM, client).download(
        output_dir=str(tmp_path), output_format="csv", anos=[2018]
    )
    assert client.downloads == 1
    (exported,) = payload["exported_files"]
    assert Path(exported).name == f"{SISAM}_2018.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame["municipio_nome"][0] == "ACRELÂNDIA"
    assert frame["pm25_ugm3"][0] == "5.3"


def test_sisam_sem_anos_ou_fora_da_serie_e_rejeitado(tmp_path: Path) -> None:
    client = _Client({})
    with pytest.raises(ValueError, match="anos"):
        _source(tmp_path, SISAM, client).download(output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="Unknown anos"):
        _source(tmp_path, SISAM, client).download(output_dir=str(tmp_path), anos=[2020])
    assert client.downloads == 0


def test_registro_das_fontes_ambientais() -> None:
    service = DownloadService()
    for key, mode in (
        (AQ, "inpe files"),
    ):
        schema = service.get_source_schema(key)
        assert schema["mode"] == mode
        assert "anos" not in {p["name"] for p in schema["params"]}
    sisam = service.get_source_schema(SISAM)
    names = {p["name"]: p for p in sisam["params"]}
    assert sisam["mode"] == "inpe files"
    assert names["anos"]["required"] is True
    assert names["anos"]["default"] == ["2019"]
    assert "meses" not in names
    service.validate_source_params(SISAM, {"anos": ["2005"]})
