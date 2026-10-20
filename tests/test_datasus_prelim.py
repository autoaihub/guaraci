"""Dado preliminar do SIM, do SINASC e do e-SUS Notifica (Chagas crônica).

Offline: o cliente FTP falso serve listagens em memória. Cobre a regra herdada
do SINAN (o consolidado vence, o PRELIM só preenche o ano que falta e sai
marcado), a deduplicação do SINASC/ANT e a fonte nova de Chagas crônica.
"""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.datasus.ftp import FtpEntry, generic_backend, sim_backend, specs
from guaraci.datasus.ftp.catalog import System
from guaraci.datasus.ftp.discovery import (
    SIM_CID9_PATH,
    SIM_CID10_PATH,
    SIM_PRELIM_PATH,
    discover_sim,
    discover_spec,
)
from guaraci.datasus.ftp_source import FtpDataSource
from guaraci.services.downloads import DownloadService

SINASC_NOV, SINASC_ANT = specs.SINASC.roots
SINASC_PRELIM = specs.SINASC.prelim_roots[0]
DOFET_FINAL = specs.SIM_OBITOS_FETAIS.roots[0]
DOFET_PRELIM = specs.SIM_OBITOS_FETAIS.prelim_roots[0]
CHAGAS = specs.ESUS_NOTIFICA_CHAGAS_CRONICA
CHAGAS_FINAIS = CHAGAS.roots[0]
CHAGAS_PRELIM = CHAGAS.prelim_roots[0]


class FakeClient:
    def __init__(self, listings: dict[str, list[str]]) -> None:
        self.listings = listings
        self.listed: list[str] = []
        self.downloads: list[str] = []

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def list_dir(self, path: str) -> list[FtpEntry]:
        self.listed.append(path)
        return [FtpEntry(name=name) for name in self.listings.get(path, [])]

    async def size(self, path: str) -> int:
        return 10

    async def download(self, path: str, dest) -> None:
        self.downloads.append(path)
        dest.write_bytes(b"\x00")


def _reader(_path) -> pl.DataFrame:
    return pl.DataFrame({"X": ["1"]})


# --- SIM -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sim_fills_missing_year_from_prelim_and_marks_it() -> None:
    client = FakeClient(
        {
            SIM_CID10_PATH: ["DOAC2024.dbc"],
            SIM_PRELIM_PATH: ["DOAC2025.dbc", "DOSP2025.dbc"],
        }
    )

    recs = await discover_sim(client, years=[2024, 2025], groups=["CID10"], states=["AC"])

    assert [(r.basename, r.preliminary) for r in recs] == [
        ("DOAC2024.dbc", False),
        ("DOAC2025.dbc", True),
    ]
    assert all(r.group == "CID10" for r in recs)
    assert recs[1].path == f"{SIM_PRELIM_PATH}/DOAC2025.dbc"


@pytest.mark.asyncio
async def test_sim_final_wins_and_prelim_is_not_listed_when_years_are_covered() -> None:
    client = FakeClient(
        {SIM_CID10_PATH: ["DOAC2024.dbc"], SIM_PRELIM_PATH: ["DOAC2024.dbc"]}
    )

    recs = await discover_sim(client, years=[2024], groups=["CID10"])

    assert [(r.path, r.preliminary) for r in recs] == [
        (f"{SIM_CID10_PATH}/DOAC2024.dbc", False)
    ]
    assert SIM_PRELIM_PATH not in client.listed


@pytest.mark.asyncio
async def test_sim_cid9_never_reads_prelim() -> None:
    client = FakeClient({SIM_CID9_PATH: [], SIM_PRELIM_PATH: ["DOAC2025.dbc"]})
    recs = await discover_sim(client, years=[2025], groups=["CID9"])
    assert recs == []
    assert SIM_PRELIM_PATH not in client.listed


def test_sim_summary_and_download_report_preliminary(tmp_path) -> None:
    listings = {SIM_CID10_PATH: ["DOAC2024.dbc"], SIM_PRELIM_PATH: ["DOAC2025.dbc"]}

    payload = sim_backend.discover_sim_summary(
        years=[2024, 2025], groups=["CID10"], client_factory=lambda: FakeClient(listings)
    )
    assert payload["preliminary_files"] == ["DOAC2025.dbc"]
    assert any("preliminary" in w for w in payload["warnings"])

    result = sim_backend.download_sim(
        years=[2024, 2025],
        groups=["CID10"],
        cache_dir=tmp_path,
        client_factory=lambda: FakeClient(listings),
        dbc_reader=_reader,
    )
    assert result["successful_downloads"] == 2
    assert result["preliminary_files"] == ["DOAC2025.dbc"]


