"""Smoke ao vivo do MI Social (opt-in): ``GUARACI_MDS_SMOKE=1``.

Um ano inteiro do grupo ``bpc`` (12 POSTs pequenos, cerca de 15 s).
"""

from __future__ import annotations

import csv
import os

import pytest

from guaraci.mds import CAMPOS_CHAVE, GRUPOS, MisocialDataSource

pytestmark = pytest.mark.skipif(
    not os.environ.get("GUARACI_MDS_SMOKE"),
    reason="Smoke ao vivo do MI Social; defina GUARACI_MDS_SMOKE=1.",
)


def test_misocial_bpc_2024_live(tmp_path):
    payload = MisocialDataSource(output_path=str(tmp_path)).download(
        start_year=2024, grupos=["bpc"]
    )
    assert payload["failed_count"] == 0
    assert payload["downloaded_count"] == 12
    with open(payload["exported_files"][0], encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == [*CAMPOS_CHAVE, *GRUPOS["bpc"]]
    assert 12 * 5500 < len(rows) - 1 < 12 * 5600
    assert all(len(row[1]) == 6 for row in rows[1:])
    assert {row[0] for row in rows[1:]} == {f"2024{m:02d}" for m in range(1, 13)}
