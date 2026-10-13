"""Smoke ao vivo do SIOPS (opt-in): ``GUARACI_SIOPS_SMOKE=1``.

Um POST por fonte: estados 2002 (o menor) e municípios 2024.
"""

from __future__ import annotations

import csv
import os

import pytest

from guaraci.siops import (
    SiopsIndicadoresEstadosDataSource,
    SiopsIndicadoresMunicipiosDataSource,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("GUARACI_SIOPS_SMOKE"),
    reason="Smoke ao vivo do SIOPS; defina GUARACI_SIOPS_SMOKE=1.",
)


def _rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_siops_estados_live(tmp_path):
    payload = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path)).download(
        start_year=2002
    )
    assert payload["failed_count"] == 0
    rows = _rows(payload["exported_files"][0])
    assert rows[0][:4] == ["ano", "cod_uf", "uf", "nome_uf"]
    assert len(rows[0]) == 4 + 31
    assert 20 <= len(rows) - 1 <= 27
    assert all(row[1] for row in rows[1:])


def test_siops_municipios_live(tmp_path):
    payload = SiopsIndicadoresMunicipiosDataSource(output_path=str(tmp_path)).download(
        start_year=2024
    )
    assert payload["failed_count"] == 0
    rows = _rows(payload["exported_files"][0])
    assert rows[0][:3] == ["ano", "cod_ibge", "municipio"]
    assert len(rows[0]) == 3 + 31
    assert len(rows) - 1 > 5000
    assert all(len(row[1]) == 6 for row in rows[1:])
