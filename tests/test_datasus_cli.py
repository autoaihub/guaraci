"""Tests for the generic `guaraci datasus` CLI (phase 5)."""

from __future__ import annotations

from click.testing import CliRunner

from guaraci.cli.datasus_cli import datasus


def test_list_shows_all_systems() -> None:
    result = CliRunner().invoke(datasus, ["list"])
    assert result.exit_code == 0
    for name in ("sinasc", "sia", "cnes", "pni", "painel_oncologia"):
        assert name in result.output


def test_download_dispatches_via_service(monkeypatch) -> None:
    captured: dict = {}

    class FakeService:
        def run(self, source, **kwargs):
            captured["source"] = source
            captured["kwargs"] = kwargs
            return {"successful_downloads": 0, "total_files": 0}

    monkeypatch.setattr("guaraci.services.downloads.DownloadService", FakeService)

    result = CliRunner().invoke(
        datasus,
        ["download", "sia", "2024", "2024", "-g", "PA", "-s", "SP", "--format", "csv"],
    )
    assert result.exit_code == 0, result.output
    assert captured["source"] == "sia"
    assert captured["kwargs"]["start_year"] == 2024
    assert captured["kwargs"]["groups"] == ["PA"]
    assert captured["kwargs"]["states"] == ["SP"]
    assert captured["kwargs"]["output_format"] == "csv"


def test_download_omits_unprovided_optional_params(monkeypatch) -> None:
    captured: dict = {}

    class FakeService:
        def run(self, source, **kwargs):
            captured["kwargs"] = kwargs
            return {"successful_downloads": 0}

    monkeypatch.setattr("guaraci.services.downloads.DownloadService", FakeService)

    CliRunner().invoke(datasus, ["download", "sinasc", "2018", "2020"])
    # No --groups/--states/--format -> those keys must be absent (sinasc has no groups).
    assert "groups" not in captured["kwargs"]
    assert "states" not in captured["kwargs"]
    assert "output_format" not in captured["kwargs"]


def test_download_rejects_unknown_source() -> None:
    result = CliRunner().invoke(datasus, ["download", "nope", "2020", "2020"])
    assert result.exit_code != 0
    assert "Unknown source" in result.output
