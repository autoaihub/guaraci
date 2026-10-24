"""Smoke opt-in do CNPJ da Receita (WebDAV real); ``GUARACI_RECEITA_SMOKE=1`` liga.

Lista as pastas por ``PROPFIND`` e baixa só a menor tabela de domínio
(``Motivos.zip``, cerca de 1 KB). Nunca baixa Empresas, Estabelecimentos, Sócios
nem Simples (de dezenas de MB a 2 GB por parte).
"""

from __future__ import annotations

import os
import re

import polars as pl
import pytest

from guaraci.receita import ReceitaWebDavClient, datasource_for

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_RECEITA_SMOKE") != "1",
        reason="Set GUARACI_RECEITA_SMOKE=1 to enable the live Receita smoke test",
    ),
]


def test_propfind_lists_monthly_folders():
    folders = [e.name for e in ReceitaWebDavClient().list("") if e.is_dir]
    assert any(re.fullmatch(r"\d{4}-\d{2}", f) for f in folders)
    assert "2023-05" in folders


def test_smallest_table_exports(tmp_path):
    out = datasource_for("receita_cnpj_tabelas")(str(tmp_path)).download(
        output_format="csv", tabelas=["motivos"]
    )
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.columns == ["codigo", "descricao"]
    assert frame.height > 50
