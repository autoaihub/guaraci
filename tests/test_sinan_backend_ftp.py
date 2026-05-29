"""Tests for `guaraci.datasus.ftp.sinan_backend`.

Mirrors ``test_sih_backend_ftp.py``. The orchestrator wires
:class:`DatasusFtpClient`, :func:`discover_sinan` and :func:`dbc.read`
together; all three are stubbed here so the tests run offline.

SINAN differs from SIH/SIM: its unit of selection is the *disease* code
(the catalog ``group``), the national files have **no state** and **no
month**, and discovery scans both the FINAIS and PRELIM directories.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import polars as pl

from guaraci.datasus.ftp import sinan_backend
from guaraci.datasus.ftp.discovery import SINAN_FINAIS_PATH, SINAN_PRELIM_PATH


# --- shared fakes ------------------------------------------------------------


class FakeClient:
    """A minimal stand-in for :class:`DatasusFtpClient`."""

    def __init__(
        self,
        listings: dict[str, list[str]] | None = None,
        sizes: dict[str, int] | None = None,
        *,
        download_fails: set[str] | None = None,
    ) -> None:
        self.listings = listings or {}
        self.sizes = sizes or {}
        self.download_fails = download_fails or set()
        self.downloads: list[tuple[str, Path]] = []
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.exited = True

    async def list_dir(self, path: str):
        return [types.SimpleNamespace(name=name) for name in self.listings.get(path, [])]

    async def size(self, path: str) -> int:
        return int(self.sizes.get(path, 0))

    async def download(self, path: str, dest: Path, *, progress=None) -> Path:
        self.downloads.append((path, Path(dest)))
        if path in self.download_fails:
            raise OSError(f"forced failure for {path}")
        Path(dest).write_bytes(b"\x00")
        if progress is not None:
            progress(1, 1)
        return Path(dest)


def make_fake_dbc_reader(record_count: int = 3):
    """Return a stub of ``dbc.read`` that produces a 1-column DataFrame."""

    def _read(_path: Path) -> pl.DataFrame:
        return pl.DataFrame({"SG_UF_NOT": ["35"] * record_count})

    return _read


# --- discover_sinan_summary --------------------------------------------------


def test_discover_sinan_summary_shapes_payload() -> None:
    listings = {SINAN_FINAIS_PATH: ["DENGBR23.dbc", "CHIKBR23.dbc"]}
    sizes = {
        f"{SINAN_FINAIS_PATH}/DENGBR23.dbc": 40_000,
        f"{SINAN_FINAIS_PATH}/CHIKBR23.dbc": 10_000,
    }
    client = FakeClient(listings, sizes)

    payload = sinan_backend.discover_sinan_summary(
        years=[2023],
        diseases=["DENG", "CHIK"],
        client_factory=lambda: client,
    )

    assert payload["source"] == "sinan"
    assert payload["documents_found"] == 2
    assert payload["total_size_bytes"] == 50_000
    assert payload["by_group"] == {"CHIK": 1, "DENG": 1}
    # SINAN national files carry no state.
    assert payload["by_state"] == {}
    assert {entry["name"] for entry in payload["sample"]} == {
        "DENGBR23.dbc",
        "CHIKBR23.dbc",
    }
    assert payload["filters"] == {
        "start_year": 2023,
        "end_year": 2023,
        "diseases": ["DENG", "CHIK"],
    }
    assert client.entered and client.exited


def test_discover_sinan_summary_returns_empty_when_nothing_matches() -> None:
    client = FakeClient({SINAN_FINAIS_PATH: ["DENGBR22.dbc"]})
    payload = sinan_backend.discover_sinan_summary(
        years=[2023],
        diseases=["DENG"],
        client_factory=lambda: client,
    )
    assert payload["documents_found"] == 0
    assert payload["total_size_bytes"] == 0
    assert payload["sample"] == []


# --- download_sinan ----------------------------------------------------------


def test_download_sinan_walks_discover_download_decode_write(tmp_path) -> None:
    listings = {SINAN_FINAIS_PATH: ["DENGBR23.dbc"]}
    client = FakeClient(listings)

    result = sinan_backend.download_sinan(
        years=[2023],
        diseases=["DENG"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(record_count=5),
    )

    assert result["total_files"] == 1
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == []
    assert result["paths_by_group"] == {
        "DENG": [str(tmp_path / "DENGBR23.parquet")],
    }
    assert not (tmp_path / "DENGBR23.dbc").exists()
    parquet_path = tmp_path / "DENGBR23.parquet"
    assert parquet_path.exists()
    assert pl.read_parquet(parquet_path).height == 5


def test_download_sinan_is_idempotent_when_parquet_already_exists(tmp_path) -> None:
    listings = {SINAN_FINAIS_PATH: ["DENGBR23.dbc"]}
    client = FakeClient(listings)

    parquet_path = tmp_path / "DENGBR23.parquet"
    pl.DataFrame({"SG_UF_NOT": ["35"]}).write_parquet(parquet_path)

    result = sinan_backend.download_sinan(
        years=[2023],
        diseases=["DENG"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert result["successful_downloads"] == 1
    assert client.downloads == []


def test_download_sinan_records_failure_per_file(tmp_path) -> None:
    listings = {SINAN_FINAIS_PATH: ["DENGBR23.dbc", "CHIKBR23.dbc"]}
    fail_path = f"{SINAN_FINAIS_PATH}/DENGBR23.dbc"
    client = FakeClient(listings, download_fails={fail_path})

    result = sinan_backend.download_sinan(
        years=[2023],
        diseases=["DENG", "CHIK"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert result["total_files"] == 2
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == [("DENG", "DENGBR23.dbc")]
    assert result["paths_by_group"] == {
        "CHIK": [str(tmp_path / "CHIKBR23.parquet")],
    }
    assert not (tmp_path / "DENGBR23.dbc").exists()


def test_download_sinan_progress_callback_is_invoked(tmp_path) -> None:
    listings = {SINAN_FINAIS_PATH: ["DENGBR23.dbc", "CHIKBR23.dbc"]}
    client = FakeClient(listings)
    calls: list[tuple[int, int]] = []

    sinan_backend.download_sinan(
        years=[2023],
        diseases=["DENG", "CHIK"],
        cache_dir=tmp_path,
        progress_callback=lambda done, total: calls.append((done, total)),
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert calls[0] == (0, 2)
    assert calls[-1] == (2, 2)
