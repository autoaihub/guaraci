"""Tests for `guaraci.datasus.ftp.discovery`.

The FTP client is stubbed so these tests run offline. They exercise:

- filter semantics (year / group / state / month);
- traversal of legacy vs current SIH directories;
- ordering of results;
- enrichment with ``SIZE`` only when explicitly requested.
"""

from __future__ import annotations

import pytest

from guaraci.datasus.ftp import FtpEntry
from guaraci.datasus.ftp.discovery import (
    SIH_CURRENT_PATH,
    SIH_LEGACY_PATH,
    SIM_CID9_PATH,
    SIM_CID10_PATH,
    SINAN_FINAIS_PATH,
    SINAN_PRELIM_PATH,
    discover_sih,
    discover_sim,
    discover_sinan,
)


class _StubClient:
    """Minimal stand-in for :class:`DatasusFtpClient` in pure unit tests."""

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


@pytest.mark.asyncio
async def test_discover_sih_filters_year_group_state_month() -> None:
    client = _StubClient(
        {
            SIH_CURRENT_PATH: [
                "RDSP2401.dbc",
                "RDRJ2401.dbc",
                "RDSP2402.dbc",
                "RJSP2401.dbc",
                "RDSP2301.dbc",  # wrong year
                "README.txt",     # ignored by parser
            ]
        }
    )

    results = await discover_sih(
        client,
        years=[2024],
        groups=["RD"],
        states=["SP"],
        months=[1],
    )

    assert [r.basename for r in results] == ["RDSP2401.dbc"]
    assert results[0].path == f"{SIH_CURRENT_PATH}/RDSP2401.dbc"


@pytest.mark.asyncio
async def test_discover_sih_traverses_both_directories_for_split_window() -> None:
    client = _StubClient(
        {
            SIH_LEGACY_PATH: ["RDSP0712.dbc"],
            SIH_CURRENT_PATH: ["RDSP0801.dbc", "RDSP2401.dbc"],
        }
    )

    results = await discover_sih(
        client,
        years=[2007, 2008, 2024],
        groups=["RD"],
        states=["SP"],
    )

    assert [r.basename for r in results] == [
        "RDSP0712.dbc",
        "RDSP0801.dbc",
        "RDSP2401.dbc",
    ]
    # Legacy + current both visited
    paths_visited = {call[1] for call in client.calls if call[0] == "list_dir"}
    assert paths_visited == {SIH_LEGACY_PATH, SIH_CURRENT_PATH}


@pytest.mark.asyncio
async def test_discover_sih_only_visits_legacy_for_pre_2008_years() -> None:
    client = _StubClient(
        {
            SIH_LEGACY_PATH: ["RDSP0712.dbc"],
            SIH_CURRENT_PATH: ["RDSP0801.dbc"],
        }
    )

    results = await discover_sih(
        client,
        years=[2007],
        groups=["RD"],
    )

    assert [r.basename for r in results] == ["RDSP0712.dbc"]
    visited = {call[1] for call in client.calls if call[0] == "list_dir"}
    assert visited == {SIH_LEGACY_PATH}


@pytest.mark.asyncio
async def test_discover_sih_only_visits_current_for_post_2008_years() -> None:
    client = _StubClient(
        {
            SIH_LEGACY_PATH: ["RDSP0712.dbc"],
            SIH_CURRENT_PATH: ["RDSP2401.dbc"],
        }
    )

    results = await discover_sih(
        client,
        years=[2024],
        groups=["RD"],
    )

    assert [r.basename for r in results] == ["RDSP2401.dbc"]
    visited = {call[1] for call in client.calls if call[0] == "list_dir"}
    assert visited == {SIH_CURRENT_PATH}


@pytest.mark.asyncio
async def test_discover_sih_sorts_results_by_group_state_year_month_basename() -> None:
    client = _StubClient(
        {
            SIH_CURRENT_PATH: [
                "RDSP2402.dbc",
                "RDSP2401.dbc",
                "RJSP2401.dbc",
                "RDRJ2401.dbc",
            ]
        }
    )

    results = await discover_sih(
        client,
        years=[2024],
        groups=["RD", "RJ"],
    )

    assert [r.basename for r in results] == [
        "RDRJ2401.dbc",
        "RDSP2401.dbc",
        "RDSP2402.dbc",
        "RJSP2401.dbc",
    ]


