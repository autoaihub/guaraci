"""Testes offline do SICONFI RREO (Anexo 02, função Saúde) com cliente falso."""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.core.http import ApiClientError

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


class FlakyClient(FakeClient):
    """``flaky`` falha na primeira chamada; ``broken`` falha sempre."""

    def __init__(self, flaky=(), broken=()):
        super().__init__()
        self.flaky = set(flaky)
        self.broken = set(broken)

    def get_json(self, path, params):
        if path == "rreo":
            ente = str(params["id_ente"])
            if ente in self.broken:
                self.calls.append((path, dict(params)))
                raise ApiClientError("boom", category="http_error", retryable=False)
            if ente in self.flaky:
                self.flaky.discard(ente)
                self.calls.append((path, dict(params)))
                raise ApiClientError("boom", category="http_error", retryable=False)
        return super().get_json(path, params)


class EntesClient(FakeClient):
    def get_json(self, path, params):
        if path == "entes":
            return {"items": [
                {"cod_ibge": 3550308, "uf": "SP", "esfera": "M"},
                {"cod_ibge": 35, "uf": "BR", "esfera": "E"},
                {"cod_ibge": 53, "uf": "BR", "esfera": "D"},
                {"cod_ibge": 1, "uf": "BR", "esfera": "U"},
            ], "hasMore": False, "links": []}
        return super().get_json(path, params)


def _download(tmp_path, client, **kwargs):
    source = SiconfiRreoSaudeDataSource(output_path=str(tmp_path), client=client)
    return source.download(start_year=2024, periodos=["6"], output_dir=str(tmp_path), **kwargs)


def test_uf_inclui_o_estado_e_o_df(tmp_path):
    client = EntesClient()
    _download(tmp_path, client, uf=["SP"])
    assert {p["id_ente"] for path, p in client.calls if path == "rreo"} == {"3550308", "35"}
    client = EntesClient()
    _download(tmp_path, client, uf=["DF"])
    assert {p["id_ente"] for path, p in client.calls if path == "rreo"} == {"53"}


def test_sem_linhas_remove_o_csv_e_nao_exporta(tmp_path):
    result = _download(tmp_path, FakeClient(), entes=["35"], conta="Inexistente")
    assert result["rows"] == 0 and result["exported_files"] == []
    assert not (tmp_path / "siconfi_rreo_saude.csv").exists()


def test_falha_isolada_e_retentada_e_nao_reprova(tmp_path):
    entes = [str(1000 + i) for i in range(100)]
    client = FlakyClient(flaky={"1005"})
    result = _download(tmp_path, client, entes=entes)
    assert result["failed_count"] == 0 and result["downloaded_count"] == 100
    assert result["export_warning"] is None
    # Uma chamada que falhou e a nova tentativa, que lê duas páginas.
    assert sum(1 for _, p in client.calls if p.get("id_ente") == "1005") == 3


def test_falha_persistente_abaixo_de_1_por_cento_so_avisa(tmp_path):
    entes = [str(1000 + i) for i in range(100)]
    result = _download(tmp_path, FlakyClient(broken={"1005"}), entes=entes)
    assert result["failed_count"] == 0 and result["downloaded_count"] == 99
    assert "cod_ibge: 1005" in result["export_warning"]


def test_falha_persistente_acima_de_1_por_cento_reprova(tmp_path):
    entes = [str(1000 + i) for i in range(100)]
    result = _download(tmp_path, FlakyClient(broken={"1005", "1006"}), entes=entes)
    assert result["failed_count"] == 2
    assert "1005" in result["export_warning"] and "1006" in result["export_warning"]
