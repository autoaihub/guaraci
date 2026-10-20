"""Smoke ao vivo do dado preliminar (SIM, SIM fetal, SINASC) e do Chagas crônico.

Pulado sem ``GUARACI_FTP_SMOKE`` (mesma variável de ``test_ftp_smoke.py``).
Baixa só recortes pequenos: AC em 2025 no SIM e no SINASC, o DOFET de 2026
e o DCCRBR de 2024, alguns MB no total.

    $env:GUARACI_FTP_SMOKE = "1"; uv run pytest tests/test_datasus_prelim_smoke.py -v
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.datasus.ftp import generic_backend, sim_backend, specs

_SMOKE_ENABLED = os.environ.get("GUARACI_FTP_SMOKE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not _SMOKE_ENABLED,
        reason="Set GUARACI_FTP_SMOKE=1 to enable the live FTP smoke test",
    ),
]


def _rows(paths) -> int:
    return sum(pl.scan_parquet(p).select(pl.len()).collect().item() for p in paths)


def test_smoke_sim_prelim_ac_2025(tmp_path) -> None:
    result = sim_backend.download_sim(
        years=[2025], groups=["CID10"], states=["AC"], cache_dir=tmp_path
    )
    assert result["preliminary_files"] == ["DOAC2025.dbc"]
    assert _rows(result["paths_by_group"]["CID10"]) > 0


@pytest.mark.parametrize(
    "spec,year,states,expected",
    [
        (specs.SINASC, 2025, ["AC"], ["DNAC2025.dbc"]),
        (specs.SIM_OBITOS_FETAIS, 2026, None, ["DOFET26.dbc"]),
        (specs.ESUS_NOTIFICA_CHAGAS_CRONICA, 2024, None, ["DCCRBR24.dbc"]),
    ],
)
def test_smoke_generic_prelim(tmp_path, spec, year, states, expected) -> None:  # noqa: ANN001
    result = generic_backend.download(
        spec, years=[year], states=states, cache_dir=tmp_path
    )
    assert result["preliminary_files"] == expected
    paths = [p for items in result["paths_by_group"].values() for p in items]
    assert _rows(paths) > 0
