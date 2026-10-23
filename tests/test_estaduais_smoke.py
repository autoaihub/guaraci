"""Smoke ao vivo das fontes estaduais (opt-in: GUARACI_ESTADUAIS_SMOKE=1)."""

from __future__ import annotations

import csv
import os

import pytest

from guaraci.estaduais.cvesp import CVESP_SPECS, cvesp_datasource_for
from guaraci.estaduais.rio_iqar import RioIqarDiarioDataSource

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("GUARACI_ESTADUAIS_SMOKE"),
        reason="Defina GUARACI_ESTADUAIS_SMOKE=1 para consultar os servidores reais.",
    ),
]


def _read(path):
    return list(csv.reader(open(path, encoding="utf-8")))


@pytest.mark.parametrize("key", list(CVESP_SPECS))
def test_cvesp_live_last_year(tmp_path, key):
    spec = CVESP_SPECS[key]
    payload = cvesp_datasource_for(spec)(str(tmp_path)).download(
        start_year=2025, output_dir=str(tmp_path)
    )
    rows = _read(payload["exported_files"][0])
    assert rows[0][:3] == ["cod_ibge", "municipio", "ano"]
    assert len(rows) > 300  # só municípios com linha na matriz
    assert {r[2] for r in rows[1:]} == {"2025"}
    assert any(r[0] == "355030" for r in rows[1:])


def test_rio_iqar_live_full_layer(tmp_path):
    payload = RioIqarDiarioDataSource(str(tmp_path)).download(output_dir=str(tmp_path))
    rows = _read(payload["exported_files"][0])
    assert rows[0] == [
        "objectid", "data", "estação", "estacao_nome", "poluente",
        "classificação", "iqar", "codnum",
    ]
    assert len(rows) - 1 == payload["rows"] > 20000
    assert payload["export_warning"] is None
    datas = sorted(r[1] for r in rows[1:] if r[1])
    assert datas[0].startswith("2017") and datas[-1].startswith("2024")
