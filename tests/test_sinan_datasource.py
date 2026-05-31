"""Datasource-level tests for the SINAN legacy (PySUS) download path.

Phase 5 autonomous cleanup: the previous two tests here exercised
internals removed when SINAN moved to backend dispatch
(``ThreadPoolExecutor`` single-worker, ``_download_file_safe``,
``_sinan_instance``) and had been failing on every run. They are replaced
with coverage of the *current* legacy path — `SinanDataSource` with
``GUARACI_DATASUS_BACKEND=pysus`` — mirroring ``test_sih_datasource.py``.
The default (direct-FTP) path is covered in ``test_sinan_backend_ftp.py``
and ``test_sinan_backend_switch.py``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from guaraci.datasus import sinan as sinan_mod
from guaraci.datasus.sinan import SinanDataSource


@pytest.fixture(autouse=True)
def _force_pysus_backend(monkeypatch):
    """Pin the legacy PySUS backend for this module (default is ftp)."""
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "pysus")


class _FakeFile:
    def __init__(self, basename: str, group: str = "RAIV") -> None:
        self.basename = basename
        self.group = SimpleNamespace(name=group)

    def __str__(self) -> str:
        return self.basename


class _FakePySUS:
    downloaded: list[str] = []

    async def __aenter__(self) -> "_FakePySUS":
        type(self).downloaded = []
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def query(self, *, dataset: str, group: str, year: int):  # noqa: ANN001
        assert dataset == "sinan"
        return [_FakeFile(f"{group}BR{str(year)[2:]}.dbc", group)]

    async def download(self, file_record):  # noqa: ANN001
        type(self).downloaded.append(file_record.basename)
        return SimpleNamespace(
            path=Path("/cache") / file_record.basename.replace(".dbc", ".parquet")
        )


def test_sinan_legacy_pysus_path_downloads(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sinan_mod, "PYSUS_AVAILABLE", True)
    monkeypatch.setattr(sinan_mod, "PySUS", _FakePySUS)

    ds = SinanDataSource(output_path=str(tmp_path))
    result = ds.download(start_year=2023, end_year=2023, diseases=["RAIV"])

    assert result["total_files"] == 1
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == []
    assert _FakePySUS.downloaded == ["RAIVBR23.dbc"]
    assert [Path(item).name for item in ds.data["RAIV"]] == ["RAIVBR23.parquet"]


def test_sinan_pysus_path_requires_pysus(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sinan_mod, "PYSUS_AVAILABLE", False)
    ds = SinanDataSource(output_path=str(tmp_path))
    with pytest.raises(ImportError, match="PySUS is required"):
        ds.download(start_year=2023, end_year=2023, diseases=["RAIV"])
