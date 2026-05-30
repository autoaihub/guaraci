"""Tests for the phase-5 DATASUS system specs (`guaraci.datasus.ftp.specs`).

Each spec carries a filename regex; these tests pin the parse contract
(group / state / year / month extraction, 2- vs 4-digit year resolution,
national-vs-state handling) against basenames confirmed by FTP recon.
"""

from __future__ import annotations

import pytest

from guaraci.datasus.ftp import specs
from guaraci.datasus.ftp.catalog import System


def test_sinasc_parses_state_and_4digit_year() -> None:
    rec = specs.SINASC.parse("DNSP2020.dbc")
    assert rec is not None
    assert (rec.system, rec.group, rec.state, rec.year, rec.month) == (
        System.SINASC,
        "DNRES",
        "SP",
        2020,
        None,
    )


def test_sinasc_rejects_foreign_basename() -> None:
    assert specs.SINASC.parse("DOSP2020.dbc") is None  # that's SIM, not SINASC


@pytest.mark.parametrize(
    "basename,group,state,year,month",
    [
        ("PASP2401.dbc", "PA", "SP", 2024, 1),
        ("PAAC0001.dbc", "PA", "AC", 2000, 1),
        ("BISP2412.dbc", "BI", "SP", 2024, 12),
        ("ABOSP2401.dbc", "ABO", "SP", 2024, 1),  # ABO not shadowed by AB
        ("ABSP2401.dbc", "AB", "SP", 2024, 1),
        ("AMPSP2401.dbc", "AMP", "SP", 2024, 1),  # AMP not shadowed by AM
        ("SADRS0512.dbc", "SAD", "RS", 2005, 12),
    ],
)
def test_sia_group_alternation(basename, group, state, year, month) -> None:
    rec = specs.SIA.parse(basename)
    assert rec is not None
    assert (rec.group, rec.state, rec.year, rec.month) == (group, state, year, month)


def test_cnes_two_letter_group_and_month() -> None:
    rec = specs.CNES.parse("LTSP0512.dbc")
    assert rec is not None
    assert (rec.group, rec.state, rec.year, rec.month) == ("LT", "SP", 2005, 12)


def test_pni_reads_dbf_and_two_families() -> None:
    cpni = specs.PNI.parse("CPNISP19.DBF")
    dpni = specs.PNI.parse("DPNIAC00.dbf")
    assert cpni is not None and dpni is not None
    assert (cpni.group, cpni.state, cpni.year, cpni.month) == ("CPNI", "SP", 2019, None)
    assert (dpni.group, dpni.state, dpni.year) == ("DPNI", "AC", 2000)


def test_ciha_and_cih_legacy() -> None:
    ciha = specs.CIHA.parse("CIHASP1503.dbc")
    cih = specs.CIH.parse("CRSP0810.dbc")
    assert ciha is not None and cih is not None
    assert (ciha.group, ciha.state, ciha.year, ciha.month) == ("CIHA", "SP", 2015, 3)
    assert (cih.group, cih.state, cih.year, cih.month) == ("CR", "SP", 2008, 10)


def test_siscan_colo_and_mama_groups() -> None:
    cc = specs.SISCAN.parse("CCSP0601.dbc")
    cm = specs.SISCAN.parse("CMSP0907.dbc")
    assert cc is not None and cm is not None
    assert (cc.group, cc.year, cc.month) == ("CC", 2006, 1)
    assert (cm.group, cm.year, cm.month) == ("CM", 2009, 7)


def test_sisprenatal_resp_pce_state_systems() -> None:
    pn = specs.SISPRENATAL.parse("PNSP1202.dbc")
    resp = specs.RESP.parse("RESPSP15.dbc")
    pce = specs.PCE.parse("PCEAL00.dbc")
    assert pn is not None and resp is not None and pce is not None
    assert (pn.group, pn.state, pn.year, pn.month) == ("PN", "SP", 2012, 2)
    assert (resp.group, resp.state, resp.year, resp.month) == ("RESP", "SP", 2015, None)
    assert (pce.group, pce.state, pce.year) == ("PCE", "AL", 2000)


def test_painel_oncologia_is_national() -> None:
    rec = specs.PAINEL_ONCOLOGIA.parse("POBR2015.dbc")
    assert rec is not None
    assert rec.state is None
    assert (rec.group, rec.year, rec.month) == ("PO", 2015, None)


def test_two_digit_year_window_boundary() -> None:
    # >= 92 resolves to 19xx, otherwise 20xx (shared DATASUS convention).
    assert specs.RESP.parse("RESPSP94.dbc").year == 1994
    assert specs.RESP.parse("RESPSP05.dbc").year == 2005


def test_registry_is_complete_and_consistent() -> None:
    assert set(specs.SPECS) == {s.name for s in specs.ALL_SPECS}
    assert len(specs.ALL_SPECS) == 11
    # Every spec defines exactly one of roots / group_dirs.
    for spec in specs.ALL_SPECS:
        assert bool(spec.roots) != bool(spec.group_dirs), spec.name
    assert specs.get_spec("SINASC").system is System.SINASC
    with pytest.raises(KeyError):
        specs.get_spec("nope")
