"""Opt-in live smoke test for the bronze orchestrator (real DATASUS FTP).

Disabled by default; set ``GUARACI_FTP_SMOKE=1`` to run. It discovers a single
small SINAN file on the real server, materialises it through the actual
``run_ftp_batch`` path, and asserts a bronze CSV + an ``ok`` ledger row. Keep it
to one small disease (RAIV/ANIM) so it stays a courteous, cheap check.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from guaraci.orchestrator.ledger import STATUS_OK, Ledger
from guaraci.orchestrator.planner import _record_to_unit
from guaraci.orchestrator.model import Kind
from guaraci.orchestrator.runner import run_ftp_batch

SMOKE = os.environ.get("GUARACI_FTP_SMOKE") == "1"
pytestmark = pytest.mark.skipif(
    not SMOKE, reason="Set GUARACI_FTP_SMOKE=1 to enable the live FTP smoke test"
)


def _one_small_sinan_record():
    """Discover one small SINAN file (prefer RAIV/ANIM) on the live server."""
    from guaraci.datasus.ftp.client import DatasusFtpClient
    from guaraci.datasus.ftp.discovery import discover_sinan
    from guaraci.datasus.ftp.orchestration import run_coro

    async def _impl():
        async with DatasusFtpClient() as client:
            for disease in ("RAIV", "ANIM", "ESQU"):
                for year in (2023, 2022, 2021):
                    recs = await discover_sinan(
                        client, years=[year], groups=[disease], fetch_sizes=False
                    )
                    if recs:
                        return recs[0]
            recs = await discover_sinan(client, years=[2022], fetch_sizes=False)
            return recs[0] if recs else None

    return run_coro(_impl())


def test_live_sinan_single_file_to_bronze(tmp_path):
    record = _one_small_sinan_record()
    assert record is not None, "no SINAN files discovered on the live server"

    unit = _record_to_unit("sinan", Kind.FTP_SINAN, record)
    ledger = Ledger(tmp_path / "_ledger.csv")
    rows = run_ftp_batch(
        [unit], bronze_root=tmp_path, run_id="smoke", ts="t", ledger=ledger
    )

    assert len(rows) == 1
    assert rows[0].status == STATUS_OK, rows[0].error
    materialised = Path(rows[0].out_path)
    assert materialised.exists() and materialised.stat().st_size > 0
    # at least a header row lands in the CSV
    assert materialised.read_text(encoding="utf-8", errors="replace").count("\n") >= 1
