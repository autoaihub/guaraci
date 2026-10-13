"""Testes offline do SICONFI (DCA, despesa por função) com cliente falso."""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.core.http import ApiClientError
from guaraci.services.downloads import DownloadService
from guaraci.tesouro import SiconfiClient, SiconfiDcaDespesaFuncaoDataSource

ENTES = [
    {"cod_ibge": 3550308, "ente": "São Paulo", "uf": "SP", "esfera": "M"},
    {"cod_ibge": 35, "ente": "Estado de São Paulo", "uf": "SP", "esfera": "E"},
    {"cod_ibge": 4106902, "ente": "Curitiba", "uf": "PR", "esfera": "M"},
]


def _item(ente, year, conta, valor):
    return {
        "exercicio": year, "instituicao": f"Ente {ente}", "cod_ibge": ente, "uf": "SP",
        "anexo": "DCA-Anexo I-E", "rotulo": None, "coluna": "Despesas Empenhadas",
        "cod_conta": "TotalDespesas", "conta": conta, "valor": valor, "populacao": 100,
    }


class FakeClient(SiconfiClient):
    """Responde ``/entes`` e ``/dca`` em duas páginas, com ``links`` internos."""

    def __init__(self, fail_for=()):
        super().__init__(base_url="https://exemplo.invalid/tt")
        self.calls = []
        self.fail_for = set(fail_for)

    def get_json(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "entes":
            return {"items": ENTES, "hasMore": False, "links": []}
        ente = str(params["id_ente"])
        if ente in self.fail_for:
            raise ApiClientError("boom", category="http_error", retryable=False)
        rows = [
            _item(ente, params["an_exercicio"], "01 - Legislativa", 1.0),
            _item(ente, params["an_exercicio"], "10 - Saúde", 2.0),
            _item(ente, params["an_exercicio"], "10.301 - Atenção Básica", 3.0),
            _item(ente, params["an_exercicio"], "12 - Educação", 4.0),
        ]
        offset = params["offset"]
        page = rows[:2] if offset == 0 else rows[2:]
        return {
            "items": page,
            "hasMore": offset == 0,
            "links": [{"rel": "next", "href": "https://host.oraclevcn.com/next"}],
        }


def _run(tmp_path, client, **kwargs):
    source = SiconfiDcaDespesaFuncaoDataSource(output_path=str(tmp_path), client=client)
    return source.download(output_dir=str(tmp_path), **kwargs)


def test_filters_health_and_paginates(tmp_path):
    client = FakeClient()
    result = _run(tmp_path, client, start_year=2023, entes=["3550308"])
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.columns[0] == "exercicio" and frame.columns[-1] == "populacao"
    assert frame["conta"].to_list() == ["10 - Saúde", "10.301 - Atenção Básica"]
    assert result["rows"] == 2 and result["failed_count"] == 0
    dca = [params for path, params in client.calls if path == "dca"]
    assert [p["offset"] for p in dca] == [0, 2]
    assert all(p["no_anexo"] == "DCA-Anexo I-E" for p in dca)


def test_todas_turns_filter_off(tmp_path):
    result = _run(tmp_path, FakeClient(), start_year=2023, entes=["35"], funcao="todas")
    assert result["rows"] == 4


def test_uf_selects_entes_from_listing(tmp_path):
    client = FakeClient()
    result = _run(tmp_path, client, start_year=2022, end_year=2023, uf=["sp"])
    assert result["documents_found"] == 4  # 2 entes x 2 anos
    queried = {params["id_ente"] for path, params in client.calls if path == "dca"}
    assert queried == {"3550308", "35"}


def test_failed_ente_does_not_abort_batch(tmp_path):
    result = _run(tmp_path, FakeClient(fail_for={"35"}), start_year=2023, entes="3550308,35")
    assert result["failed_count"] == 1 and result["downloaded_count"] == 1
    assert result["rows"] == 2
    assert "falharam" in result["export_warning"]


def test_links_are_never_followed(tmp_path):
    client = FakeClient()
    _run(tmp_path, client, start_year=2023, entes=["35"])
    assert {path for path, _ in client.calls} == {"dca"}


def test_parquet_export_and_year_floor(tmp_path):
    result = _run(tmp_path, FakeClient(), start_year=2023, entes=["35"], output_format="parquet")
    assert result["exported_files"][0].endswith(".parquet")
    with pytest.raises(ValueError):
        _run(tmp_path, FakeClient(), start_year=2013, entes=["35"])


def test_registered_with_schema():
    schema = DownloadService().get_source_schema("siconfi_dca_despesa_funcao")
    assert schema["mode"] == "siconfi api"
    names = {spec["name"] for spec in schema["params"]}
    assert {"start_year", "end_year", "uf", "entes", "funcao"} <= names