# --- SIM fetal e SINASC (motor genérico) -----------------------------------


@pytest.mark.asyncio
async def test_sim_fetal_prelim_fills_2026_but_final_2025_wins() -> None:
    client = FakeClient(
        {
            DOFET_FINAL: ["DOFET24.dbc", "DOFET25.dbc"],
            DOFET_PRELIM: ["DOFET25.dbc", "DOFET26.dbc", "DOEXT26.dbc"],
        }
    )

    recs = await discover_spec(client, specs.SIM_OBITOS_FETAIS, years=[2025, 2026])

    assert [(r.path, r.preliminary) for r in recs] == [
        (f"{DOFET_FINAL}/DOFET25.dbc", False),
        (f"{DOFET_PRELIM}/DOFET26.dbc", True),
    ]


@pytest.mark.asyncio
async def test_sinasc_prelim_by_state() -> None:
    client = FakeClient(
        {
            SINASC_NOV: ["DNAC2022.dbc"],
            SINASC_PRELIM: ["DNAC2025.dbc", "DNSP2025.dbc", "DNEX25.dbc"],
        }
    )

    recs = await discover_spec(client, specs.SINASC, years=[2025], states=["AC"])

    assert [(r.basename, r.state, r.preliminary) for r in recs] == [
        ("DNAC2025.dbc", "AC", True)
    ]


@pytest.mark.asyncio
async def test_sinasc_ant_reads_1994_and_skips_duplicates() -> None:
    client = FakeClient(
        {
            SINASC_NOV: ["DNAC2014.dbc", "DNRJ2014.DBC"],
            # DNAC2014 repete o do NOV; DNRAC94.DBC é a cópia de nome curto.
            SINASC_ANT: ["DNAC2014.dbc", "DNRAC1994.dbc", "DNRAC94.DBC", "DNRES1995.dbc"],
        }
    )

    recs = await discover_spec(client, specs.SINASC, years=[1994, 1995, 2014])

    assert [(r.path, r.state, r.year) for r in recs] == [
        (f"{SINASC_ANT}/DNRAC1994.dbc", "AC", 1994),
        (f"{SINASC_NOV}/DNAC2014.dbc", "AC", 2014),
        (f"{SINASC_ANT}/DNRES1995.dbc", "ES", 1995),
        (f"{SINASC_NOV}/DNRJ2014.DBC", "RJ", 2014),
    ]
    assert not any(r.preliminary for r in recs)


def test_sinasc_schema_floor_is_1994_and_default_stays_consolidated() -> None:
    params = {p["name"]: p for p in DownloadService().get_source_schema("sinasc")["params"]}
    assert params["start_year"]["minimum"] == 1994
    assert params["start_year"]["default"] == 2022


# --- e-SUS Notifica: Chagas crônica ----------------------------------------


def test_chagas_spec_parses_national_file() -> None:
    rec = CHAGAS.parse("DCCRBR23.dbc")
    assert (rec.system, rec.group, rec.state, rec.year) == (
        System.ESUS_NOTIFICA,
        "DCCR",
        None,
        2023,
    )
    assert CHAGAS.parse("CHAGBR23.dbc") is None


def test_chagas_summary_marks_prelim_years() -> None:
    listings = {
        CHAGAS_FINAIS: ["DCCRBR23.dbc"],
        CHAGAS_PRELIM: ["DCCRBR24.dbc", "DCCRBR25.dbc"],
    }
    payload = generic_backend.discover_summary(
        CHAGAS, years=[2023, 2024, 2025], client_factory=lambda: FakeClient(listings)
    )
    assert payload["documents_found"] == 3
    assert payload["preliminary_files"] == ["DCCRBR24.dbc", "DCCRBR25.dbc"]


def test_chagas_registered_with_consolidated_default() -> None:
    schema = DownloadService().get_source_schema("esus_notifica_chagas_cronica")
    params = {p["name"]: p for p in schema["params"]}
    assert params["start_year"]["minimum"] == 2023
    assert params["start_year"]["default"] == 2023
    assert "states" not in params and "groups" not in params


def test_chagas_load_keeps_uf_names(tmp_path) -> None:
    # As colunas de UF vêm por extenso; o mapeamento de código as apagaria.
    path = tmp_path / "DCCRBR23.parquet"
    pl.DataFrame({"SG_UF_NOT": ["Minas Gerais"], "SG_UF": ["Bahia"]}).write_parquet(path)
    ds = FtpDataSource(CHAGAS, output_path=str(tmp_path))
    ds.data["DCCR"].append(str(path))

    df = ds.load_dataframe()

    assert df["SG_UF_NOT"].to_list() == ["Minas Gerais"]
    assert df["SG_UF"].to_list() == ["Bahia"]
