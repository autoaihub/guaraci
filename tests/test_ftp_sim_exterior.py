"""SIM DOREXT: óbitos de residentes no exterior (spec nova do FTP do DATASUS)."""
from __future__ import annotations

import pytest

from guaraci.datasus.ftp import specs
from guaraci.datasus.ftp.catalog import System
from guaraci.services.downloads import DownloadService


@pytest.mark.parametrize(
    "basename,year",
    [
        ("DOREXT13.dbc", 2013),
        ("DOREXT25.dbc", 2025),
        ("DOREXT20.DBC", 2020),  # o servidor mistura .dbc e .DBC
        ("dorext22.dbc", 2022),
    ],
)
def test_dorext_parseia_ano_de_dois_digitos_em_caixa_mista(basename, year):
    rec = specs.SIM_OBITOS_EXTERIOR.parse(basename)
    assert rec is not None
    assert (rec.system, rec.group, rec.state, rec.year, rec.month) == (
        System.SIM_EXTERIOR,
        "DOREXT",
        None,
        year,
        None,
    )


@pytest.mark.parametrize(
    "basename", ["DOEXT20.dbc", "DOFET20.dbc", "DOREXT2020.dbc", "DOREXT20.dbf", "DOINF20.dbc"]
)
def test_dorext_nao_casa_outros_arquivos_da_pasta(basename):
    assert specs.SIM_OBITOS_EXTERIOR.parse(basename) is None


def test_spec_dorext_esta_na_tupla_e_e_nacional_desde_2013():
    assert specs.get_spec("sim_obitos_exterior") is specs.SIM_OBITOS_EXTERIOR
    assert specs.SIM_OBITOS_EXTERIOR in specs.ALL_SPECS
    assert specs.SIM_OBITOS_EXTERIOR.national and not specs.SIM_OBITOS_EXTERIOR.has_state
    assert specs.SIM_OBITOS_EXTERIOR.min_year == 2013
    assert specs.SIM_OBITOS_EXTERIOR.roots == ("/dissemin/publicos/SIM/CID10/DOFET",)


def test_dorext_registrada_como_fonte_ftp_nacional():
    servico = DownloadService()
    descritor = {d.source: d for d in servico.list_sources()}["sim_obitos_exterior"]
    assert descritor.mode == "datasus ftp"
    parametros = servico.get_source_schema("sim_obitos_exterior")["params"]
    nomes = {p["name"] for p in parametros}
    assert {"start_year", "end_year"} <= nomes
    assert "states" not in nomes and "groups" not in nomes
    assert {p["name"]: p for p in parametros}["start_year"]["minimum"] == 2013
