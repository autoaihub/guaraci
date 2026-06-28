"""Tests for the generic spec-driven `FtpDataSource` (phase 5).

The FTP backend is faked, so these run offline. They pin the datasource
contract the service adapter relies on: year clamping, group
normalisation/validation, ``self.data`` population, discovery filter
anchoring, and load/filter/export behaviour.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from guaraci.datasus import ftp_source as ftp_source_mod
from guaraci.datasus.ftp import specs
from guaraci.datasus.ftp_source import FtpDataSource


@pytest.fixture
def fake_backend(monkeypatch):
    """Replace generic_backend.download/discover_summary with recorders."""
    calls: dict = {}

    def fake_download(spec, **kwargs):
        calls["download"] = {"spec": spec.name, **kwargs}
        return {
            "successful_downloads": 2,
            "failed_downloads": [],
            "total_files": 2,
            "paths_by_group": {"PA": ["/cache/PASP2401.parquet", "/cache/PARJ2401.parquet"]},
        }

    def fake_discover_summary(spec, **kwargs):
        calls["discover"] = {"spec": spec.name, **kwargs}
        return {
            "source": spec.name,
            "documents_found": 1,
            "total_size_bytes": 10,
            "by_group": {"PA": 1},
            "by_state": {"SP": 1},
            "sample": [],
            "filters": {"placeholder": True},
        }

    monkeypatch.setattr(ftp_source_mod.generic_backend, "download", fake_download)
    monkeypatch.setattr(
        ftp_source_mod.generic_backend, "discover_summary", fake_discover_summary
    )
    return calls


def test_download_populates_data_and_strips_paths(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.SIA, output_path=str(tmp_path))
    result = ds.download(start_year=2024, end_year=2024, groups=["PA"])

    kw = fake_backend["download"]
    assert kw["years"] == [2024]
    assert kw["groups"] == ["PA"]
    assert "paths_by_group" not in result
    assert result["successful_downloads"] == 2
    assert ds.data["PA"] == ["/cache/PASP2401.parquet", "/cache/PARJ2401.parquet"]


def test_download_defaults_groups_for_grouped_spec(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.SIA, output_path=str(tmp_path))
    ds.download(start_year=2024, end_year=2024)
    assert fake_backend["download"]["groups"] == ["PA"]  # SIA default_groups


def test_download_passes_none_groups_for_ungrouped_spec(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.SINASC, output_path=str(tmp_path))
    ds.download(start_year=2020, end_year=2020)
    assert fake_backend["download"]["groups"] is None


def test_download_validates_groups(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.SIA, output_path=str(tmp_path))
    with pytest.raises(ValueError, match="Unknown sia group"):
        ds.download(start_year=2024, end_year=2024, groups=["ZZ"])


def test_national_spec_drops_states(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.PAINEL_ONCOLOGIA, output_path=str(tmp_path))
    ds.download(start_year=2015, end_year=2015, states=["SP"])
    assert fake_backend["download"]["states"] is None


def test_resolve_years_allows_current_and_clamps_future(
    fake_backend, tmp_path, monkeypatch
) -> None:
    real_datetime = datetime.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return real_datetime(2030, 6, 1, tzinfo=tz)

    monkeypatch.setattr(ftp_source_mod.datetime, "datetime", FrozenDateTime)
    ds = FtpDataSource(specs.SINASC, output_path=str(tmp_path))

    # The in-progress current year (2030) is collectable for surveillance.
    ds.download(start_year=2020, end_year=2030)
    assert fake_backend["download"]["years"] == list(range(2020, 2031))

    # Only genuinely future years (2031) are clamped back to the current year.
    ds.download(start_year=2020, end_year=2031)
    assert fake_backend["download"]["years"] == list(range(2020, 2031))


def test_resolve_years_clamps_start_to_min_year(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.CIHA, output_path=str(tmp_path))  # min_year 2011
    ds.download(start_year=2005, end_year=2012)
    assert fake_backend["download"]["years"] == [2011, 2012]


def test_discover_anchors_filters_to_request(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.SIA, output_path=str(tmp_path))
    payload = ds.discover(start_year=2024, end_year=2024, groups=["PA"], states=["SP"])
    assert payload["filters"] == {
        "start_year": 2024,
        "end_year": 2024,
        "groups": ["PA"],
        "states": ["SP"],
    }


def test_discover_national_has_no_states_filter(fake_backend, tmp_path) -> None:
    ds = FtpDataSource(specs.PAINEL_ONCOLOGIA, output_path=str(tmp_path))
    payload = ds.discover(start_year=2015, end_year=2015)
    assert "states" not in payload["filters"]


def test_load_dataframe_concats_all_groups(tmp_path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    pl.DataFrame({"VALOR": [1]}).write_parquet(a)
    pl.DataFrame({"VALOR": [2]}).write_parquet(b)
    ds = FtpDataSource(specs.SISPRENATAL, output_path=str(tmp_path))
    ds.data["PN"] = [str(a), str(b)]
    df = ds.load_dataframe()
    assert sorted(df["VALOR"].to_list()) == [1, 2]


def test_filter_resolves_common_columns(tmp_path) -> None:
    ds = FtpDataSource(specs.SINASC, output_path=str(tmp_path))
    df = pl.DataFrame(
        {"UF_RES": ["SP", "RJ"], "CODMUNRES": ["355030", "330455"], "SEXO": ["M", "F"]}
    )
    out = ds.filter(df, uf="SP")
    assert out["UF_RES"].to_list() == ["SP"]
    # Unknown refinement keys are ignored, not errored.
    assert ds.filter(df, faixa_etaria="20-29").height == 2


def test_export_writes_csv(tmp_path) -> None:
    ds = FtpDataSource(specs.RESP, output_path=str(tmp_path))
    path = ds.export(pl.DataFrame({"X": [1, 2]}), format="csv", name="resp_test")
    assert path is not None and path.exists()
    assert ds.export(pl.DataFrame(), format="csv") is None  # empty -> nothing
