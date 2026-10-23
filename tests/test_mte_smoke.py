"""Smoke opt-in do MTE (FTP real); ``GUARACI_MTE_SMOKE=1`` liga.

Baixa só o menor arquivo de cada família: o CAGEDEXC do último mês (cerca de
140 KB) e o ``RAIS_VINC_PUB_NI`` de 2023 (54 KB). Exige o 7-Zip no PATH ou o py7zr.
"""

from __future__ import annotations

import os
import re

import polars as pl
import pytest

from guaraci.mte import (
    FtpLister,
    caged_datasource_for,
    find_binary,
    rais_datasource_for,
)
from guaraci.mte.pdet import FTP_ROOT

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_MTE_SMOKE") != "1",
        reason="Set GUARACI_MTE_SMOKE=1 to enable the live MTE smoke test",
    ),
]


def _cpf_valido(digits: str) -> bool:
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(d) * w for d, w in zip(digits[:size], range(size + 1, 1, -1)))
        if int(digits[size]) != (total * 10 % 11) % 10:
            return False
    return True


def test_live_listagem_de_anos_e_meses() -> None:
    lister = FtpLister()
    assert "2020" in lister.names(f"{FTP_ROOT}/NOVO CAGED")
    assert "202001" in lister.names(f"{FTP_ROOT}/NOVO CAGED/2020")
    assert "RAIS_ESTAB_PUB.7z" in lister.names(f"{FTP_ROOT}/RAIS/2023")


def test_live_caged_exclusoes_ultimo_mes(tmp_path) -> None:
    if find_binary() is None:
        pytest.importorskip("py7zr")
    payload = caged_datasource_for("mte_novo_caged_exclusoes")(output_path=str(tmp_path)).download(
        output_dir=str(tmp_path), output_format="csv"
    )
    assert payload["failed_count"] == 0 and len(payload["exported_files"]) == 1
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False, separator=",")
    assert frame.width == 30
    assert {"competênciamov", "competênciaexc", "indicadordeexclusão"} <= set(frame.columns)
    assert payload["export_warning"] is None
    cpfs = 0
    for row in frame.head(5000).iter_rows():
        for value in row:
            if value and re.fullmatch(r"\d{11}", value) and _cpf_valido(value):
                cpfs += 1
    assert cpfs == 0


def test_live_rais_vinculos_regiao_ni_2023(tmp_path) -> None:
    if find_binary() is None:
        pytest.importorskip("py7zr")
    payload = rais_datasource_for("mte_rais_vinculos")(output_path=str(tmp_path)).download(
        output_dir=str(tmp_path), output_format="csv", anos=[2023], regioes=["NI"]
    )
    assert payload["failed_count"] == 0 and len(payload["exported_files"]) == 1
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.width == 62
    assert frame.columns[7] == "CBO 2002 Ocupação - Código"
    assert payload["export_warning"] is None
