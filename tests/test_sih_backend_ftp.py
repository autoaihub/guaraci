"""Tests for `guaraci.datasus.ftp.sih_backend`.

The orchestrator wires :class:`DatasusFtpClient`,
:func:`discover_sih` and :func:`dbc.read` together. All three are
stubbed here so the tests run offline and stay fast.

Coverage:

- ``discover_sih_summary`` shapes the discovery payload that the API
  serializes back to the UI;
- ``download_sih`` walks discover → download → decode → write parquet,
  populating ``paths_by_group``;
- ``download_sih`` is idempotent (skips files that already have a
  ``.parquet`` sibling);
- ``download_sih`` records per-file failures without aborting the run.
"""

from __future__ import annotations

import sys
import types
from collections import defaultdict
from pathlib import Path
from typing import Any, List

import polars as pl
import pytest

from guaraci.datasus.ftp import sih_backend
from guaraci.datasus.ftp.catalog import FileRecord, System
from guaraci.datasus.ftp.discovery import SIH_CURRENT_PATH, SIH_LEGACY_PATH


# --- shared fakes ------------------------------------------------------------


class FakeClient:
    """A minimal stand-in for :class:`DatasusFtpClient`.

    Records (path, dest) tuples for every ``download`` call, plus the
    payload returned by ``size`` and ``list_dir``.
    """

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
        # Reuse the dataclass surface of FtpEntry without importing it: a
        # SimpleNamespace with `.name` is enough for discover_sih.
        return [types.SimpleNamespace(name=name) for name in self.listings.get(path, [])]

    async def size(self, path: str) -> int:
        return int(self.sizes.get(path, 0))

    async def download(self, path: str, dest: Path, *, progress=None) -> Path:
        self.downloads.append((path, Path(dest)))
        if path in self.download_fails:
            raise OSError(f"forced failure for {path}")
        Path(dest).write_bytes(b"\x00")  # the FTP layer would write real bytes here
        if progress is not None:
            progress(1, 1)
        return Path(dest)


def make_fake_dbc_reader(record_count: int = 3):
    """Return a stub of ``dbc.read`` that produces a 1-column DataFrame."""

    def _read(_path: Path) -> pl.DataFrame:
        return pl.DataFrame({"UF_ZI": ["35"] * record_count})

    return _read


# --- discover_sih_summary ----------------------------------------------------


def test_discover_sih_summary_shapes_payload_like_legacy_discover() -> None:
    listings = {
        SIH_CURRENT_PATH: ["RDSP2401.dbc", "RDRJ2401.dbc"],
    }
    sizes = {
        f"{SIH_CURRENT_PATH}/RDSP2401.dbc": 10_000,
        f"{SIH_CURRENT_PATH}/RDRJ2401.dbc": 20_000,
    }
    client = FakeClient(listings, sizes)

    payload = sih_backend.discover_sih_summary(
        years=[2024],
        groups=["RD"],
        client_factory=lambda: client,
    )

    assert payload["source"] == "sih"
    assert payload["documents_found"] == 2
    assert payload["total_size_bytes"] == 30_000
    assert payload["by_group"] == {"RD": 2}
    assert payload["by_state"] == {"RJ": 1, "SP": 1}
    assert {entry["name"] for entry in payload["sample"]} == {
        "RDSP2401.dbc",
        "RDRJ2401.dbc",
    }
    assert payload["filters"] == {
        "start_year": 2024,
        "end_year": 2024,
        "groups": ["RD"],
        "states": None,
        "months": None,
    }
    assert client.entered and client.exited  # async-with respected


def test_discover_sih_summary_returns_empty_when_nothing_matches() -> None:
    client = FakeClient({SIH_CURRENT_PATH: ["RDSP2301.dbc"]})
    payload = sih_backend.discover_sih_summary(
        years=[2024],
        groups=["RD"],
        client_factory=lambda: client,
    )
    assert payload["documents_found"] == 0
    assert payload["total_size_bytes"] == 0
    assert payload["sample"] == []


# --- download_sih ------------------------------------------------------------


def test_download_sih_walks_discover_download_decode_write(tmp_path) -> None:
    listings = {SIH_CURRENT_PATH: ["RDSP2401.dbc"]}
    client = FakeClient(listings)

    result = sih_backend.download_sih(
        years=[2024],
        groups=["RD"],
        states=["SP"],
        months=[1],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(record_count=5),
    )

    assert result["total_files"] == 1
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == []
    assert result["paths_by_group"] == {
        "RD": [str(tmp_path / "RDSP2401.parquet")],
    }
    # The .dbc is downloaded then removed; the .parquet remains.
    assert not (tmp_path / "RDSP2401.dbc").exists()
    parquet_path = tmp_path / "RDSP2401.parquet"
    assert parquet_path.exists()
    df = pl.read_parquet(parquet_path)
    assert df.height == 5


def test_download_sih_is_idempotent_when_parquet_already_exists(tmp_path) -> None:
    listings = {SIH_CURRENT_PATH: ["RDSP2401.dbc"]}
    client = FakeClient(listings)

    # Pre-create the .parquet so the second call should skip the download.
    parquet_path = tmp_path / "RDSP2401.parquet"
    pl.DataFrame({"UF_ZI": ["35"]}).write_parquet(parquet_path)

    result = sih_backend.download_sih(
        years=[2024],
        groups=["RD"],
        states=["SP"],
        months=[1],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert result["successful_downloads"] == 1
    assert client.downloads == []  # nothing was downloaded


def test_download_sih_records_failure_per_file(tmp_path) -> None:
    listings = {SIH_CURRENT_PATH: ["RDSP2401.dbc", "RDRJ2401.dbc"]}
    fail_path = f"{SIH_CURRENT_PATH}/RDSP2401.dbc"
    client = FakeClient(listings, download_fails={fail_path})

    result = sih_backend.download_sih(
        years=[2024],
        groups=["RD"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert result["total_files"] == 2
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == [("RD", "RDSP2401.dbc")]
    assert result["paths_by_group"] == {
        "RD": [str(tmp_path / "RDRJ2401.parquet")],
    }
    # Failed download's stray .dbc must be cleaned up.
    assert not (tmp_path / "RDSP2401.dbc").exists()


def test_download_sih_progress_callback_is_invoked(tmp_path) -> None:
    listings = {SIH_CURRENT_PATH: ["RDSP2401.dbc", "RDRJ2401.dbc"]}
    client = FakeClient(listings)
    calls: list[tuple[int, int]] = []

    sih_backend.download_sih(
        years=[2024],
        groups=["RD"],
        cache_dir=tmp_path,
        progress_callback=lambda done, total: calls.append((done, total)),
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    # First call announces total; subsequent calls report progress.
    assert calls[0] == (0, 2)
    assert calls[-1] == (2, 2)
