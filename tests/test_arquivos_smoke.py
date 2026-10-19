"""Smoke opt-in das fontes de arquivo HTTP (rede real).

Desligado por padrão; ``GUARACI_ARQUIVOS_SMOKE=1`` liga. IBAMA baixa o arquivo
inteiro (13 MB), o Vigitel só faz HEAD (o zip tem 87 MB) e a Farmácia Popular
baixa apenas ``pfpbben``.
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.arquivos import HTTP_FILES, HttpFileClient, HttpFileDataSource

SMOKE = os.environ.get("GUARACI_ARQUIVOS_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_ARQUIVOS_SMOKE=1 to enable the live file smoke test"
    ),
]


def test_live_ibama_inteiro(tmp_path):
    key = "ibama_agrotoxicos_comercializacao"
    payload = HttpFileDataSource(output_path=str(tmp_path), dataset=key).download(
        output_dir=str(tmp_path), output_format="csv"
    )
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False, n_rows=5)
    assert frame.columns[0] == "Classe de uso"
    assert len(frame.columns) == 33


def test_live_vigitel_so_head():
    remote = HttpFileClient(timeout_seconds=60).head(HTTP_FILES["vigitel"].resources[0].url)
    assert remote.size and remote.size > 50_000_000


def test_live_farmacia_popular_pfpbben(tmp_path):
    payload = HttpFileDataSource(
        output_path=str(tmp_path), dataset="farmacia_popular_indicadores"
    ).download(output_dir=str(tmp_path), output_format="csv", indicadores=["pfpbben"])
    assert payload["failed_count"] == 0
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False, n_rows=5)
    assert {"co_anomes", "co_ibge"} <= set(frame.columns)


def test_live_mgdi_samu_samuaer(tmp_path):
    payload = HttpFileDataSource(output_path=str(tmp_path), dataset="mgdi_samu").download(
        output_dir=str(tmp_path), output_format="csv", indicadores=["samuaer"]
    )
    assert payload["failed_count"] == 0
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False, n_rows=5)
    assert {"co_ibge", "vl_indicador_calculado_mun"} <= set(frame.columns)


def test_live_pni_e_sisvan_so_head():
    client = HttpFileClient(timeout_seconds=60)
    pni = client.head(HTTP_FILES["pni_doses_aplicadas_arquivos"].resources[11].url)
    assert pni.size and pni.size > 300_000_000
    sisvan = client.head(HTTP_FILES["sisvan_estado_nutricional_arquivos"].resources[0].url)
    assert sisvan.size and sisvan.size > 500_000_000
