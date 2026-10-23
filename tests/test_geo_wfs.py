"""WFS genérico (SGB e FUNAI), sem rede: versão por camada, paginação e geometria em WKT."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import polars as pl
import pytest

from guaraci.geo import WFS_FAMILIES, WfsClient, WfsDataSource
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import geo_wfs


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class _FakeWfs:
    """Responde por URL: guarda as consultas e serve páginas de uma tabela fixa."""

    def __init__(self, header: list[str], rows: list[list[str]], *, hits: str | None = None,
                 page_param: bool = True) -> None:
        self.header = header
        self.rows = rows
        self.hits = hits
        self.queries: list[dict] = []
        self.page_param = page_param

    def __call__(self, request, timeout=None):
        q = {k: v[0] for k, v in parse_qs(urlparse(request.full_url).query).items()}
        self.queries.append(q)
        if q.get("resultType") == "hits":
            if self.hits is None:
                from urllib.error import HTTPError

                raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
            return _Response(f'<wfs:FeatureCollection numberOfFeatures="{self.hits}"/>')
        start = int(q.get("startIndex", 0))
        count = int(q["maxFeatures"])
        page = self.rows[start:start + count]
        lines = [",".join(["FID"] + self.header)]
        for i, row in enumerate(page, start=start):
            cells = [f"lay.{i}"] + row
            lines.append(",".join(f'"{c}"' if ("," in c or "\n" in c) else c for c in cells))
        return _Response("\r\n".join(lines) + "\r\n")


def _client(family: str, fake: _FakeWfs) -> WfsClient:
    return WfsClient(WFS_FAMILIES[family].base_url, opener=fake, max_attempts=1)


def test_funai_uses_version_100_with_typename_and_no_typenames(tmp_path):
    fake = _FakeWfs(["cod_aldeia", "nome_aldeia", "the_geom"],
                    [["1", "Apikay", "POINT (-55.1 -23.7)"], ["2", "Anambé", "POINT (-49.6 -3.5)"]])
    source = WfsDataSource("funai_aldeias", output_path=str(tmp_path), client=_client("funai_aldeias", fake))
    result = source.download(output_dir=str(tmp_path), page_size=10)
    first = fake.queries[0]
    assert first["version"] == "1.0.0"
    assert first["typeName"] == "Funai:aldeias_pontos"
    assert "typeNames" not in first
    assert first["sortBy"] == "cod_aldeia"
    assert "srsName" not in first
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.columns == ["cod_aldeia", "nome_aldeia", "the_geom"]  # FID descartada
    assert frame["the_geom"][0] == "POINT (-55.1 -23.7)"
    assert frame["nome_aldeia"][1] == "Anambé"
    assert result["rows"] == 2
    assert result["export_warning"] is None  # hits deu 403: conferência pulada, sem alarme


def test_sgb_paginates_in_110_with_sortby_and_lon_lat_srs(tmp_path):
    rows = [[str(i), "RS", f"POLYGON (({i} 0, 1 1, 0 0, {i} 0))"] for i in range(5)]
    fake = _FakeWfs(["fid", "uf", "geom"], rows, hits="5")
    source = WfsDataSource("sgb_risco_geologico", output_path=str(tmp_path),
                           client=_client("sgb_risco_geologico", fake))
    result = source.download(output_dir=str(tmp_path), page_size=2)
    pages = [q for q in fake.queries if q.get("resultType") != "hits"]
    assert [int(q["startIndex"]) for q in pages] == [0, 2, 4]
    assert all(q["version"] == "1.1.0" and q["sortBy"] == "fid" and q["srsName"] == "EPSG:4326"
               for q in pages)
    assert result["rows"] == 5
    assert result["export_warning"] is None
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.height == 5
    assert frame["geom"][4].startswith("POLYGON ((4 0")
    assert frame.columns == ["fid", "uf", "geom"]


def test_total_mismatch_warns_but_hits_ceiling_does_not(tmp_path):
    rows = [["1", "x"], ["2", "y"]]
    fake = _FakeWfs(["fid", "geom"], rows, hits="7")
    source = WfsDataSource("sgb_risco_geologico", output_path=str(tmp_path),
                           client=_client("sgb_risco_geologico", fake))
    result = source.download(output_dir=str(tmp_path), page_size=10)
    assert "anunciou 7" in result["export_warning"]
    fake2 = _FakeWfs(["fid", "geom"], rows, hits="100000")
    source2 = WfsDataSource("sgb_risco_geologico", output_path=str(tmp_path / "b"),
                            client=_client("sgb_risco_geologico", fake2))
    assert source2.download(output_dir=str(tmp_path / "b"), page_size=10)["export_warning"] is None


def test_camadas_selects_files_and_cql_goes_to_the_server(tmp_path):
    fake = _FakeWfs(["fid", "uf", "geom"], [["1", "RO", "POLYGON ((0 0, 1 1, 0 0))"]], hits="1")
    source = WfsDataSource("sgb_suscetibilidade", output_path=str(tmp_path),
                           client=_client("sgb_suscetibilidade", fake))
    result = source.download(output_dir=str(tmp_path), camadas=["suscet_inundacao"],
                             cql_filter="uf='RO'", page_size=10)
    assert [p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in result["exported_files"]] == [
        "sgb_suscetibilidade_suscet_inundacao.csv"
    ]
    assert all(q["CQL_FILTER"] == "uf='RO'" for q in fake.queries)
    assert fake.queries[0]["typeName"] == "gestao-territorial:suscet_inundacao"
    with pytest.raises(ValueError, match="Camada inválida"):
        source.download(output_dir=str(tmp_path), camadas=["nao_existe"])


def test_repeated_feature_across_pages_is_an_error(tmp_path):
    class _Loop(_FakeWfs):
        def __call__(self, request, timeout=None):
            q = {k: v[0] for k, v in parse_qs(urlparse(request.full_url).query).items()}
            if q.get("resultType") == "hits":
                return super().__call__(request, timeout)
            return _Response("FID,fid\r\nlay.1,1\r\nlay.2,2\r\n")  # ignora startIndex

    fake = _Loop(["fid"], [], hits="4")
    source = WfsDataSource("sgb_risco_geologico", output_path=str(tmp_path),
                           client=_client("sgb_risco_geologico", fake))
    result = source.download(output_dir=str(tmp_path), page_size=2)
    assert result["failed_count"] == 1
    assert "duas páginas" in result["export_warning"]
    assert result["exported_files"] == []


def test_exception_report_is_not_swallowed(tmp_path):
    def opener(request, timeout=None):
        return _Response('<?xml version="1.0" ?><ServiceExceptionReport version="1.2.0"><ServiceException>x</ServiceException></ServiceExceptionReport>')

    source = WfsDataSource("sgb_risco_geologico", output_path=str(tmp_path),
                           client=WfsClient(WFS_FAMILIES["sgb_risco_geologico"].base_url,
                                            opener=opener, max_attempts=1))
    result = source.download(output_dir=str(tmp_path))
    assert result["failed_count"] == 1 and "ExceptionReport" in result["export_warning"]


def test_registry_answers_schema_for_every_key():
    service = DownloadService(sources=geo_wfs.build_sources())
    for key in ("sgb_risco_geologico", "sgb_suscetibilidade", "funai_terras_indigenas", "funai_aldeias"):
        assert service.get_source_schema(key) is not None
