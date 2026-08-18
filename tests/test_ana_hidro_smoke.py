"""Opt-in live smoke test for the ANA HidroWebService connector.

Disabled by default; set ``GUARACI_ANA_SMOKE=1`` to enable, and additionally
skips (with a clear reason) unless ``GUARACI_ANA_ID``/``GUARACI_ANA_SENHA``
are present in the environment. As of writing, the operator's e-mail
registration with ANA (required to obtain those credentials, per the
HidroWebService manual) was still pending, so this test has never been
exercised against a live payload — see the module docstrings in
``guaraci/ana/client.py`` and ``guaraci/ana/hidro.py`` for exactly what was,
and was not, verifiable via the public OpenAPI document alone.

Once credentials exist, run with:
    GUARACI_ANA_SMOKE=1 GUARACI_ANA_ID=... GUARACI_ANA_SENHA=... pytest tests/test_ana_hidro_smoke.py
and inspect the resulting DataFrame columns before relying on any field name
downstream (the response schema is not published).
"""

from __future__ import annotations

import os

import pytest

from guaraci.ana.hidro import AnaHidroDataSource

SMOKE = os.environ.get("GUARACI_ANA_SMOKE") == "1"
HAS_CREDENTIALS = bool(os.environ.get("GUARACI_ANA_ID")) and bool(
    os.environ.get("GUARACI_ANA_SENHA")
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE,
        reason="Set GUARACI_ANA_SMOKE=1 to enable the live ANA HidroWebService smoke test",
    ),
    pytest.mark.skipif(
        SMOKE and not HAS_CREDENTIALS,
        reason=(
            "GUARACI_ANA_SMOKE=1 but GUARACI_ANA_ID/GUARACI_ANA_SENHA are not "
            "set — the operator's ANA e-mail registration is pending."
        ),
    ),
]


def test_live_single_station_short_window(tmp_path):
    ds = AnaHidroDataSource(output_path=str(tmp_path))
    # Station 15400000 (Rio Amazonas, historically well-known ANA station) is
    # used only as a plausible placeholder; swap for a confirmed active
    # telemetric station code once credentials are available.
    payload = ds.download(
        station_ids=["15400000"],
        start_date="2024-01-01",
        end_date="2024-01-05",
        variable="chuvas",
        detail="adotada",
    )
    assert payload["documents_found"] >= 0
    df = ds.load_dataframe()
    assert "station_id" in df.columns