@pytest.mark.asyncio
async def test_discover_sih_without_groups_returns_all_groups() -> None:
    client = _StubClient(
        {
            SIH_CURRENT_PATH: [
                "RDSP2401.dbc",
                "RJSP2401.dbc",
                "CHSP2401.dbc",
            ]
        }
    )

    results = await discover_sih(client, years=[2024], states=["SP"])
    assert sorted(r.group for r in results) == ["CH", "RD", "RJ"]


@pytest.mark.asyncio
async def test_discover_sih_fetch_sizes_enriches_records() -> None:
    listings = {SIH_CURRENT_PATH: ["RDSP2401.dbc"]}
    sizes = {f"{SIH_CURRENT_PATH}/RDSP2401.dbc": 17_456_640}
    client = _StubClient(listings, sizes)

    results = await discover_sih(
        client,
        years=[2024],
        groups=["RD"],
        states=["SP"],
        fetch_sizes=True,
    )

    assert len(results) == 1
    assert results[0].size == 17_456_640
    assert ("size", f"{SIH_CURRENT_PATH}/RDSP2401.dbc") in client.calls


@pytest.mark.asyncio
async def test_discover_sih_returns_empty_when_no_years_requested() -> None:
    client = _StubClient({SIH_CURRENT_PATH: ["RDSP2401.dbc"]})
    results = await discover_sih(client, years=[])
    assert results == []
    assert client.calls == []


# --- discover_sim ------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_sim_filters_year_group_state() -> None:
    client = _StubClient(
        {
            SIM_CID10_PATH: [
                "DOSP2024.dbc",
                "DORJ2024.dbc",
                "DOSP2023.dbc",  # wrong year
                "LEIAME.txt",     # ignored by parser
            ],
            SIM_CID9_PATH: ["MORTSP2024.dbc"],  # wrong group
        }
    )

    results = await discover_sim(
        client,
        years=[2024],
        groups=["CID10"],
        states=["SP"],
    )

    assert [r.basename for r in results] == ["DOSP2024.dbc"]
    assert results[0].path == f"{SIM_CID10_PATH}/DOSP2024.dbc"
    assert results[0].group == "CID10"


@pytest.mark.asyncio
async def test_discover_sim_visits_only_requested_group_directory() -> None:
    client = _StubClient(
        {
            SIM_CID10_PATH: ["DOSP2024.dbc"],
            SIM_CID9_PATH: ["MORTSP1995.dbc"],
        }
    )

    results = await discover_sim(client, years=[2024], groups=["CID10"])

    assert [r.basename for r in results] == ["DOSP2024.dbc"]
    visited = {call[1] for call in client.calls if call[0] == "list_dir"}
    assert visited == {SIM_CID10_PATH}


@pytest.mark.asyncio
async def test_discover_sim_without_groups_visits_both_directories() -> None:
    client = _StubClient(
        {
            SIM_CID10_PATH: ["DOSP2024.dbc"],
            SIM_CID9_PATH: ["MORTSP1995.dbc"],
        }
    )

    results = await discover_sim(client, years=[1995, 2024])

    assert sorted(r.group for r in results) == ["CID10", "CID9"]
    visited = {call[1] for call in client.calls if call[0] == "list_dir"}
    assert visited == {SIM_CID10_PATH, SIM_CID9_PATH}


@pytest.mark.asyncio
async def test_discover_sim_sorts_by_group_state_year_basename() -> None:
    client = _StubClient(
        {
            SIM_CID10_PATH: [
                "DOSP2024.dbc",
                "DORJ2024.dbc",
                "DOSP2023.dbc",
            ],
        }
    )

    results = await discover_sim(
        client,
        years=[2023, 2024],
        groups=["CID10"],
    )

    assert [r.basename for r in results] == [
        "DORJ2024.dbc",
        "DOSP2023.dbc",
        "DOSP2024.dbc",
    ]


@pytest.mark.asyncio
async def test_discover_sim_fetch_sizes_enriches_records() -> None:
    listings = {SIM_CID10_PATH: ["DOSP2024.dbc"]}
    sizes = {f"{SIM_CID10_PATH}/DOSP2024.dbc": 9_999_999}
    client = _StubClient(listings, sizes)

    results = await discover_sim(
        client,
        years=[2024],
        groups=["CID10"],
        fetch_sizes=True,
    )

    assert len(results) == 1
    assert results[0].size == 9_999_999
    assert ("size", f"{SIM_CID10_PATH}/DOSP2024.dbc") in client.calls


