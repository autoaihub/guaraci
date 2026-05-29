"""Tests for `guaraci.datasus.ftp.sim_backend`.

Mirrors ``test_sih_backend_ftp.py``. The orchestrator wires
:class:`DatasusFtpClient`, :func:`discover_sim` and :func:`dbc.read`
together; all three are stubbed here so the tests run offline.

SIM differs from SIH in two ways exercised below: it has a *state*
dimension but **no month**, and it splits its archive by classification
directory (CID-10 vs CID-9).
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import polars as pl

from guaraci.datasus.ftp import sim_backend
from guaraci.datasus.ftp.discovery import SIM_CID9_PATH, SIM_CID10_PATH


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
        return pl.DataFrame({"CODMUNRES": ["355030"] * record_count})

    return _read


# --- discover_sim_summary ----------------------------------------------------


def test_discover_sim_summary_shapes_payload() -> None:
    listings = {SIM_CID10_PATH: ["DOSP2024.dbc", "DORJ2024.dbc"]}
    sizes = {
        f"{SIM_CID10_PATH}/DOSP2024.dbc": 10_000,
        f"{SIM_CID10_PATH}/DORJ2024.dbc": 20_000,
    }
    client = FakeClient(listings, sizes)

    payload = sim_backend.discover_sim_summary(
        years=[2024],
        groups=["CID10"],
        client_factory=lambda: client,
    )

    assert payload["source"] == "sim"
    assert payload["documents_found"] == 2
    assert payload["total_size_bytes"] == 30_000
    assert payload["by_group"] == {"CID10": 2}
    assert payload["by_state"] == {"RJ": 1, "SP": 1}
    assert {entry["name"] for entry in payload["sample"]} == {
        "DOSP2024.dbc",
        "DORJ2024.dbc",
    }
    assert payload["filters"] == {
        "start_year": 2024,
        "end_year": 2024,
        "groups": ["CID10"],
        "states": None,
    }
    assert client.entered and client.exited


def test_discover_sim_summary_returns_empty_when_nothing_matches() -> None:
    client = FakeClient({SIM_CID10_PATH: ["DOSP2023.dbc"]})
    payload = sim_backend.discover_sim_summary(
        years=[2024],
        groups=["CID10"],
        client_factory=lambda: client,
    )
    assert payload["documents_found"] == 0
    assert payload["total_size_bytes"] == 0
    assert payload["sample"] == []


# --- download_sim ------------------------------------------------------------


def test_download_sim_walks_discover_download_decode_write(tmp_path) -> None:
    listings = {SIM_CID10_PATH: ["DOSP2024.dbc"]}
    client = FakeClient(listings)

    result = sim_backend.download_sim(
        years=[2024],
        groups=["CID10"],
        states=["SP"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(record_count=5),
    )

    assert result["total_files"] == 1
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == []
    assert result["paths_by_group"] == {
        "CID10": [str(tmp_path / "DOSP2024.parquet")],
    }
    assert not (tmp_path / "DOSP2024.dbc").exists()
    parquet_path = tmp_path / "DOSP2024.parquet"
    assert parquet_path.exists()
    assert pl.read_parquet(parquet_path).height == 5


def test_download_sim_is_idempotent_when_parquet_already_exists(tmp_path) -> None:
    listings = {SIM_CID10_PATH: ["DOSP2024.dbc"]}
    client = FakeClient(listings)

    parquet_path = tmp_path / "DOSP2024.parquet"
    pl.DataFrame({"CODMUNRES": ["355030"]}).write_parquet(parquet_path)

    result = sim_backend.download_sim(
        years=[2024],
        groups=["CID10"],
        states=["SP"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert result["successful_downloads"] == 1
    assert client.downloads == []


def test_download_sim_records_failure_per_file(tmp_path) -> None:
    listings = {SIM_CID10_PATH: ["DOSP2024.dbc", "DORJ2024.dbc"]}
    fail_path = f"{SIM_CID10_PATH}/DOSP2024.dbc"
    client = FakeClient(listings, download_fails={fail_path})

    result = sim_backend.download_sim(
        years=[2024],
        groups=["CID10"],
        cache_dir=tmp_path,
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert result["total_files"] == 2
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == [("CID10", "DOSP2024.dbc")]
    assert result["paths_by_group"] == {
        "CID10": [str(tmp_path / "DORJ2024.parquet")],
    }
    assert not (tmp_path / "DOSP2024.dbc").exists()


def test_download_sim_progress_callback_is_invoked(tmp_path) -> None:
    listings = {SIM_CID10_PATH: ["DOSP2024.dbc", "DORJ2024.dbc"]}
    client = FakeClient(listings)
    calls: list[tuple[int, int]] = []

    sim_backend.download_sim(
        years=[2024],
        groups=["CID10"],
        cache_dir=tmp_path,
        progress_callback=lambda done, total: calls.append((done, total)),
        client_factory=lambda: client,
        dbc_reader=make_fake_dbc_reader(),
    )

    assert calls[0] == (0, 2)
    assert calls[-1] == (2, 2)
