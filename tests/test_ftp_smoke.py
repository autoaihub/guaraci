"""End-to-end smoke test against the real DATASUS FTP server.

Skipped unless ``GUARACI_FTP_SMOKE`` is set to one of ``1/true/yes``.

This is the exit criterion of phase 1 in
``docs/PLANO_DATASUS_FTP_DIRETO.md``: download one canonical SIH file
(``RDSP2401.dbc``) via the new FTP layer and confirm it decodes into a
non-empty Polars DataFrame.

Run on Windows PowerShell:

    $env:GUARACI_FTP_SMOKE = "1"; uv run pytest tests/test_ftp_smoke.py -v
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.datasus.ftp import (
    DatasusFtpClient,
    SIH_CURRENT_PATH,
    dbc,
    discover_sih,
)

_SMOKE_FLAGS = {"1", "true", "yes", "on"}
_SMOKE_ENABLED = os.environ.get("GUARACI_FTP_SMOKE", "").strip().lower() in _SMOKE_FLAGS

pytestmark = pytest.mark.skipif(
    not _SMOKE_ENABLED,
    reason="Set GUARACI_FTP_SMOKE=1 to enable the live FTP smoke test",
)


@pytest.mark.asyncio
async def test_smoke_connect_list_size() -> None:
    """Bare-minimum connectivity probe — replicates the discover_sih_rd script."""
    async with DatasusFtpClient() as client:
        entries = await client.list_dir(SIH_CURRENT_PATH)
        assert len(entries) > 1000

        target = next(
            (e for e in entries if e.name.upper() == "RDSP2401.DBC"),
            None,
        )
        assert target is not None, "RDSP2401.dbc must exist in current SIH dir"

        size = await client.size(f"{SIH_CURRENT_PATH}/{target.name}")
        assert size > 1_000_000  # > 1 MB


@pytest.mark.asyncio
async def test_smoke_download_and_decode_rdsp2401(tmp_path) -> None:
    """Exit criterion: download → decode produces a non-empty Polars DataFrame."""
    async with DatasusFtpClient() as client:
        results = await discover_sih(
            client,
            years=[2024],
            groups=["RD"],
            states=["SP"],
            months=[1],
        )
        assert len(results) == 1
        record = results[0]
        assert record.basename.upper() == "RDSP2401.DBC"

        dest = tmp_path / record.basename
        await client.download(record.path, dest)
        assert dest.exists()
        assert dest.stat().st_size > 1_000_000

    df = dbc.read(dest)
    assert isinstance(df, pl.DataFrame)
    assert df.height > 0
    assert any("UF" in column.upper() for column in df.columns)
