"""Tests for the ``GUARACI_DATASUS_BACKEND`` switch on :class:`SimDataSource`.

These run with no real network and confirm the public dispatch contract:
when the env var is ``ftp`` the direct-FTP backend is invoked, parameters
are normalized, and ``paths_by_group`` is unpacked into ``self.data`` for
``load_dataframe``. The selector contract (default / unknown) is pinned in
``test_datasus_backend.py``; here we only assert each module wires it in.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from guaraci.datasus import sim as sim_module
from guaraci.datasus.sim import SimDataSource


@pytest.fixture
def fake_ftp_backend(monkeypatch):
    """Replace ``guaraci.datasus.ftp.sim_backend`` with a recording fake."""
    calls: dict[str, Any] = {}

    def fake_download_sim(**kwargs):
        calls["download_kwargs"] = kwargs
        cache = Path(kwargs["cache_dir"])
        return {
            "successful_downloads": 2,
            "failed_downloads": [],
            "total_files": 2,
            "paths_by_group": {
                "CID10": [
                    str(cache / "DOSP2024.parquet"),
                    str(cache / "DORJ2024.parquet"),
                ],
            },
        }

    fake_module = types.SimpleNamespace(download_sim=fake_download_sim)
    monkeypatch.setitem(sys.modules, "guaraci.datasus.ftp.sim_backend", fake_module)

    # `from guaraci.datasus.ftp import sim_backend` resolves via the package
    # attribute when the submodule was already imported earlier in the
    # session (e.g. by test_sim_backend_ftp.py). Patch the attribute too.
    import guaraci.datasus.ftp as _ftp_pkg

    monkeypatch.setattr(_ftp_pkg, "sim_backend", fake_module, raising=False)
    return calls


def test_backend_ftp_selected_via_env_var(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    assert sim_module._get_datasus_backend() == "ftp"


def test_download_with_ftp_backend_delegates_to_ftp_orchestrator(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    ds = SimDataSource(output_path=str(tmp_path))
    result = ds.download(
        start_year=2024,
        end_year=2024,
        groups=["CID10"],
        states=["SP"],
    )

    kw = fake_ftp_backend["download_kwargs"]
    assert kw["years"] == [2024]
    assert kw["groups"] == ["CID10"]
    assert kw["states"] == ["SP"]
    assert Path(kw["cache_dir"]) == tmp_path

    assert result["total_files"] == 2
    assert result["successful_downloads"] == 2
    assert "paths_by_group" not in result
    assert ds.data["CID10"] == [
        str(tmp_path / "DOSP2024.parquet"),
        str(tmp_path / "DORJ2024.parquet"),
    ]


def test_download_with_ftp_backend_defaults_groups_to_cid10(
    monkeypatch, tmp_path, fake_ftp_backend
) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(tmp_path))

    ds = SimDataSource(output_path=str(tmp_path))
    ds.download(start_year=2024, end_year=2024)

    assert fake_ftp_backend["download_kwargs"]["groups"] == ["CID10"]


def test_download_with_ftp_backend_validates_groups(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    ds = SimDataSource(output_path=str(tmp_path))
    with pytest.raises(ValueError, match="Unknown SIM group"):
        ds.download(start_year=2024, end_year=2024, groups=["ZZ"])


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

    monkeypatch.setattr(sim_module.datetime, "datetime", FrozenDateTime)

    ds = SimDataSource(output_path=str(tmp_path))
    ds.download(start_year=2024, end_year=2030)

    # 2030 must be clamped to 2029 (current_year - 1).
    assert fake_ftp_backend["download_kwargs"]["years"] == list(range(2024, 2030))


def test_ftp_cache_dir_honours_env_var(monkeypatch, tmp_path) -> None:
    explicit = tmp_path / "custom-cache"
    monkeypatch.setenv("GUARACI_FTP_CACHE_DIR", str(explicit))
    ds = SimDataSource(output_path=str(tmp_path))
    assert ds._ftp_cache_dir() == explicit
    assert explicit.exists()


def test_ftp_cache_dir_defaults_to_output_subdir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GUARACI_FTP_CACHE_DIR", raising=False)
    ds = SimDataSource(output_path=str(tmp_path))
    assert ds._ftp_cache_dir() == tmp_path / ".cache_ftp"
