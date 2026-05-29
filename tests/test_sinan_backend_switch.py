"""Tests for the ``GUARACI_DATASUS_BACKEND`` switch on :class:`SinanDataSource`.

These run with no real network and confirm the public dispatch contract:
when the env var is ``ftp`` the direct-FTP backend is invoked, parameters
are normalized (diseases default to the neglected-disease list), and
``paths_by_group`` is unpacked into ``self.data`` keyed by disease. The
selector contract (default / unknown) is pinned in
``test_datasus_backend.py``; here we only assert the module wires it in.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from guaraci.datasus import sinan as sinan_module
from guaraci.datasus.sinan import SinanDataSource


@pytest.fixture
def fake_ftp_backend(monkeypatch):
    """Replace ``guaraci.datasus.ftp.sinan_backend`` with a recording fake."""
    calls: dict[str, Any] = {}

    def fake_download_sinan(**kwargs):
        calls["download_kwargs"] = kwargs
        cache = Path(kwargs["cache_dir"])
        return {
            "successful_downloads": 2,
            "failed_downloads": [],
            "total_files": 2,
            "paths_by_group": {
                "DENG": [str(cache / "DENGBR23.parquet")],
                "CHIK": [str(cache / "CHIKBR23.parquet")],
            },
        }

    fake_module = types.SimpleNamespace(download_sinan=fake_download_sinan)
    monkeypatch.setitem(sys.modules, "guaraci.datasus.ftp.sinan_backend", fake_module)

    # `from guaraci.datasus.ftp import sinan_backend` resolves via the package
    # attribute when the submodule was already imported earlier in the
    # session (e.g. by test_sinan_backend_ftp.py). Patch the attribute too.
    import guaraci.datasus.ftp as _ftp_pkg

    monkeypatch.setattr(_ftp_pkg, "sinan_backend", fake_module, raising=False)
    return calls


def test_backend_ftp_selected_via_env_var(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    assert sinan_module._get_datasus_backend() == "ftp"


def test_download_with_ftp_backend_delegates_to_ftp_orchestrator(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    ds = SinanDataSource(output_path=str(tmp_path))
    result = ds.download(
        start_year=2023,
        end_year=2023,
        diseases=["DENG", "CHIK"],
    )

    kw = fake_ftp_backend["download_kwargs"]
    assert kw["years"] == [2023]
    assert kw["diseases"] == ["DENG", "CHIK"]
    assert Path(kw["cache_dir"]) == tmp_path

    assert result["total_files"] == 2
    assert result["successful_downloads"] == 2
    assert "paths_by_group" not in result
    assert ds.data["DENG"] == [str(tmp_path / "DENGBR23.parquet")]
    assert ds.data["CHIK"] == [str(tmp_path / "CHIKBR23.parquet")]


def test_download_with_ftp_backend_defaults_to_neglected_diseases(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    ds = SinanDataSource(output_path=str(tmp_path))
    ds.download(start_year=2023, end_year=2023)

    kw = fake_ftp_backend["download_kwargs"]
    assert kw["diseases"] == SinanDataSource.NEGLECTED_DISEASES


def test_download_with_ftp_backend_clamps_current_year(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    import datetime as _dt

    real_datetime = _dt.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return real_datetime(2030, 6, 1, tzinfo=tz)

    monkeypatch.setattr(sinan_module.datetime, "datetime", FrozenDateTime)

    ds = SinanDataSource(output_path=str(tmp_path))
    ds.download(start_year=2024, end_year=2030, diseases=["DENG"])

    # 2030 must be clamped to 2029 (current_year - 1).
    assert fake_ftp_backend["download_kwargs"]["years"] == list(range(2024, 2030))


def test_ftp_cache_dir_honours_env_var(monkeypatch, tmp_path) -> None:
    explicit = tmp_path / "custom-cache"
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(explicit))
    ds = SinanDataSource(output_path=str(tmp_path))
    assert ds._ftp_cache_dir() == explicit
    assert explicit.exists()


def test_ftp_cache_dir_defaults_to_output_subdir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GUARACI_FTP_CACHE_DIR", raising=False)
    ds = SinanDataSource(output_path=str(tmp_path))
    assert ds._ftp_cache_dir() == tmp_path / ".cache_ftp"
