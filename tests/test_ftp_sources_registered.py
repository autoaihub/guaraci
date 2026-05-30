"""Tests that the 11 phase-5 FTP systems are registered platform sources.

Verifies registry presence, schema shape per spec dimensions, and that a
job run dispatches into FtpDataSource (FTP backend faked, offline).
"""

from __future__ import annotations

import pytest

from guaraci.datasus import ftp_source as ftp_source_mod
from guaraci.datasus.ftp import specs
from guaraci.services.downloads import DownloadService

FTP_NAMES = [s.name for s in specs.ALL_SPECS]


@pytest.fixture
def service() -> DownloadService:
    return DownloadService()


def test_all_eleven_ftp_sources_registered(service) -> None:
    descriptors = {d.source: d for d in service.list_sources()}
    for name in FTP_NAMES:
        assert name in descriptors, f"{name} not registered"
        assert descriptors[name].mode == "datasus ftp"
    assert len(FTP_NAMES) == 11


def test_grouped_state_spec_schema(service) -> None:
    params = {p["name"] for p in service.get_source_schema("sia")["params"]}
    assert {"start_year", "end_year", "groups", "states", "output_dir", "output_format"} <= params


def test_ungrouped_state_spec_schema(service) -> None:
    params = {p["name"] for p in service.get_source_schema("sinasc")["params"]}
    assert "states" in params
    assert "groups" not in params  # SINASC has a single implicit group


def test_national_spec_schema_has_neither_groups_nor_states(service) -> None:
    params = {p["name"] for p in service.get_source_schema("painel_oncologia")["params"]}
    assert "states" not in params
    assert "groups" not in params
    assert {"start_year", "end_year"} <= params


def test_groups_allowed_values_match_spec(service) -> None:
    schema = service.get_source_schema("cnes")
    groups_param = next(p for p in schema["params"] if p["name"] == "groups")
    assert set(groups_param["allowed_values"]) == set(specs.CNES.groups)


def test_run_dispatches_into_ftp_datasource(service, monkeypatch, tmp_path) -> None:
    captured: dict = {}

    def fake_download(spec, **kwargs):
        captured["spec"] = spec.name
        captured["kwargs"] = kwargs
        return {
            "successful_downloads": 0,
            "failed_downloads": [],
            "total_files": 0,
            "paths_by_group": {},
        }

    monkeypatch.setattr(ftp_source_mod.generic_backend, "download", fake_download)

    service.run("resp", output_dir=str(tmp_path), start_year=2016, end_year=2016)

    assert captured["spec"] == "resp"
    assert captured["kwargs"]["years"] == [2016]


def test_validate_rejects_unknown_param(service) -> None:
    with pytest.raises(Exception):
        service.validate_source_params(
            "sinasc", {"start_year": 2020, "end_year": 2020, "bogus": 1}
        )


def test_discover_dispatches_into_ftp_datasource(service, monkeypatch) -> None:
    captured: dict = {}

    def fake_discover_summary(spec, **kwargs):
        captured["spec"] = spec.name
        captured["kwargs"] = kwargs
        return {
            "source": spec.name,
            "documents_found": 3,
            "total_size_bytes": 0,
            "by_group": {"PA": 3},
            "by_state": {"SP": 3},
            "sample": [],
            "filters": {},
        }

    monkeypatch.setattr(
        ftp_source_mod.generic_backend, "discover_summary", fake_discover_summary
    )

    result = service.discover("sia", start_year=2024, end_year=2024, groups=["PA"], states=["SP"])

    assert captured["spec"] == "sia"
    assert captured["kwargs"]["fetch_sizes"] is False  # preflight stays cheap
    assert result["documents_found"] == 3
    assert result["filters"]["start_year"] == 2024


def test_discover_still_rejects_non_ftp_unsupported_source(service) -> None:
    with pytest.raises(ValueError, match="not supported"):
        service.discover("sinan", start_year=2020, end_year=2020)
