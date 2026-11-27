"""Testes offline das fontes SIAB e HIPERDIA (TabNet mensal) e do parser de ``<OPTION>``."""

from __future__ import annotations

import csv
from urllib.parse import parse_qsl

import pytest

from guaraci.services.sources import tabnet_saude
from guaraci.tabnet import TabnetNoTableError, parse_form
from guaraci.tabnet.mensal import parse_ufs, split_municipio
from guaraci.tabnet.saude import HiperdiaCadastroDataSource, SiabSituacaoSaudeDataSource

FORM_SIAB = """<html><FORM ACTION="/cgi/tabcgi.exe?siab/cnv/SIABSbr.def" METHOD=POST>
<SELECT NAME="Linha" SIZE=4>
<OPTION VALUE="Município">Munic&iacute;pio
<OPTION VALUE="Ano">Ano
</SELECT>
<SELECT NAME="Coluna" SIZE=4>
<OPTION SELECTED VALUE="--Não-Ativa--">N&atilde;o ativa
</SELECT>
<SELECT NAME="Incremento" SIZE=4 MULTIPLE>
<OPTION VALUE="Nascidos_Vivos">Nascidos Vivos
<OPTION VALUE="Mulheres_>60anos">Mulheres >60anos
<OPTION VALUE="Mulheres_<1ano">Mulheres <1ano
</SELECT>
<SELECT NAME="Arquivos" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="brs1512.dbf">Dez/2015
<OPTION VALUE="brs1511.dbf">Nov/2015
<OPTION VALUE="brs1412.dbf">Dez/2014
</SELECT>
<SELECT NAME="SMunicípio" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="TODAS_AS_CATEGORIAS__">Todas as categorias
<OPTION VALUE="1">MUNICIPIO IGNORADO - RO
<OPTION VALUE="2">110001 ALTA FLORESTA D'OESTE
<OPTION VALUE="3">410010 ABATIA
<OPTION VALUE="4">MUNICIPIO IGNORADO - PR
</SELECT>
<INPUT TYPE="radio" NAME="formato" VALUE="prn">
</FORM></html>"""

HEADER = '"Município";"Nascidos Vivos";"Mulheres >60anos";"Mulheres &lt;1ano"'


def prn(*rows: str, header: str = HEADER) -> str:
    return "<PRE>\n" + header + "\n" + "\n".join(rows) + '\n"Total";1;1;1\n&\n</PRE>'


class FakeTabnet:
    def __init__(self, form: str, pages=None) -> None:
        self.form = form
        self.pages = pages or {}
        self.posts = []

    def text(self, url, body=None):
        if body is None:
            return self.form
        fields = parse_qsl(body.decode("ascii"), encoding="latin-1")
        self.posts.append((url, fields))
        page = self.pages[dict(fields)["Arquivos"]]
        return page(fields) if callable(page) else page


def _rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_form_option_with_gt_in_value_and_lt_in_label():
    form = parse_form(FORM_SIAB)
    assert form.values("Incremento") == ["Nascidos_Vivos", "Mulheres_>60anos", "Mulheres_<1ano"]
    assert [o.label for o in form.selects["Incremento"]][1:] == ["Mulheres >60anos", "Mulheres <1ano"]
    assert form.periods() == {(2015, 12): "brs1512.dbf", (2015, 11): "brs1511.dbf", (2014, 12): "brs1412.dbf"}


def test_split_municipio_and_ufs():
    assert split_municipio("410010 ABATIA") == ("PR", "410010", "ABATIA")
    assert split_municipio("MUNICIPIO IGNORADO - RO") == ("RO", "", "MUNICIPIO IGNORADO - RO")
    assert parse_ufs("pr, sc") == ["PR", "SC"] and parse_ufs(None) == []
    with pytest.raises(ValueError):
        parse_ufs("XX")


