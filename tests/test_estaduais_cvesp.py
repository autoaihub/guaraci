"""Testes offline do TabNet do CVE-SP (formulário de deftohtm.exe e POST em tabcgi.exe)."""

from __future__ import annotations

import csv
from urllib.parse import parse_qsl

import pytest

from guaraci.estaduais.cvesp import CVESP_SPECS, cvesp_datasource_for
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import estaduais as estaduais_sources

# Formulário reduzido do .def real: a ACTION aponta para o tabcgi.exe na raiz do host.
FORM = """<html><FORM ACTION="/tabcgi.exe?cvetab/defs/crt/sifilisnet.def" METHOD=POST>
<SELECT NAME="Linha" ID="L" SIZE=4 >
<OPTION  VALUE="Ano_da_Notific">Ano da Notific
<OPTION  VALUE="Mun_Resid_SP">Mun Resid SP
</SELECT>
<SELECT NAME="Coluna" ID="C" SIZE=4 >
<OPTION SELECTED VALUE="--N&atilde;o-Ativa--">N&atilde;o ativa
<OPTION  VALUE="Ano_da_Notific">Ano da Notific
</SELECT>
<SELECT NAME="Incremento" ID="I" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="Nº_de_Casos">Nº de Casos
</SELECT>
<SELECT NAME="Arquivos" ID="A" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="sifcon25.dbf">2025
</SELECT>
<SELECT NAME="SAno_da_Notific" ID="S1" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="TODAS_AS_CATEGORIAS__">Todas as categorias
</SELECT>
<INPUT TYPE="radio" NAME="formato" ID="F" VALUE="table" CHECKED >
<INPUT TYPE="radio" NAME="formato" ID="F" VALUE="prn" >
</FORM></html>"""

PRN = """<html><PRE>
"Mun Resid SP";"2007";"2008";"2009";"Em Branco";"Total"
"350010 ADAMANTINA";0;1;2;0;3
"355030 SAO PAULO";10;20;30;1;61
"350000 MUNICIPIO IGNORADO";0;0;1;0;1
"Total";10;21;33;1;65
&
</PRE></html>"""


class FakeTabnet:
    def __init__(self, page: str = PRN) -> None:
        self.page = page
        self.calls = []

    def text(self, url, body=None):
        self.calls.append((url, body))
        return FORM if body is None else self.page


def _run(tmp_path, key="cvesp_sifilis_congenita", **kwargs):
    spec = CVESP_SPECS[key]
    fake = FakeTabnet()
    source = cvesp_datasource_for(spec)(str(tmp_path), client=fake)
    payload = source.download(output_dir=str(tmp_path), **kwargs)
    return fake, payload


def test_post_goes_to_action_of_the_form_not_to_deftohtm(tmp_path):
    fake, _ = _run(tmp_path, start_year=2007, end_year=2009)
    get_url, get_body = fake.calls[0]
    post_url, post_body = fake.calls[1]
    assert get_body is None
    assert get_url == "https://tabnetcve.saude.sp.gov.br/deftohtm.exe?cvetab/defs/crt/sifilisnet.def"
    assert post_url == "https://tabnetcve.saude.sp.gov.br/tabcgi.exe?cvetab/defs/crt/sifilisnet.def"
    fields = parse_qsl(post_body.decode("ascii"), encoding="latin-1")
    assert ("Linha", "Mun_Resid_SP") in fields
    assert ("Coluna", "Ano_da_Notific") in fields
    assert ("Incremento", "Nº_de_Casos") in fields
    assert ("Arquivos", "sifcon25.dbf") in fields
    assert ("formato", "prn") in fields
    assert ("SAno_da_Notific", "TODAS_AS_CATEGORIAS__") in fields


def test_matrix_becomes_long_csv_without_total_and_filters_years(tmp_path):
    _, payload = _run(tmp_path, start_year=2008, end_year=2009)
    rows = list(csv.reader(open(payload["exported_files"][0], encoding="utf-8")))
    assert rows[0] == ["cod_ibge", "municipio", "ano", "Nº de Casos"]
    assert rows[1:] == [
        ["350010", "ADAMANTINA", "2008", "1"],
        ["350010", "ADAMANTINA", "2009", "2"],
        ["355030", "SAO PAULO", "2008", "20"],
        ["355030", "SAO PAULO", "2009", "30"],
        ["350000", "MUNICIPIO IGNORADO", "2008", "0"],
        ["350000", "MUNICIPIO IGNORADO", "2009", "1"],
    ]
    assert payload["rows"] == 6
    assert "Em Branco" in payload["export_warning"]
    assert "Total" not in payload["export_warning"]


def test_year_after_series_warns_and_year_below_floor_fails(tmp_path):
    _, payload = _run(tmp_path, start_year=2009, end_year=2030)
    assert payload["rows"] == 3
    assert "acima de 2009" in payload["export_warning"]
    with pytest.raises(ValueError):
        _run(tmp_path, start_year=1999)


def test_empty_range_writes_no_file(tmp_path):
    _, payload = _run(tmp_path, start_year=2015)
    assert payload["exported_files"] == []
    assert payload["downloaded_count"] == 0
    assert "Nenhum ano" in payload["export_warning"]


def test_parquet_export(tmp_path):
    pl = pytest.importorskip("polars")
    _, payload = _run(tmp_path, start_year=2007, output_format="parquet")
    frame = pl.read_parquet(payload["exported_files"][0])
    assert frame.columns == ["cod_ibge", "municipio", "ano", "Nº de Casos"]
    assert frame.height == 3


@pytest.mark.parametrize("key", list(CVESP_SPECS))
def test_every_key_answers_get_source_schema(key):
    service = DownloadService(sources=estaduais_sources.build_sources())
    names = {p["name"] for p in service.get_source_schema(key)["params"]}
    assert {"start_year", "end_year", "output_format"} <= names
