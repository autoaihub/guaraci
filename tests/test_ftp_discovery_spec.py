"""Tests for the spec-driven `discover_spec` (phase 5).

Offline: the FTP client is stubbed. Exercises the two directory layouts
(``group_dirs`` vs flat ``roots``), group/year/state filtering, the
national (no-state) case, and size enrichment.
"""

from __future__ import annotations

import pytest

from guaraci.datasus.ftp import FtpEntry, specs
from guaraci.datasus.ftp.discovery import discover_spec


class _StubClient:
    def __init__(self, listings: dict[str, list[str]], sizes: dict[str, int] | None = None) -> None:
        self.listings = listings
        self.sizes = sizes or {}
        self.calls: list[tuple[str, str]] = []

    async def list_dir(self, path: str) -> list[FtpEntry]:
        self.calls.append(("list_dir", path))
        return [FtpEntry(name=name) for name in self.listings.get(path, [])]

    async def size(self, path: str) -> int:
        self.calls.append(("size", path))
        return int(self.sizes.get(path, 0))


def _listed_dirs(client: _StubClient) -> list[str]:
    return [path for kind, path in client.calls if kind == "list_dir"]


@pytest.mark.asyncio
async def test_group_dirs_visits_only_requested_group() -> None:
    lt_dir = dict(specs.CNES.group_dirs)["LT"]
    st_dir = dict(specs.CNES.group_dirs)["ST"]
    client = _StubClient(
        {
            lt_dir: ["LTSP0512.dbc", "LTRJ0512.dbc"],
            st_dir: ["STSP0512.dbc"],
        }
    )

    results = await discover_spec(client, specs.CNES, years=[2005], groups=["LT"])

    assert {r.group for r in results} == {"LT"}
    assert _listed_dirs(client) == [lt_dir]  # ST directory never touched


@pytest.mark.asyncio
async def test_group_dirs_without_groups_visits_all() -> None:
    client = _StubClient({})
    await discover_spec(client, specs.CNES, years=[2005], groups=None)
    assert set(_listed_dirs(client)) == {d for _, d in specs.CNES.group_dirs}


@pytest.mark.asyncio
async def test_flat_roots_filter_group_from_filename() -> None:
    root = specs.SIA.roots[1]  # 200801_ window
    client = _StubClient(
        {
            root: ["PASP2401.dbc", "BISP2401.dbc", "PARJ2401.dbc"],
            specs.SIA.roots[0]: [],
        }
    )

    results = await discover_spec(client, specs.SIA, years=[2024], groups=["PA"])

    assert sorted(r.basename for r in results) == ["PARJ2401.dbc", "PASP2401.dbc"]
    # Flat layout lists every root regardless of group.
    assert set(_listed_dirs(client)) == set(specs.SIA.roots)


@pytest.mark.asyncio
async def test_state_and_year_filters_apply() -> None:
    root = specs.SISPRENATAL.roots[0]
    client = _StubClient(
        {
            root: [
                "PNSP1202.dbc",
                "PNRJ1202.dbc",
                "PNSP1302.dbc",  # wrong year
                "garbage.txt",   # unparseable
            ]
        }
    )

    results = await discover_spec(
        client, specs.SISPRENATAL, years=[2012], states=["SP"]
    )

    assert [r.basename for r in results] == ["PNSP1202.dbc"]


@pytest.mark.asyncio
async def test_national_spec_ignores_states() -> None:
    root = specs.PAINEL_ONCOLOGIA.roots[0]
    client = _StubClient({root: ["POBR2014.dbc", "POBR2015.dbc"]})

    results = await discover_spec(
        client, specs.PAINEL_ONCOLOGIA, years=[2015], states=["SP"]
    )

    assert [r.basename for r in results] == ["POBR2015.dbc"]
    assert results[0].state is None


@pytest.mark.asyncio
async def test_fetch_sizes_enriches_records() -> None:
    root = specs.RESP.roots[0]
    path = f"{root}/RESPSP15.dbc"
    client = _StubClient({root: ["RESPSP15.dbc"]}, sizes={path: 4096})

    results = await discover_spec(client, specs.RESP, years=[2015], fetch_sizes=True)

    assert results[0].size == 4096
    assert ("size", path) in client.calls


@pytest.mark.asyncio
async def test_empty_years_short_circuits() -> None:
    client = _StubClient({})
    assert await discover_spec(client, specs.RESP, years=[]) == []
    assert client.calls == []
