"""PNI e SISVAN por arquivo (bucket ckan.saude.gov.br), sem rede.

Cobrem o recorte por ano e mês, a obrigação de pedir ``anos`` (cada zip tem GB), o
latin-1 com ``;`` e aspas, e o registro das fontes e dos parâmetros.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from guaraci.arquivos import HTTP_FILES, HttpFileDataSource
from guaraci.services.downloads import DownloadService
from tests.test_arquivos_http import _Client, _source, _zip

PNI = "pni_doses_aplicadas_arquivos"
SISVAN = "sisvan_estado_nutricional_arquivos"

_PNI_CSV = (
    "co_documento;co_paciente;ds_tipo_dose;dt_vacina;no_municipio_paciente\r\n"
    "abc-i0b0;h1;Única;2024-01-11;SÃO PAULO\r\n"
).encode("cp1252")
_SISVAN_CSV = (
    '"CO_ACOMPANHAMENTO";"CO_PESSOA_SISVAN";NU_IDADE_ANO;"DS_FASE_VIDA";"NU_PESO"\r\n'
    '"A1";"P1";37;"ADULTO";"51,5"\r\n'
).encode("cp1252")


def _payloads(key: str, body: bytes) -> dict:
    return {r.url: _zip({"dado.csv": body}) for r in HTTP_FILES[key].resources}


def test_pni_registra_um_zip_por_mes_de_2020_a_2026() -> None:
    resources = HTTP_FILES[PNI].resources
    assert len(resources) == 7 * 12
    assert resources[0].code == "2020_01"
    assert resources[0].url == (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2020_csv.zip"
    )
    assert resources[-1].url.endswith("PNI/csv/vacinacao_dez_2026_csv.zip")
    assert len({r.code for r in resources}) == len(resources)


def test_sisvan_registra_um_zip_por_ano_de_2008_a_2023() -> None:
    resources = HTTP_FILES[SISVAN].resources
    assert [r.code for r in resources] == [str(a) for a in range(2008, 2024)]
    assert resources[0].url.endswith("SISVAN/estado_nutricional/sisvan_estado_nutricional_2008.zip")


def test_pni_recorta_por_ano_e_mes_e_nomeia_a_saida(tmp_path: Path) -> None:
    client = _Client(_payloads(PNI, _PNI_CSV))
    payload = _source(tmp_path, PNI, client).download(
        output_dir=str(tmp_path), output_format="csv", anos=[2024], meses=["01", 3]
    )
    assert payload["documents_found"] == 2
    assert client.downloads == 2
    assert [Path(p).name for p in payload["exported_files"]] == [
        f"{PNI}_2024_01.csv",
        f"{PNI}_2024_03.csv",
    ]
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns[:2] == ["co_documento", "co_paciente"]
    assert frame["ds_tipo_dose"][0] == "Única"
    assert frame["no_municipio_paciente"][0] == "SÃO PAULO"


def test_pni_sem_meses_baixa_o_ano_inteiro(tmp_path: Path) -> None:
    client = _Client(_payloads(PNI, _PNI_CSV))
    payload = _source(tmp_path, PNI, client).download(output_dir=str(tmp_path), anos=["2021"])
    assert payload["documents_found"] == 12
    assert client.downloads == 12


def test_sisvan_exporta_o_ano_pedido_com_aspas_e_latin1(tmp_path: Path) -> None:
    client = _Client(_payloads(SISVAN, _SISVAN_CSV))
    payload = _source(tmp_path, SISVAN, client).download(
        output_dir=str(tmp_path), output_format="csv", anos=[2023]
    )
    assert payload["documents_found"] == 1
    (exported,) = payload["exported_files"]
    assert Path(exported).name == f"{SISVAN}_2023.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.columns == [
        "CO_ACOMPANHAMENTO", "CO_PESSOA_SISVAN", "NU_IDADE_ANO", "DS_FASE_VIDA", "NU_PESO",
    ]
    assert frame["NU_PESO"][0] == "51,5"


def test_sem_anos_pede_o_recorte_em_vez_de_baixar_tudo(tmp_path: Path) -> None:
    for key in (PNI, SISVAN):
        client = _Client(_payloads(key, _PNI_CSV))
        with pytest.raises(ValueError, match="anos"):
            _source(tmp_path, key, client).download(output_dir=str(tmp_path))
        assert client.downloads == 0


def test_ano_fora_do_acervo_e_rejeitado(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown anos"):
        _source(tmp_path, SISVAN, _Client({})).download(output_dir=str(tmp_path), anos=[2024])
    with pytest.raises(ValueError, match="Unknown anos"):
        _source(tmp_path, PNI, _Client({})).download(output_dir=str(tmp_path), anos=[2019])


def test_mes_ainda_nao_publicado_vira_aviso(tmp_path: Path) -> None:
    payloads = _payloads(PNI, _PNI_CSV)
    client = _Client(payloads, fail=("vacinacao_dez_2026_csv.zip",))
    payload = HttpFileDataSource(output_path=str(tmp_path), dataset=PNI, client=client).download(
        output_dir=str(tmp_path), output_format="csv", anos=[2026], meses=["11", "12"]
    )
    assert payload["failed_count"] == 1
    assert len(payload["exported_files"]) == 1
    assert "2026_12" in payload["export_warning"]


def test_registro_expoe_anos_e_meses_com_valores_permitidos() -> None:
    service = DownloadService()
    pni = service.get_source_schema(PNI)
    names = {p["name"]: p for p in pni["params"]}
    assert pni["mode"] == "demas s3 files"
    assert names["anos"]["required"] is True
    assert names["anos"]["allowed_values"] == [str(a) for a in range(2020, 2027)]
    assert names["meses"]["allowed_values"][0] == "01"
    sisvan = {p["name"] for p in service.get_source_schema(SISVAN)["params"]}
    assert "anos" in sisvan and "meses" not in sisvan
    service.validate_source_params(PNI, {"anos": ["2024"], "meses": ["01"]})
    with pytest.raises(ValueError):
        service.validate_source_params(PNI, {"anos": ["2019"]})
