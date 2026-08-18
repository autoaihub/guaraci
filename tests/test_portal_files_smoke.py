"""Opt-in live smoke test for the portal-files transport (real HTTP).

Disabled by default; set ``GUARACI_PORTAL_SMOKE=1`` to run. Exercises the
full discover -> download -> idempotency loop against the real
dadosabertos.saude.gov.br portal, always downloading the smallest possible
recorte (rule 5 in docs/PLANO_NOVAS_FONTES.md §0): SRAG's frozen 2019 year
(picks parquet automatically, ~3 MB) and SISAGUA's populacao_abastecida
package (no year segmentation; smallest available format, tens of MB).
"""
from __future__ import annotations

import os

import pytest

from guaraci.opendatasus.portal_files import PortalFileDataSource

SMOKE = os.environ.get("GUARACI_PORTAL_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_PORTAL_SMOKE=1 to enable the live portal smoke test"
    ),
]


def test_live_discover_srag_2019_lists_resources_without_downloading(tmp_path):
    ds = PortalFileDataSource(output_path=str(tmp_path))
    result = ds.discover(dataset="srag_arquivos", start_year=2019, end_year=2019)
    assert result["documents_found"] >= 1
    assert not list(tmp_path.iterdir())  # discover never writes files
    formats = {item["format"] for item in result["resources"]}
    assert "parquet" in formats


def test_live_download_srag_2019_is_small_and_idempotent(tmp_path):
    ds = PortalFileDataSource(output_path=str(tmp_path))
    first = ds.download(dataset="srag_arquivos", start_year=2019, end_year=2019)
    assert first["downloaded_count"] == 1
    materialized = first["materialized_paths"][0]
    assert materialized.endswith(".parquet")  # format_priority prefers parquet

    second = ds.download(dataset="srag_arquivos", start_year=2019, end_year=2019)
    assert second["downloaded_count"] == 0
    assert second["skipped_count"] == 1


def test_live_discover_sisagua_populacao_abastecida_excludes_dictionary(tmp_path):
    ds = PortalFileDataSource(output_path=str(tmp_path))
    result = ds.discover(dataset="sisagua_populacao_abastecida")
    assert result["documents_found"] >= 1
    names = " ".join(item["name"].lower() for item in result["resources"])
    assert "dicion" not in names