def test_siab_downloads_each_month_with_uf_filter(tmp_path):
    fake = FakeTabnet(FORM_SIAB, {
        "brs1512.dbf": lambda f: prn('"ABATIA";1;2;3', header=HEADER) if dict(f)["Linha"] == "Ano"
        else prn('"410010 ABATIA";6;-;3', '"MUNICIPIO IGNORADO - PR";1;1;1'),
        "brs1511.dbf": prn('"410010 ABATIA";5;1;...'),
    })
    result = SiabSituacaoSaudeDataSource(output_path=str(tmp_path), client=fake).download(
        start_year=2015, uf="PR"
    )
    rows = _rows(result["exported_files"][0])
    assert rows[0] == [
        "ano", "mes", "uf", "cod_ibge", "municipio",
        "Nascidos Vivos", "Mulheres >60anos", "Mulheres <1ano",
    ]
    assert rows[1:] == [
        ["2015", "11", "PR", "410010", "ABATIA", "5", "1", "..."],
        ["2015", "12", "PR", "410010", "ABATIA", "6", "-", "3"],
        ["2015", "12", "PR", "", "MUNICIPIO IGNORADO - PR", "1", "1", "1"],
    ]
    assert result["downloaded_count"] == 2 and result["failed_count"] == 0
    # Só as categorias de município do PR entram no filtro; a sonda não filtra.
    real = [f for _, f in fake.posts if dict(f)["Linha"] == "Município"][0]
    assert [v for k, v in real if k == "SMunicípio"] == ["3", "4"]
    assert ("Incremento", "Mulheres_>60anos") in real


def test_siab_rejects_year_before_series_and_flags_unpublished(tmp_path):
    ds = SiabSituacaoSaudeDataSource(output_path=str(tmp_path), client=FakeTabnet(FORM_SIAB))
    with pytest.raises(ValueError):
        ds.download(start_year=1997)
    result = ds.download(start_year=2016)
    assert result["rows"] == 0 and "posterior" in result["export_warning"]
    assert result["exported_files"] == []


def test_probe_that_refuses_a_measure_stops_with_warning(tmp_path):
    def page(fields):
        d = dict(fields)
        items = [v for k, v in fields if k == "Incremento"]
        if "Mulheres_<1ano" in items:
            return "<html>Campo Incremento nao encontrado em x.dbf</html>"
        header = '"Município";"Nascidos Vivos";"Mulheres >60anos"'
        return prn('"410010 ABATIA";4;2', header=header)

    fake = FakeTabnet(FORM_SIAB, {"brs1512.dbf": page, "brs1511.dbf": page, "brs1412.dbf": page})
    # A sonda do mês mais recente recusa uma medida: a coleta para com aviso claro.
    result = SiabSituacaoSaudeDataSource(output_path=str(tmp_path), client=fake).download(
        start_year=2015
    )
    assert result["failed_count"] == 1 and "recusa" in result["export_warning"]
    with pytest.raises(TabnetNoTableError):
        from guaraci.tabnet import parse_prn
        parse_prn(page([("Incremento", "Mulheres_<1ano")]))


FORM_HD = FORM_SIAB.replace("siab/cnv/SIABSbr.def", "hiperdia/cnv/hdac.def")


def test_hiperdia_uses_one_def_per_uf(tmp_path):
    fake = FakeTabnet(FORM_HD, {
        "brs1512.dbf": prn('"120040 RIO BRANCO";11;2;1'),
        "brs1511.dbf": prn('"120040 RIO BRANCO";9;1;0'),
        "brs1412.dbf": prn('"120040 RIO BRANCO";1;1;1'),
    })
    result = HiperdiaCadastroDataSource(output_path=str(tmp_path), client=fake).download(
        start_year=2014, end_year=2015, uf="AC,AP"
    )
    urls = {u for u, _ in fake.posts}
    assert any("hdac.def" in u for u in urls) and any("hdap.def" in u for u in urls)
    rows = _rows(result["exported_files"][0])
    assert {r[2] for r in rows[1:]} == {"AC"}
    assert len(rows) - 1 == 3 * 2


def test_registered_specs_follow_schema():
    sources = {s.descriptor.source: s for s in tabnet_saude.build_sources()}
    assert set(sources) == {
        "siab_situacao_saude", "siab_producao_marcadores", "siab_cadastro_familiar",
        "siab_saneamento", "hiperdia_cadastro",
    }
    source = sources["hiperdia_cadastro"]
    source.validate_params({"start_year": "2012", "uf": "PR"})
    with pytest.raises(Exception):
        source.validate_params({"start_year": 2012, "inexistente": 1})
