"""Smoke ao vivo opt-in do SIAPS (API DEMAS).

Desligado por padrao; ``GUARACI_SIAPS_SMOKE=1`` liga. Baixa uma unica pagina
de 10 linhas do cadastro individual na competencia 202606.
"""
from __future__ import annotations

import csv
import os

import pytest

from guaraci.services.downloads import DownloadService

SMOKE = os.environ.get("GUARACI_SIAPS_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_SIAPS_SMOKE=1 to enable the live SIAPS smoke test"
    ),
]


def test_live_cadastro_individual_uma_pagina(tmp_path):
    result = DownloadService().run(
        "atencao_primaria_siaps_cadastro_individual",
        competencia_siaps="202606",
        max_pages=1,
        batch_size=10,
        output_format="csv",
        output_dir=str(tmp_path),
    )
    assert result.exported_files
    with open(result.exported_files[0], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 10
    assert {"competencia_siaps", "qtd_pessoas_cadastradas"} <= set(rows[0])
    assert "co_uf_ibge" not in rows[0]
