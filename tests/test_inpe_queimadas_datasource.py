"""Tests for the INPE Queimadas datasource."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from guaraci.inpe.client import InpeQueimadasClientError
from guaraci.inpe.queimadas import InpeQueimadasDataSource

_ANNUAL_HEADER = "id_bdq,foco_id,lat,lon,data_pas,pais,estado,municipio,bioma"
_MONTHLY_HEADER = (
    "id,lat,lon,data_hora_gmt,satelite,municipio,estado,pais,municipio_id,"
    "estado_id,pais_id,numero_dias_sem_chuva,precipitacao,risco_fogo,bioma,frp"
)


def _zip_csv(filename: str, rows: list[str], header: str = _ANNUAL_HEADER) -> bytes:
    text = "\n".join([header, *rows]) + "\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(filename, text)
    return buffer.getvalue()


def _raw_csv(rows: list[str], header: str = _MONTHLY_HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


class _FakeClient:
    base_url = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv"

    def __init__(
        self,
        *,
        annual_listing: dict[str, list[str]] | None = None,
        monthly_listing: list[str] | None = None,
        files: dict[str, bytes] | None = None,
    ) -> None:
        self.annual_listing = annual_listing or {}
        self.monthly_listing = monthly_listing or []
        self.files = files or {}
        self.fetched: list[str] = []

    def list_directory(self, path: str) -> list[str]:
        if path == "mensal/Brasil":
            return self.monthly_listing
        return self.annual_listing.get(path, [])

    def fetch_bytes(self, path: str) -> bytes:
        self.fetched.append(path)
        if path not in self.files:
            raise InpeQueimadasClientError(
                f"not found: {path}", category="configuration"
            )
        return self.files[path]


def _annual_client(years: list[int]) -> _FakeClient:
    dir_path = "anual/Brasil_sat_ref"
    listing = [f"focos_br_ref_{y}.zip" for y in years]
    files = {
        f"{dir_path}/focos_br_ref_{y}.zip": _zip_csv(
            f"focos_br_ref_{y}.csv",
            [
                f" 1{y} , foco-{y} ,  -18.518000 ,  -55.028000 ,{y}-05-15 17:05:00,Brasil,MATO GROSSO DO SUL,RIO VERDE DE MATO GROSSO,Cerrado",
                f" 2{y} , foco-{y}b ,  -3.100000 ,  -60.000000 ,{y}-06-01 12:00:00,Brasil,SÃO PAULO,SAO PAULO,Cerrado",
            ],
        )
        for y in years
    }
    return _FakeClient(annual_listing={dir_path: listing}, files=files)


def test_download_annual_parses_and_casts_numeric(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2003)
    assert payload["documents_found"] == 2
    df = ds.load_dataframe()
    assert df["lat"].dtype.is_numeric()
    assert df["id_bdq"].dtype.is_numeric()
    assert "queimadas_produto" in df.columns
    assert df["queimadas_produto"].to_list() == ["referencia_anual", "referencia_anual"]


def test_year_range_spans_multiple_files(tmp_path: Path) -> None:
    client = _annual_client([2003, 2004])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2004)
    assert payload["documents_found"] == 4
    assert sorted(payload["files_used"]) == [
        "focos_br_ref_2003.zip",
        "focos_br_ref_2004.zip",
    ]


def test_year_not_in_index_is_skipped_with_warning(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2004, output_format="csv")
    assert payload["documents_found"] == 2
    assert "2004" in payload["export_warning"]


def test_states_filter_applies_post_download(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2003, states=["SP"])
    assert payload["documents_found"] == 1
    df = ds.load_dataframe()
    assert df["estado"].to_list() == ["SÃO PAULO"]


def test_states_accepts_full_name(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2003, states=["Mato Grosso do Sul"])
    assert payload["documents_found"] == 1


def test_invalid_state_raises(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    with pytest.raises(ValueError):
        ds.download(start_year=2003, end_year=2003, states=["ZZ"])


def test_todos_satelites_uses_different_directory(tmp_path: Path) -> None:
    dir_path = "anual/Brasil_todos_sats"
    listing = ["focos_br_todos-sats_2003.zip"]
    files = {
        f"{dir_path}/focos_br_todos-sats_2003.zip": _zip_csv(
            "focos_br_todos-sats_2003.csv",
            [" 1 , f1 , -1.0 , -2.0 ,2003-01-01,Brasil,ACRE,RIO BRANCO,Amazônia"],
        )
    }
    client = _FakeClient(annual_listing={dir_path: listing}, files=files)
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2003, dataset="todos_satelites")
    assert payload["documents_found"] == 1
    assert client.fetched == [f"{dir_path}/focos_br_todos-sats_2003.zip"]


def test_invalid_dataset_raises(tmp_path: Path) -> None:
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=_annual_client([2003]))
    with pytest.raises(ValueError):
        ds.download(start_year=2003, end_year=2003, dataset="bogus")


def test_year_below_minimum_raises(tmp_path: Path) -> None:
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=_annual_client([2003]))
    with pytest.raises(ValueError):
        ds.download(start_year=1999)


def test_start_after_end_rejected(tmp_path: Path) -> None:
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=_annual_client([2003]))
    with pytest.raises(ValueError):
        ds.download(start_year=2005, end_year=2003)


def test_months_switches_to_monthly_product(tmp_path: Path) -> None:
    monthly_listing = ["focos_mensal_br_202301.csv", "focos_mensal_br_202302.zip"]
    files = {
        "mensal/Brasil/focos_mensal_br_202301.csv": _raw_csv(
            [
                "abc,-9.5,-44.6,2023-01-01 00:00:00,GOES-19,REDENCAO,PIAUI,Brasil,2208700,22,33,2,0.66,0.06,Cerrado,71.9"
            ]
        ),
        "mensal/Brasil/focos_mensal_br_202302.zip": _zip_csv(
            "focos_mensal_br_202302.csv",
            [
                "def,-9.6,-44.7,2023-02-01 00:00:00,GOES-19,REDENCAO,PIAUI,Brasil,2208700,22,33,3,0.5,0.1,Cerrado,60.0"
            ],
            header=_MONTHLY_HEADER,
        ),
    }
    client = _FakeClient(monthly_listing=monthly_listing, files=files)
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2023, end_year=2023, months=[1, 2])
    assert payload["documents_found"] == 2
    df = ds.load_dataframe()
    assert df["queimadas_produto"].to_list() == ["mensal", "mensal"]
    assert df["risco_fogo"].dtype.is_numeric()
    assert df["frp"].dtype.is_numeric()


def test_month_not_available_is_skipped_with_warning(tmp_path: Path) -> None:
    client = _FakeClient(monthly_listing=[], files={})
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(
        start_year=2003, end_year=2003, months=[1], output_format="csv"
    )
    assert payload["documents_found"] == 0
    assert "not available" in payload["export_warning"]


def test_invalid_month_raises(tmp_path: Path) -> None:
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=_annual_client([2003]))
    with pytest.raises(ValueError):
        ds.download(start_year=2003, end_year=2003, months=[13])


def test_export_and_manifest_written(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(
        start_year=2003, end_year=2003, output_format="parquet", keep_raw=True
    )
    assert len(payload["exported_files"]) == 1
    assert Path(payload["exported_files"][0]).exists()
    assert Path(str(payload["raw_file"])).exists()
    manifest_text = Path(str(payload["manifest_path"])).read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["source"] == "inpe_queimadas"
    assert manifest["request"]["filters"]["dataset"] == "referencia_anual"


def test_no_artifact_warning_without_format_or_raw(tmp_path: Path) -> None:
    client = _annual_client([2003])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2003, end_year=2003)
    assert payload["exported_files"] == []
    assert "No data artifact" in payload["export_warning"]


def test_progress_events(tmp_path: Path) -> None:
    client = _annual_client([2003, 2004])
    ds = InpeQueimadasDataSource(output_path=str(tmp_path), client=client)
    events: list[dict] = []
    ds.download(start_year=2003, end_year=2004, progress_callback=events.append)
    names = [event["event"] for event in events]
    assert names[0] == "download_start"
    assert names[-1] == "download_complete"
    assert names.count("file_completed") == 2
