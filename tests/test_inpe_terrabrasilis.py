"""INPE TerraBrasilis (WFS), sem rede: paginacao, CQL e exclusao da geometria."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import polars as pl
import pytest

import guaraci.core.http as http
from guaraci.inpe.terrabrasilis import (
    DETER_LAYERS,
    PRODES_LAYERS,
    TerraBrasilisClient,
    TerraBrasilisDataSource,
    TerraBrasilisError,
    build_cql,
    parse_attributes,
)
from guaraci.services.downloads import DownloadService

_XSD = """<xsd:complexType name="xType"><xsd:complexContent><xsd:extension base="gml:AbstractFeatureType"><xsd:sequence>
<xsd:element maxOccurs="1" minOccurs="0" name="gid" nillable="true" type="xsd:string"/>
<xsd:element maxOccurs="1" minOccurs="0" name="view_date" type="xsd:date"/>
<xsd:element maxOccurs="1" minOccurs="0" name="geom" type="gml:MultiPolygonPropertyType"/>
<xsd:element maxOccurs="1" minOccurs="0" name="st_multi" type="gml:GeometryPropertyType"/>
</xsd:sequence></xsd:extension></xsd:complexContent></xsd:complexType>
<xsd:element name="x" substitutionGroup="gml:AbstractFeature" type="xType"/>"""


class _Fake(TerraBrasilisClient):
    """Serve paginas fixas e registra os parametros enviados."""

    def __init__(self, rows):
        super().__init__(max_attempts=1)
        self.rows = rows
        self.calls = []

    def describe(self, typename):
        return parse_attributes(_XSD)

    def get_page(self, typename, properties, *, count, start_index, sort_field, cql):
        self.calls.append(
            dict(typename=typename, properties=list(properties), count=count,
                 start=start_index, sort=sort_field, cql=cql)
        )
        chunk = self.rows[start_index:start_index + count]
        lines = ["FID," + ",".join(properties)]
        for r in chunk:
            lines.append(f"x.{r[0]}," + ",".join(r))
        return "\n".join(lines) + "\n"


class _Resp:
    headers: dict = {}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_parse_attributes_exclui_geometria():
    assert parse_attributes(_XSD) == ["gid", "view_date"]


def test_cql_deter_usa_intervalo_semiaberto_em_data():
    spec = DETER_LAYERS["inpe_deter_amazonia"]
    assert build_cql(spec, 2020, 2021) == "view_date >= '2020-01-01' AND view_date < '2022-01-01'"
    assert build_cql(spec, None, None) is None


def test_cql_prodes_usa_ano_inteiro():
    assert build_cql(PRODES_LAYERS["cerrado"], 2010, 2012) == "year >= 2010 AND year <= 2012"
    assert build_cql(PRODES_LAYERS["cerrado"], 2010, None) == "year >= 2010"


def test_paginacao_junta_paginas_e_descarta_fid(tmp_path: Path):
    rows = [(f"{i}_hist", f"2020-01-0{i}") for i in range(1, 6)]
    fake = _Fake(rows)
    ds = TerraBrasilisDataSource("inpe_deter_amazonia", output_path=str(tmp_path), client=fake)
    payload = ds.download(start_year=2020, end_year=2020, page_size=2)
    assert [c["start"] for c in fake.calls] == [0, 2, 4]
    assert all("geom" not in c["properties"] for c in fake.calls)
    assert all(c["sort"] == "gid" for c in fake.calls)
    assert payload["rows"] == 5 and payload["failed_count"] == 0
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns == ["gid", "view_date"]
    assert frame["gid"].to_list()[0] == "1_hist"


def test_prodes_gera_um_csv_por_bioma(tmp_path: Path):
    fake = _Fake([("1", "2020-01-01")])
    ds = TerraBrasilisDataSource("inpe_prodes", output_path=str(tmp_path), client=fake)
    payload = ds.download(biomas=["cerrado", "pampa"])
    names = sorted(Path(p).name for p in payload["exported_files"])
    assert names == ["inpe_prodes_cerrado.csv", "inpe_prodes_pampa.csv"]
    assert {c["typename"] for c in fake.calls} == {
        "prodes-cerrado-nb:yearly_deforestation",
        "prodes-pampa-nb:yearly_deforestation",
    }


def test_bioma_invalido_e_ano_invertido(tmp_path: Path):
    ds = TerraBrasilisDataSource("inpe_prodes", output_path=str(tmp_path), client=_Fake([]))
    with pytest.raises(ValueError):
        ds.download(biomas=["marte"])
    with pytest.raises(ValueError):
        ds.download(start_year=2020, end_year=2019)


def test_exception_report_transitorio_e_repetido(monkeypatch):
    erro = (b'<?xml version="1.0"?><ows:ExceptionReport><ows:ExceptionText>'
            b"pool error Timeout</ows:ExceptionText></ows:ExceptionReport>")
    respostas = [erro, b"FID,gid\nx.1,1\n"]
    seen = []

    def opener(req, timeout):
        seen.append(parse_qs(urlparse(req.full_url).query))
        return _Resp(respostas.pop(0))

    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    client = TerraBrasilisClient(max_attempts=2, opener=opener)
    assert client.request({"request": "GetFeature"}).startswith("FID")
    assert len(seen) == 2
    assert seen[0]["service"] == ["WFS"] and seen[0]["version"] == ["2.0.0"]


def test_exception_report_de_filtro_nao_repete():
    erro = b"<ows:ExceptionReport><ows:ExceptionText>bad cql</ows:ExceptionText></ows:ExceptionReport>"
    client = TerraBrasilisClient(max_attempts=3, opener=lambda req, timeout: _Resp(erro))
    with pytest.raises(TerraBrasilisError) as info:
        client.request({})
    assert info.value.retryable is False


@pytest.mark.parametrize("key", ["inpe_deter_amazonia", "inpe_deter_cerrado", "inpe_prodes"])
def test_schema_registrado(key):
    names = {p["name"] for p in DownloadService().get_source_schema(key)["params"]}
    assert {"start_year", "end_year", "output_format", "page_size"} <= names
    assert ("biomas" in names) == (key == "inpe_prodes")