@pytest.mark.asyncio
async def test_discover_sim_returns_empty_when_no_years_requested() -> None:
    client = _StubClient({SIM_CID10_PATH: ["DOSP2024.dbc"]})
    results = await discover_sim(client, years=[])
    assert results == []
    assert client.calls == []


# --- discover_sinan ----------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_sinan_filters_year_group() -> None:
    client = _StubClient(
        {
            SINAN_FINAIS_PATH: [
                "DENGBR23.dbc",
                "CHIKBR23.dbc",
                "DENGBR22.dbc",  # wrong year
                "LEIAME.txt",     # ignored by parser
            ],
            SINAN_PRELIM_PATH: [],
        }
    )

    results = await discover_sinan(client, years=[2023], groups=["DENG"])

    assert [r.basename for r in results] == ["DENGBR23.dbc"]
    assert results[0].path == f"{SINAN_FINAIS_PATH}/DENGBR23.dbc"
    assert results[0].group == "DENG"
    assert results[0].state is None


@pytest.mark.asyncio
async def test_discover_sinan_scans_both_finais_and_prelim() -> None:
    client = _StubClient(
        {
            SINAN_FINAIS_PATH: ["DENGBR22.dbc"],
            SINAN_PRELIM_PATH: ["DENGBR23.dbc"],
        }
    )

    results = await discover_sinan(client, years=[2022, 2023], groups=["DENG"])

    assert [r.basename for r in results] == ["DENGBR22.dbc", "DENGBR23.dbc"]
    visited = {call[1] for call in client.calls if call[0] == "list_dir"}
    assert visited == {SINAN_FINAIS_PATH, SINAN_PRELIM_PATH}


@pytest.mark.asyncio
async def test_discover_sinan_finais_wins_over_prelim_on_duplicate() -> None:
    # The same consolidated file appears in both windows; FINAIS must win
    # so the download step stays idempotent. PRELIM still fills the gap for
    # a disease only present there (CHIK).
    client = _StubClient(
        {
            SINAN_FINAIS_PATH: ["DENGBR23.dbc"],
            SINAN_PRELIM_PATH: ["DENGBR23.dbc", "CHIKBR23.dbc"],
        }
    )

    results = await discover_sinan(client, years=[2023])

    assert [r.basename for r in results] == ["CHIKBR23.dbc", "DENGBR23.dbc"]
    by_name = {r.basename: r for r in results}
    # FINAIS copy wins for the duplicate...
    assert by_name["DENGBR23.dbc"].path == f"{SINAN_FINAIS_PATH}/DENGBR23.dbc"
    # ...and PRELIM-only files are still discovered.
    assert by_name["CHIKBR23.dbc"].path == f"{SINAN_PRELIM_PATH}/CHIKBR23.dbc"


@pytest.mark.asyncio
async def test_discover_sinan_sorts_by_group_year_basename() -> None:
    client = _StubClient(
        {
            SINAN_FINAIS_PATH: [
                "DENGBR24.dbc",
                "DENGBR23.dbc",
                "CHIKBR23.dbc",
            ],
            SINAN_PRELIM_PATH: [],
        }
    )

    results = await discover_sinan(client, years=[2023, 2024])

    assert [r.basename for r in results] == [
        "CHIKBR23.dbc",
        "DENGBR23.dbc",
        "DENGBR24.dbc",
    ]


@pytest.mark.asyncio
async def test_discover_sinan_without_groups_returns_all_diseases() -> None:
    client = _StubClient(
        {
            SINAN_FINAIS_PATH: ["DENGBR23.dbc", "CHIKBR23.dbc", "CHAGBR23.dbc"],
            SINAN_PRELIM_PATH: [],
        }
    )

    results = await discover_sinan(client, years=[2023])
    assert sorted(r.group for r in results) == ["CHAG", "CHIK", "DENG"]


@pytest.mark.asyncio
async def test_discover_sinan_returns_empty_when_no_years_requested() -> None:
    client = _StubClient({SINAN_FINAIS_PATH: ["DENGBR23.dbc"]})
    results = await discover_sinan(client, years=[])
    assert results == []
    assert client.calls == []
