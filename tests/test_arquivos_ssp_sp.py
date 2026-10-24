"""SSP-SP, dados criminais: xlsx anual com aba de dicionário e uma aba por semestre, sem rede."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from guaraci.arquivos import datasource_for_spec, seguranca
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import arquivos as sources_arquivos
from tests.test_arquivos_ext_a import _workbook
from tests.test_arquivos_http import _Client


def test_spec_congelada_de_2022_a_2026() -> None:
    spec = seguranca.SSP_SP_DADOS_CRIMINAIS
    assert [r.code for r in spec.resources] == ["2022", "2023", "2024", "2025", "2026"]
    assert spec.resources[0].url.endswith("/spDados/SPDadosCriminais_2022.xlsx")
    assert spec.file_format == "xlsx" and spec.period_required is True


def test_exporta_dicionario_e_um_semestre_por_aba(tmp_path: Path) -> None:
    spec = seguranca.SSP_SP_DADOS_CRIMINAIS
    url = spec.resources[3].url
    path = tmp_path / "ssp.xlsx"
    _workbook(
        path,
        {
            "CAMPOS_DA_TABELA_SPDADOS": [["Campos", "Descrição"], ["NUM_BO", "Número do BO"]],
            "JAN-JUN_2025": [["NUM_BO", "CD_IBGE"], ["AA1", "3550308"]],
            "JUL-DEZ_2025": [["NUM_BO", "CD_IBGE"], ["AB2", "3509502"]],
        },
    )
    out = tmp_path / "out"
    payload = datasource_for_spec(spec)(
        output_path=str(out), client=_Client({url: path.read_bytes()})
    ).download(output_dir=str(out), output_format="csv", anos=[2025])
    names = sorted(Path(p).name for p in payload["exported_files"])
    assert names == [
        "ssp_sp_dados_criminais_2025_CAMPOS_DA_TABELA_SPDADOS.csv",
        "ssp_sp_dados_criminais_2025_JAN-JUN_2025.csv",
        "ssp_sp_dados_criminais_2025_JUL-DEZ_2025.csv",
    ]
    frame = pl.read_csv(out / names[1], infer_schema=False)
    assert frame.rows() == [("AA1", "3550308")]
    assert not list(out.glob("*.tmp.*"))


def test_chave_responde_no_schema() -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema(
        "ssp_sp_dados_criminais"
    )
    params = {p["name"]: p for p in schema["params"]}
    assert params["anos"]["required"] is True
