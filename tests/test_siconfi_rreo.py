"""Testes offline do SICONFI RREO (Anexo 02, função Saúde) com cliente falso."""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.services.downloads import DownloadService
from guaraci.tesouro import SiconfiClient
from guaraci.tesouro.rreo import SiconfiRreoSaudeDataSource


def _item(ente, year, period, conta, valor):
    return {
        "exercicio": year, "demonstrativo": "RREO", "periodo": period, "periodicidade": "B",
        "instituicao": f"Ente {ente}", "cod_ibge": ente, "uf": "SP", "populacao": 100,
        "anexo": "RREO-Anexo 02", "esfera": "M", "rotulo": "Total das Despesas",
        "coluna": "DESPESAS EMPENHADAS NO BIMESTRE", "cod_conta": "RREO2TotalDespesas",
        "conta": conta, "valor": valor,
    }


class FakeClient(SiconfiClient):
    def __init__(self):
        super().__init__(base_url="https://exemplo.invalid/tt")
        self.calls = []

    def get_json(self, path, params):
        self.calls.append((path, dict(params)))
        rows = [
            _item(params["id_ente"], params["an_exercicio"], params["nr_periodo"], "Legislativa", 1.5),
            _item(params["id_ente"], params["an_exercicio"], params["nr_periodo"], "Saúde", 2.25),
        ]
        page = rows[:1] if params["offset"] == 0 else rows[1:]
        return {"items": page, "hasMore": params["offset"] == 0, "links": []}


def test_filtra_saude_pagina_e_percorre_bimestres(tmp_path):
    client = FakeClient()
    source = SiconfiRreoSaudeDataSource(output_path=str(tmp_path), client=client)
    result = source.download(
        start_year=2024, periodos=["5", "6"], entes=["3550308"], output_dir=str(tmp_path)
    )
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame["conta"].to_list() == ["Saúde", "Saúde"]
    assert frame["valor"].to_list() == ["2.25", "2.25"]
    assert frame["periodo"].to_list() == ["5", "6"]
    assert result["failed_count"] == 0 and result["documents_found"] == 2
    assert all(p["no_anexo"] == "RREO-Anexo 02" and p["co_tipo_demonstrativo"] == "RREO"
               for _, p in client.calls)


def test_piso_de_ano_e_bimestre_invalido(tmp_path):
    source = SiconfiRreoSaudeDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        source.download(start_year=2014, entes=["35"])
    with pytest.raises(ValueError):
        source.download(start_year=2024, periodos=["7"], entes=["35"])


def test_registrada_com_esquema():
    schema = DownloadService().get_source_schema("siconfi_rreo_saude")
    assert schema["mode"] == "siconfi api"
    assert {"start_year", "periodos", "entes", "conta"} <= {p["name"] for p in schema["params"]}
