"""Tests for `guaraci.datasus.ftp.catalog`.

Pure parsing — no network, no fixtures larger than a string.
"""

from __future__ import annotations

import pytest

from guaraci.datasus.ftp.catalog import (
    FileRecord,
    System,
    parse,
    parse_sih,
    parse_sim,
    parse_sinan,
)


# --- SIH ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("basename", "group", "state", "year", "month"),
    [
        ("RDSP2401.dbc", "RD", "SP", 2024, 1),
        ("RDSP9201.dbc", "RD", "SP", 1992, 1),
        ("RDSP0712.dbc", "RD", "SP", 2007, 12),
        ("RDSP0801.dbc", "RD", "SP", 2008, 1),
        ("RJRJ1503.dbc", "RJ", "RJ", 2015, 3),
        ("SPMG2206.dbc", "SP", "MG", 2022, 6),
        ("CHBA0801.dbc", "CH", "BA", 2008, 1),
        ("CMSP1310.dbc", "CM", "SP", 2013, 10),
        ("ERSP9912.dbc", "ER", "SP", 1999, 12),
        ("rdsp2401.dbc", "RD", "SP", 2024, 1),  # case-insensitive
    ],
)
def test_parse_sih_valid(basename: str, group: str, state: str, year: int, month: int) -> None:
    rec = parse_sih(basename)
    assert rec is not None
    assert rec.system is System.SIH
    assert rec.group == group
    assert rec.state == state
    assert rec.year == year
    assert rec.month == month
    assert rec.path == ""  # set by discovery, not by parsing


@pytest.mark.parametrize(
    "basename",
    [
        "",
        "RDSP24.dbc",         # missing month
        "RDSP24011.dbc",      # too many digits
        "XXSP2401.dbc",       # unknown group
        "RDSP24X1.dbc",       # non-digit month
        "RDSP2401.parquet",   # wrong extension
        "RDSP2401",           # missing extension
        "noise.txt",
    ],
)
def test_parse_sih_invalid(basename: str) -> None:
    assert parse_sih(basename) is None


def test_parse_sih_returns_immutable_record() -> None:
    rec = parse_sih("RDSP2401.dbc")
    assert rec is not None
    with pytest.raises(Exception):
        rec.year = 2025  # frozen dataclass


def test_file_record_with_path_returns_new_instance() -> None:
    rec = parse_sih("RDSP2401.dbc")
    assert rec is not None
    enriched = rec.with_path("/dissemin/publicos/SIHSUS/200801_/Dados/RDSP2401.dbc")
    assert enriched.path.endswith("RDSP2401.dbc")
    assert rec.path == ""  # original untouched


def test_file_record_to_dict_is_json_serializable() -> None:
    import json

    rec = parse_sih("RDSP2401.dbc")
    assert rec is not None
    payload = rec.to_dict()
    json.dumps(payload)  # must not raise


# --- SIM ---------------------------------------------------------------------

def test_parse_sim_cid10() -> None:
    rec = parse_sim("DOSP2020.dbc")
    assert rec is not None
    assert rec.system is System.SIM
    assert rec.group == "CID10"
    assert rec.state == "SP"
    assert rec.year == 2020
    assert rec.month is None


def test_parse_sim_cid9() -> None:
    rec = parse_sim("MORTSP1992.dbc")
    assert rec is not None
    assert rec.system is System.SIM
    assert rec.group == "CID9"
    assert rec.state == "SP"
    assert rec.year == 1992


@pytest.mark.parametrize(
    "basename",
    [
        "",
        "DOSP20.dbc",       # 2-digit year
        "DOSP20201.dbc",    # 5-digit year
        "RDSP2401.dbc",     # SIH, not SIM
        "noise.txt",
    ],
)
def test_parse_sim_invalid(basename: str) -> None:
    assert parse_sim(basename) is None


# --- SINAN -------------------------------------------------------------------

def test_parse_sinan_national() -> None:
    rec = parse_sinan("DENGBR24.dbc")
    assert rec is not None
    assert rec.system is System.SINAN
    assert rec.group == "DENG"
    assert rec.state is None
    assert rec.year == 2024


@pytest.mark.parametrize(
    ("basename", "group", "year"),
    [
        ("CHIKBR23.dbc", "CHIK", 2023),
        ("HANSBR95.dbc", "HANS", 1995),  # 95 -> 1995 (window starts at 92)
        ("DENGBR00.dbc", "DENG", 2000),
    ],
)
def test_parse_sinan_window(basename: str, group: str, year: int) -> None:
    rec = parse_sinan(basename)
    assert rec is not None
    assert rec.group == group
    assert rec.year == year


@pytest.mark.parametrize(
    "basename",
    ["", "DENGBR2024.dbc", "DENGBR.dbc", "noise.txt"],
)
def test_parse_sinan_invalid(basename: str) -> None:
    assert parse_sinan(basename) is None


# --- dispatcher --------------------------------------------------------------

def test_parse_dispatches_by_pattern() -> None:
    sih_rec = parse("RDSP2401.dbc")
    sim_rec = parse("DOSP2020.dbc")
    sinan_rec = parse("DENGBR24.dbc")
    assert sih_rec is not None and sih_rec.system is System.SIH
    assert sim_rec is not None and sim_rec.system is System.SIM
    assert sinan_rec is not None and sinan_rec.system is System.SINAN


def test_parse_returns_none_for_unknown_pattern() -> None:
    assert parse("README.txt") is None
    assert parse("") is None
