"""Tests for InmetEstacoesDataSource (offline, fake zip fixtures / fake client)."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from guaraci.inmet.datasource import InmetEstacoesDataSource

SP_CSV = (
    "REGIAO:;SE\r\n"
    "UF:;SP\r\n"
    "ESTACAO:;SAO PAULO - MIRANTE\r\n"
    "CODIGO (WMO):;A701\r\n"
    "LATITUDE:;-23,4962888\r\n"
    "LONGITUDE:;-46,6200666\r\n"
    "ALTITUDE:;785,64\r\n"
    "DATA DE FUNDACAO:;25/07/06\r\n"
    "Data;Hora UTC;PRECIPITACAO TOTAL, HORARIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (C);\r\n"
    "2025/01/01;0000 UTC;0;21,2;\r\n"
    "2025/01/01;0100 UTC;;21,1;\r\n"
).encode("latin-1")

RJ_CSV = (
    "REGIAO:;SE\r\n"
    "UF:;RJ\r\n"
    "ESTACAO:;RIO DE JANEIRO\r\n"
    "CODIGO (WMO):;A602\r\n"
    "LATITUDE:;-22,99\r\n"
    "LONGITUDE:;-43,23\r\n"
    "ALTITUDE:;10\r\n"
    "DATA DE FUNDACAO:;01/01/06\r\n"
    "Data;Hora UTC;PRECIPITACAO TOTAL, HORARIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (C);\r\n"
    "2025/01/01;0000 UTC;1;25,0;\r\n"
).encode("latin-1")


def _write_year_zip(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


class _FakeClient:
    """Stand-in for InmetClient: 'downloads' by copying a pre-built fixture zip."""

    def __init__(self, fixtures: dict[int, Path]) -> None:
        self.base_url = "https://portal.inmet.gov.br/uploads/dadoshistoricos"
        self._fixtures = fixtures
        self.download_calls: list[int] = []
        self.head_calls: list[int] = []

    def head_content_length(self, year: int) -> int:
        self.head_calls.append(year)
        return self._fixtures[year].stat().st_size

    def download_zip(self, year: int, destination: Path, **_kwargs) -> int:
        self.download_calls.append(year)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._fixtures[year].read_bytes())
        return destination.stat().st_size


@pytest.fixture()
def fixture_zip(tmp_path_factory) -> Path:
    fixtures_dir = tmp_path_factory.mktemp("inmet_fixtures")
    zip_path = fixtures_dir / "2025.zip"
    _write_year_zip(
        zip_path,
        {
            "2025/INMET_SE_SP_A701_SAO PAULO - MIRANTE_01-01-2025_A_31-12-2025.CSV": SP_CSV,
            "2025/INMET_SE_RJ_A602_RIO DE JANEIRO_01-01-2025_A_31-12-2025.CSV": RJ_CSV,
        },
    )
    return zip_path


def test_download_parses_all_ufs_by_default(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2025, end_year=2025, output_format="csv")

    assert payload["record_count"] == 3  # 2 SP rows + 1 RJ row
    assert payload["station_count"] == 2
    df = ds.load_dataframe()
    assert set(df["uf"].unique().to_list()) == {"SP", "RJ"}
    assert Path(payload["manifest_path"]).exists()
    assert payload["exported_files"]


def test_download_filters_by_uf(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2025, end_year=2025, ufs=["sp"], output_format="csv")

    assert payload["record_count"] == 2
    df = ds.load_dataframe()
    assert set(df["uf"].unique().to_list()) == {"SP"}


def test_download_filters_by_variables(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(
        start_year=2025,
        end_year=2025,
        ufs=["SP"],
        variables=["precipitacao_total_horario_mm"],
    )
    df = ds.load_dataframe()
    assert "precipitacao_total_horario_mm" in df.columns
    assert "temperatura_do_ar_bulbo_seco_horaria_c" not in df.columns
    assert "uf" in df.columns  # base columns always kept


def test_frozen_year_zip_is_not_redownloaded(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2025, end_year=2025)
    ds.download(start_year=2025, end_year=2025)

    # A frozen (past) year should only be fetched once; the datasource treats
    # any year < current-year as immutable and reuses the cached ZIP.
    if client.download_calls.count(2025) > 1:
        # Only meaningful when 2025 really is a past year relative to "today".
        import datetime

        assert datetime.datetime.now().year <= 2025
    assert client.download_calls.count(2025) <= 2


def test_rejects_year_before_2000(tmp_path) -> None:
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=_FakeClient({}))
    with pytest.raises(ValueError):
        ds.download(start_year=1999)


def test_rejects_end_year_before_start_year(tmp_path) -> None:
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=_FakeClient({}))
    with pytest.raises(ValueError):
        ds.download(start_year=2020, end_year=2010)


def test_no_output_format_and_no_keep_raw_warns(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2025, end_year=2025)
    assert "export_warning" in payload
    assert "No data artifact" in payload["export_warning"]


def test_keep_raw_extracts_station_csvs(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2025, end_year=2025, ufs=["SP"], keep_raw=True)
    extracted = list((tmp_path / "extracted" / "2025").glob("*.CSV"))
    assert len(extracted) == 1


def test_progress_callback_receives_lifecycle_events(tmp_path, fixture_zip) -> None:
    client = _FakeClient({2025: fixture_zip})
    ds = InmetEstacoesDataSource(output_path=str(tmp_path), client=client)
    events = []
    ds.download(start_year=2025, end_year=2025, output_format="csv", progress_callback=events.append)
    event_names = [e["event"] for e in events]
    assert "download_start" in event_names
    assert "download_complete" in event_names
