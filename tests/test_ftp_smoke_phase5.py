"""End-to-end smoke tests for the phase-5 FTP systems against the real server.

Skipped unless ``GUARACI_FTP_SMOKE`` is set to one of ``1/true/yes/on``
(the same flag as ``test_ftp_smoke.py``). Mirrors the SIH smoke for the
eleven systems added in phase 5 — it is the on-demand validation that the
spec paths/regexes match reality and that both decode paths work:

- the national ``.dbc`` path (painel de oncologia), and
- the plain ``.DBF`` path (PNI), which skips ``pyreaddbc``.

Run on Windows PowerShell:

    $env:GUARACI_FTP_SMOKE = "1"; uv run pytest tests/test_ftp_smoke_phase5.py -v
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.datasus.ftp import dbc, specs
from guaraci.datasus.ftp.client import DatasusFtpClient
from guaraci.datasus.ftp.discovery import discover_spec

_SMOKE_FLAGS = {"1", "true", "yes", "on"}
_SMOKE_ENABLED = os.environ.get("GUARACI_FTP_SMOKE", "").strip().lower() in _SMOKE_FLAGS

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
    not _SMOKE_ENABLED,
    reason="Set GUARACI_FTP_SMOKE=1 to enable the live FTP smoke test",
),
]


# (spec, probe year, groups, min files expected) — values from live recon.
_DISCOVERY_PROBES = [
    (specs.SINASC, 2020, None, 25),
    (specs.SISPRENATAL, 2013, None, 100),
    (specs.RESP, 2016, None, 20),
    (specs.PCE, 2005, None, 10),
    (specs.CNES, 2010, ["ST"], 200),
    (specs.SIA, 2024, ["PA"], 100),
    (specs.SISCAN, 2010, ["CC"], 100),
    (specs.PAINEL_ONCOLOGIA, 2015, None, 1),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("spec,year,groups,min_files", _DISCOVERY_PROBES)
async def test_smoke_discovery_matches_server(spec, year, groups, min_files) -> None:  # noqa: ANN001
    """Each spec's paths + filename regex find files on the live server."""
    async with DatasusFtpClient() as client:
        records = await discover_spec(client, spec, years=[year], groups=groups)
    assert len(records) >= min_files, f"{spec.name} {year}: only {len(records)} files"


@pytest.mark.asyncio
async def test_smoke_download_decode_painel_oncologia(tmp_path) -> None:
    """National .dbc path: download + decode the single oncology-panel file."""
    async with DatasusFtpClient() as client:
        records = await discover_spec(client, specs.PAINEL_ONCOLOGIA, years=[2015])
        assert len(records) == 1
        record = records[0]
        assert record.basename.upper() == "POBR2015.DBC"
        assert record.state is None  # national

        dest = tmp_path / record.basename
        await client.download(record.path, dest)
        assert dest.exists() and dest.stat().st_size > 0

    df = dbc.read(dest)
    assert isinstance(df, pl.DataFrame)
    assert df.height > 0


@pytest.mark.asyncio
async def test_smoke_download_decode_pni_dbf(tmp_path) -> None:
    """Plain .DBF path: PNI ships uncompressed DBF; decode must skip pyreaddbc."""
    async with DatasusFtpClient() as client:
        records = await discover_spec(
            client, specs.PNI, years=[2010], groups=["CPNI"], states=["AC"]
        )
        assert len(records) >= 1
        record = next(r for r in records if r.basename.upper().endswith(".DBF"))
        assert record.group == "CPNI"

        dest = tmp_path / record.basename
        await client.download(record.path, dest)
        assert dest.exists() and dest.stat().st_size > 0

    df = dbc.read(dest)  # .DBF -> dbfread directly, no dbc2dbf
    assert isinstance(df, pl.DataFrame)
    assert df.height > 0


# --- SINAN ampliado e SIM fetal (conferido em 2026-10-19) --------------------


@pytest.mark.asyncio
async def test_smoke_sinan_prelim_only_and_new_finais_and_dofet(tmp_path) -> None:
    """Tres arquivos pequenos: HIVE 2024 (so em PRELIM), PEST 2024 (FINAIS novo) e DOFET."""
    from guaraci.datasus.ftp.discovery import discover_sinan

    async with DatasusFtpClient() as client:
        sinan = await discover_sinan(
            client, years=[2024], groups=["HIVE", "PEST"], fetch_sizes=False
        )
        by_group = {r.group: r for r in sinan}
        assert by_group["HIVE"].preliminary is True  # existe apenas em PRELIM
        assert by_group["PEST"].preliminary is False  # FINAIS
        assert len(sinan) == 2  # nenhum ano duplicado

        fetal = await discover_spec(client, specs.SIM_OBITOS_FETAIS, years=[2020])
        assert len(fetal) == 1
        assert fetal[0].state is None and fetal[0].group == "DOFET"

        paths = []
        for record in (by_group["HIVE"], by_group["PEST"], fetal[0]):
            dest = tmp_path / record.basename
            await client.download(record.path, dest)
            assert dest.exists() and dest.stat().st_size > 0
            paths.append(dest)

    # Caminho real de producao (streaming); dbc.read tropeca em datas '********'.
    frames = []
    for dest in paths:
        out = dest.with_suffix(".parquet")
        dbc.decode_to_parquet(dest, out)
        frames.append(pl.read_parquet(out))
    assert all(df.height > 0 for df in frames)
    assert "CAUSABAS" in frames[2].columns
