"""Tests for the spec-driven `generic_backend` (phase 5).

Offline: a fake FTP client serves directory listings and writes stub
files on download; the DBC reader is faked to return a small DataFrame.
Covers the download walk (group keying, idempotency) and the discovery
summary payload for both state and national specs.
"""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.datasus.ftp import FtpEntry, generic_backend, specs


class FakeClient:
    """Async-context FTP stand-in backed by an in-memory directory map."""

    def __init__(self, listings: dict[str, list[str]]) -> None:
        self.listings = listings
        self.downloads: list[str] = []

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def list_dir(self, path: str) -> list[FtpEntry]:
        return [FtpEntry(name=name) for name in self.listings.get(path, [])]

    async def size(self, path: str) -> int:
        return 1234

    async def download(self, path: str, dest) -> None:
        self.downloads.append(path)
        dest.write_bytes(b"\x00")


def _fake_reader(_path) -> pl.DataFrame:
    return pl.DataFrame({"COD": ["355030", "330455"]})


def _factory(listings):
    return lambda: FakeClient(listings)


def test_download_keys_paths_by_group(tmp_path) -> None:
    root = specs.SISPRENATAL.roots[0]
    listings = {root: ["PNSP1202.dbc", "PNRJ1202.dbc"]}

    result = generic_backend.download(
        specs.SISPRENATAL,
        years=[2012],
        cache_dir=tmp_path,
        client_factory=_factory(listings),
        dbc_reader=_fake_reader,
    )

    assert result["successful_downloads"] == 2
    assert result["failed_downloads"] == []
    assert sorted(result["paths_by_group"]) == ["PN"]
    assert len(result["paths_by_group"]["PN"]) == 2
    assert all(p.endswith(".parquet") for p in result["paths_by_group"]["PN"])


def test_download_is_idempotent(tmp_path) -> None:
    root = specs.SISPRENATAL.roots[0]
    listings = {root: ["PNSP1202.dbc"]}
    client_holder = {}

    def factory():
        client = FakeClient(listings)
        client_holder["last"] = client
        return client

    generic_backend.download(
        specs.SISPRENATAL, years=[2012], cache_dir=tmp_path,
        client_factory=factory, dbc_reader=_fake_reader,
    )
    first = client_holder["last"].downloads

    generic_backend.download(
        specs.SISPRENATAL, years=[2012], cache_dir=tmp_path,
        client_factory=factory, dbc_reader=_fake_reader,
    )
    second = client_holder["last"].downloads

    assert first == [f"{root}/PNSP1202.dbc"]
    assert second == []  # parquet already cached → no re-download


def test_download_group_dirs_spec(tmp_path) -> None:
    cc_dir = dict(specs.SISCAN.group_dirs)["CC"]
    cm_dir = dict(specs.SISCAN.group_dirs)["CM"]
    listings = {cc_dir: ["CCSP0601.dbc"], cm_dir: ["CMSP0907.dbc"]}

    result = generic_backend.download(
        specs.SISCAN,
        years=[2006, 2009],
        cache_dir=tmp_path,
        client_factory=_factory(listings),
        dbc_reader=_fake_reader,
    )

    assert sorted(result["paths_by_group"]) == ["CC", "CM"]


def test_download_dbf_system(tmp_path) -> None:
    root = specs.PNI.roots[0]
    listings = {root: ["CPNISP19.DBF", "DPNISP19.DBF"]}

    result = generic_backend.download(
        specs.PNI,
        years=[2019],
        cache_dir=tmp_path,
        client_factory=_factory(listings),
        dbc_reader=_fake_reader,
    )

    assert result["successful_downloads"] == 2
    assert sorted(result["paths_by_group"]) == ["CPNI", "DPNI"]


def test_discover_summary_state_spec(tmp_path) -> None:
    root = specs.SISPRENATAL.roots[0]
    listings = {root: ["PNSP1202.dbc", "PNRJ1202.dbc"]}

    summary = generic_backend.discover_summary(
        specs.SISPRENATAL,
        years=[2012],
        states=["SP"],
        client_factory=_factory(listings),
    )

    assert summary["source"] == "sisprenatal"
    assert summary["documents_found"] == 1  # only SP after filter
    assert summary["by_group"] == {"PN": 1}
    assert summary["filters"]["states"] == ["SP"]
    assert summary["total_size_bytes"] == 1234


def test_discover_summary_national_spec_has_no_states(tmp_path) -> None:
    root = specs.PAINEL_ONCOLOGIA.roots[0]
    listings = {root: ["POBR2015.dbc"]}

    summary = generic_backend.discover_summary(
        specs.PAINEL_ONCOLOGIA,
        years=[2015],
        client_factory=_factory(listings),
    )

    assert summary["source"] == "painel_oncologia"
    assert summary["by_state"] == {}
    assert "states" not in summary["filters"]
