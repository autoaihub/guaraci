"""Testes offline do IPEADATA (OData v4) com cliente falso."""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.gestao_publica.rest import JsonApiClient
from guaraci.ipea import (
    DEFAULT_SERIES,
    DEFAULT_SERIES_CODES,
    IpeadataMetadadosDataSource,
    IpeadataSeriesDataSource,
)
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import ipea as registro


def _valor(code, ano, valor, terr="1100015"):
    return {
        "SERCODIGO": code, "VALDATA": f"{ano}-01-01T00:00:00-02:00", "VALVALOR": valor,
        "NIVNOME": "Municípios", "TERCODIGO": terr,
    }


class FakeOData(JsonApiClient):
    def __init__(self):
        super().__init__("http://exemplo.invalid/api/odata4")
        self.paths = []

    def get_json(self, path="", params=None, *, headers=None):
        self.paths.append(path)
        if path == "ValoresSerie(SERCODIGO='POPTOT')":
            return {"value": [_valor("POPTOT", 1991, "17.10"), _valor("POPTOT", 2000, "20")]}
        if path == "ValoresSerie(SERCODIGO='AVS_IVS')":
            return {"value": [_valor("AVS_IVS", 2010, "0.3")]}
        if path.startswith("ValoresSerie"):
            return {"value": []}
        if path == "Metadados":
            return {"value": [
                {"SERCODIGO": "A", "SERNOME": "Série A", "PERNOME": "Anual"},
                {"SERCODIGO": "B", "SERNOME": "Série B", "PERNOME": "Mensal", "SERSTATUS": "A"},
            ]}
        if path == "Territorios":
            return {"value": [{"NIVNOME": "Estados", "TERCODIGO": "11", "TERNOME": "Rondônia"}]}
        raise AssertionError(path)


def test_series_junta_as_series_num_csv_e_preserva_digitos(tmp_path):
    client = FakeOData()
    source = IpeadataSeriesDataSource(output_path=str(tmp_path), client=client)
    result = source.download(series="POPTOT,AVS_IVS", output_dir=str(tmp_path))
    assert client.paths == ["ValoresSerie(SERCODIGO='POPTOT')", "ValoresSerie(SERCODIGO='AVS_IVS')"]
    assert result["rows"] == 3 and result["rows_by_series"] == {"POPTOT": 2, "AVS_IVS": 1}
    frame = pl.read_csv(tmp_path / "ipeadata_series.csv", infer_schema=False)
    assert frame.columns == ["SERCODIGO", "VALDATA", "VALVALOR", "NIVNOME", "TERCODIGO"]
    assert frame["VALVALOR"].to_list() == ["17.10", "20", "0.3"]
    assert frame["TERCODIGO"][0] == "1100015"


def test_series_inexistente_avisa_e_codigo_invalido_e_recusado(tmp_path):
    source = IpeadataSeriesDataSource(output_path=str(tmp_path), client=FakeOData())
    result = source.download(series=["POPTOT", "NAOEXISTE"], output_dir=str(tmp_path))
    assert "NAOEXISTE" in result["export_warning"]
    with pytest.raises(ValueError, match="inválido"):
        source.download(series=["X')?$top=1&('"], output_dir=str(tmp_path))


def test_series_padrao_e_a_lista_congelada(tmp_path):
    client = FakeOData()
    IpeadataSeriesDataSource(output_path=str(tmp_path), client=client).download(output_dir=str(tmp_path))
    assert len(client.paths) == len(DEFAULT_SERIES_CODES)
    assert len(set(DEFAULT_SERIES_CODES)) == len(DEFAULT_SERIES_CODES) <= 200
    assert not any(code.startswith(("ADH_", "IDHM")) for code in DEFAULT_SERIES_CODES)
    assert all(motivo for _, motivo in DEFAULT_SERIES)


def test_metadados_grava_catalogo_e_territorios(tmp_path):
    source = IpeadataMetadadosDataSource(output_path=str(tmp_path), client=FakeOData())
    result = source.download(output_dir=str(tmp_path))
    assert result["rows_by_table"] == {"Metadados": 2, "Territorios": 1}
    meta = pl.read_csv(tmp_path / "ipeadata_metadados.csv", infer_schema=False)
    assert meta.columns == ["SERCODIGO", "SERNOME", "PERNOME", "SERSTATUS"]
    assert meta["SERSTATUS"].to_list() == [None, "A"]
    assert (tmp_path / "ipeadata_territorios.csv").exists()


def test_registro_responde_schema_das_duas_chaves():
    service = DownloadService(sources=registro.build_sources())
    for key in ("ipeadata_series", "ipeadata_metadados"):
        assert service.get_source_schema(key)
