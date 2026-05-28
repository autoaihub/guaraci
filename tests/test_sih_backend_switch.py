"""Tests for the ``GUARACI_DATASUS_BACKEND`` switch on :class:`SihDataSource`.

These tests run with no real network and confirm the public dispatch
contract: by default the PySUS path is taken; when the env var is set to
``ftp`` the new direct-FTP backend is invoked instead.

Validation logic (year clamp, group whitelist, month range) is shared
across backends — covered once here, on the FTP path, since the legacy
path already has its own tests in ``test_sih_datasource.py``.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from guaraci.datasus import sih as sih_module
from guaraci.datasus.sih import SihDataSource


@pytest.fixture
def fake_ftp_backend(monkeypatch):
    """Replace ``guaraci.datasus.ftp.sih_backend`` with a recording fake."""
    calls: dict[str, Any] = {}

    def fake_download_sih(**kwargs):
        calls["download_kwargs"] = kwargs
        return {
            "successful_downloads": 2,
            "failed_downloads": [],
            "total_files": 2,
            "paths_by_group": {
                "RD": [str(Path(kwargs["cache_dir"]) / "RDSP2401.parquet")],
                "RJ": [str(Path(kwargs["cache_dir"]) / "RJSP2401.parquet")],
            },
        }

    def fake_discover_sih_summary(**kwargs):
        calls["discover_kwargs"] = kwargs
        return {
            "source": "sih",
            "documents_found": 1,
            "total_size_bytes": 12345,
            "by_group": {"RD": 1},
            "by_state": {"SP": 1},
            "sample": [
                {
                    "name": "RDSP2401.dbc",
                    "group": "RD",
                    "state": "SP",
                    "year": 2024,
                    "month": 1,
                    "size_bytes": 12345,
                }
            ],
            "filters": {
                "start_year": min(kwargs["years"]),
                "end_year": max(kwargs["years"]),
                "groups": list(kwargs.get("groups") or []),
                "states": list(kwargs.get("states") or []) or None,
                "months": list(kwargs.get("months") or []) or None,
            },
        }

    fake_module = types.SimpleNamespace(
        download_sih=fake_download_sih,
        discover_sih_summary=fake_discover_sih_summary,
    )
    monkeypatch.setitem(sys.modules, "guaraci.datasus.ftp.sih_backend", fake_module)

    # `from guaraci.datasus.ftp import sih_backend` resolves via the package's
    # attribute when it already exists from a prior real import in this
    # pytest session (e.g. `test_sih_backend_ftp.py` running before us).
    # Patch the attribute too so the lookup hits our fake.
    import guaraci.datasus.ftp as _ftp_pkg

    monkeypatch.setattr(_ftp_pkg, "sih_backend", fake_module, raising=False)
    return calls


def test_default_backend_is_pysus(monkeypatch) -> None:
    monkeypatch.delenv("GUARACI_DATASUS_BACKEND", raising=False)
    assert sih_module._get_datasus_backend() == "pysus"


def test_backend_ftp_selected_via_env_var(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    assert sih_module._get_datasus_backend() == "ftp"


def test_unknown_backend_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "nonsense")
    assert sih_module._get_datasus_backend() == "pysus"


def test_download_with_ftp_backend_delegates_to_ftp_orchestrator(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    ds = SihDataSource(output_path=str(tmp_path))
    result = ds.download(
        start_year=2024,
        end_year=2024,
        groups=["RD", "RJ"],
        states=["SP"],
        months=[1],
    )

    # Backend was called with normalized parameters.
    kw = fake_ftp_backend["download_kwargs"]
    assert kw["years"] == [2024]
    assert sorted(kw["groups"]) == ["RD", "RJ"]
    assert kw["states"] == ["SP"]
    assert kw["months"] == [1]
    assert Path(kw["cache_dir"]) == tmp_path

    # The dispatch unpacked paths_by_group into self.data for load_dataframe().
    assert result["total_files"] == 2
    assert result["successful_downloads"] == 2
    assert "paths_by_group" not in result
    assert ds.data["RD"] == [str(tmp_path / "RDSP2401.parquet")]
    assert ds.data["RJ"] == [str(tmp_path / "RJSP2401.parquet")]


def test_download_with_ftp_backend_validates_groups(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    ds = SihDataSource(output_path=str(tmp_path))
    with pytest.raises(ValueError, match="Unknown SIH group"):
        ds.download(start_year=2024, end_year=2024, groups=["ZZ"])


def test_download_with_ftp_backend_validates_months(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    ds = SihDataSource(output_path=str(tmp_path))
    with pytest.raises(ValueError, match="Invalid month"):
        ds.download(start_year=2024, end_year=2024, months=[13])


def test_download_with_ftp_backend_clamps_current_year(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    # Pretend "now" is well within the future to force the clamp.
    import datetime as _dt

    real_datetime = _dt.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return real_datetime(2030, 6, 1, tzinfo=tz)

    monkeypatch.setattr(sih_module.datetime, "datetime", FrozenDateTime)

    ds = SihDataSource(output_path=str(tmp_path))
    ds.download(start_year=2024, end_year=2030)

    kw = fake_ftp_backend["download_kwargs"]
    # 2030 must be clamped to 2029 (current_year - 1).
    assert kw["years"] == list(range(2024, 2030))


def test_discover_with_ftp_backend_delegates_and_anchors_filters(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    ds = SihDataSource(output_path=str(tmp_path))

    payload = ds.discover(
        start_year=2024,
        end_year=2024,
        groups=["RD"],
        states=["SP"],
        months=[1],
    )

    kw = fake_ftp_backend["discover_kwargs"]
    assert kw["years"] == [2024]
    assert kw["groups"] == ["RD"]
    assert kw["states"] == ["SP"]
    assert kw["months"] == [1]

    # The dispatch overrides `filters` with the request's own range.
    assert payload["filters"] == {
        "start_year": 2024,
        "end_year": 2024,
        "groups": ["RD"],
        "states": ["SP"],
        "months": [1],
    }


def test_ftp_cache_dir_honours_env_var(monkeypatch, tmp_path) -> None:
    explicit = tmp_path / "custom-cache"
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(explicit))
    ds = SihDataSource(output_path=str(tmp_path))
    assert ds._ftp_cache_dir() == explicit
    assert explicit.exists()


def test_ftp_cache_dir_defaults_to_output_subdir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GUARACI_FTP_CACHE_DIR", raising=False)
    ds = SihDataSource(output_path=str(tmp_path))
    assert ds._ftp_cache_dir() == tmp_path / ".cache_ftp"
