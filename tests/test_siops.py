"""Testes offline do transporte TabNet e das fontes do SIOPS."""

from __future__ import annotations

import csv
from urllib.parse import parse_qsl

import pytest

from guaraci.tabnet import (
    TabnetClient,
    TabnetClientError,
    parse_form,
    parse_prn,
    parse_raw_response,
)
from guaraci.siops import (
    SiopsIndicadoresEstadosDataSource,
    SiopsIndicadoresMunicipiosDataSource,
)

# Trecho do formulário real (TabNet Win32 3.0), com OPTION sem fechamento e
# um valor com tabulação, como no SIOPS.
FORM_MUN = """<html><FORM ACTION="/CGI/tabcgi.exe?SIOPS/serhist/municipio/mIndicadores.def" METHOD=POST>
<SELECT NAME="Linha" ID="L" SIZE=4 >
<OPTION  VALUE="Ano">Ano
<OPTION  VALUE="Munic-BR">Munic-BR
</SELECT>
<SELECT NAME="Coluna" ID="C" SIZE=4 >
<OPTION SELECTED VALUE="--Não-Ativa--">N&atilde;o ativa
<OPTION  VALUE="Ano">Ano
</SELECT>
<SELECT NAME="Incremento" ID="I" SIZE=4 MULTIPLE>
<OPTION  VALUE="População">Popula&ccedil;&atilde;o
<OPTION  VALUE="2.10\tSUBFUNÇÕES_ADMINISTRATIVAS">2.10\tSUBFUN&Ccedil;&Otilde;ES ADMINISTRATIVAS
<OPTION  VALUE="D.Total_Saúde">D.Total Sa&uacute;de
</SELECT>
<SELECT NAME="Arquivos" ID="A" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="indmun24.dbf">2024
<OPTION  VALUE="indmun23.dbf">2023
</SELECT>
<SELECT NAME="SUF" ID="S1" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="TODAS_AS_CATEGORIAS__">Todas as categorias
<OPTION  VALUE="1">Rond&ocirc;nia
</SELECT>
<SELECT NAME="SMunic-BR" ID="S3" SIZE=4 MULTIPLE>
<OPTION SELECTED VALUE="TODAS_AS_CATEGORIAS__">Todas as categorias
<OPTION  VALUE="1">110001 Alta Floresta D'Oeste
</SELECT>
<INPUT TYPE="radio" NAME="formato" ID="F" VALUE="table" CHECKED >
<INPUT TYPE="radio" NAME="formato" ID="F" VALUE="prn" >
</FORM></html>"""

PRN_MUN_2024 = """<html><b>Per&iacute;odo:</b> 2024<P>
<PRE>
"Munic-BR";"Popula&ccedil;&atilde;o";"2.10\tSUBFUN&Ccedil;&Otilde;ES ADMINISTRATIVAS";"D.Total Sa&uacute;de"
"110001 Alta Floresta D'Oeste";21494;...;31753563,38
"522230 Vila Prop&iacute;cio";5815;...;10704227,19
"Total";27309;...;42457790,57
&
</PRE>
<P ALIGN=left>Legenda:</P></html>"""

FORM_UF = FORM_MUN.replace("municipio/mIndicadores.def", "estado/indicuf.def").replace(
    '<OPTION  VALUE="Munic-BR">Munic-BR', '<OPTION  VALUE="UF">UF'
).replace("indmun24.dbf", "induf24.dbf").replace("indmun23.dbf", "induf23.dbf")

PRN_UF_2024 = """<PRE>
"UF";"Popula&ccedil;&atilde;o";"2.10\tSUBFUN&Ccedil;&Otilde;ES ADMINISTRATIVAS";"D.Total Sa&uacute;de"
"Rond&ocirc;nia";1581196;...;2438298729,84
"S&atilde;o Paulo";45973194;...;1,00
"Total";47554390;...;2438298730,84
&
</PRE>"""


FORM_DF = FORM_MUN.replace("municipio/mIndicadores.def", "estado/indicdf.def").replace(
    '<OPTION  VALUE="Munic-BR">Munic-BR', '<OPTION  VALUE="Distrito_Federal">Distrito Federal'
).replace("indmun24.dbf", "inddf24.dbf").replace("indmun23.dbf", "inddf23.dbf")

PRN_DF = """<PRE>
"Distrito Federal";"Popula&ccedil;&atilde;o";"2.10	SUBFUN&Ccedil;&Otilde;ES ADMINISTRATIVAS";"D.Total Sa&uacute;de"
"Distrito Federal";2817381;...;5099437748,60
&
</PRE>"""


class FakeConn:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.sent = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        chunk, self.payload = self.payload[:size], self.payload[size:]
        return chunk

    def close(self) -> None:
        pass


class FakeTabnet:
    """Responde ao GET do .def com o formulário e ao POST com a página do ano."""

    def __init__(self, form: str, pages: dict, df_pages: dict = None) -> None:
        self.form = form
        self.pages = pages
        # O DF vem de outro .def (indicdf.def); por padrão responde 2023 e 2024.
        self.df_pages = {"inddf24.dbf": PRN_DF, "inddf23.dbf": PRN_DF} if df_pages is None else df_pages
        self.posts = []
        self.df_posts = []

    def text(self, url, body=None):
        is_df = "indicdf.def" in url
        if body is None:
            return FORM_DF if is_df else self.form
        fields = parse_qsl(body.decode("ascii"), encoding="latin-1")
        (self.df_posts if is_df else self.posts).append(fields)
        arquivo = dict(fields)["Arquivos"]
        page = (self.df_pages if is_df else self.pages)[arquivo]
        if callable(page):
            page = page(fields)
        if isinstance(page, Exception):
            raise page
        return page


def test_raw_response_tolerates_doctype_inside_headers():
    raw = (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nServer: Microsoft-IIS/6.0\r\n"
        b'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http: //www.w3.org">\r\n'
        b"X-Powered-By: ASP.NET\r\nConnection: close\r\n\r\n<html>Sa\xfade</html>"
    )
    response = parse_raw_response(raw)
    assert response.status == 200
    assert response.headers["server"] == "Microsoft-IIS/6.0"
    assert response.headers["x-powered-by"] == "ASP.NET"
    assert response.charset == "latin-1"
    assert response.body.decode(response.charset) == "<html>Saúde</html>"


def test_client_sends_http10_post_and_reads_until_close():
    payload = b"HTTP/1.1 200 OK\r\n<!DOCTYPE x>\r\n\r\n" + b"x" * 200_000
    conn = FakeConn(payload)
    client = TabnetClient(connect=lambda host, port, tls, timeout: conn)
    text = client.text("http://siops.example/CGI/tabcgi.exe?SIOPS/a.def", b"Linha=UF")
    assert len(text) == 200_000
    head = conn.sent.decode("latin-1")
    assert head.startswith("POST /CGI/tabcgi.exe?SIOPS/a.def HTTP/1.0\r\n")
    assert "Connection: close" in head and "Content-Length: 8" in head
    assert head.endswith("\r\n\r\nLinha=UF")


def test_client_maps_http_error_status():
    conn = FakeConn(b"HTTP/1.1 404 Not Found\r\n\r\nnada")
    client = TabnetClient(connect=lambda *a: conn, max_attempts=1)
    with pytest.raises(TabnetClientError) as info:
        client.text("http://siops.example/x.def")
    assert info.value.retryable is False


def test_form_reads_options_and_builds_latin1_body():
    form = parse_form(FORM_MUN)
    assert form.action.endswith("mIndicadores.def")
    assert form.years() == {2024: "indmun24.dbf", 2023: "indmun23.dbf"}
    assert form.values("Incremento")[1] == "2.10\tSUBFUNÇÕES_ADMINISTRATIVAS"
    assert form.filter_fields() == ["SUF", "SMunic-BR"]
    assert form.radios["formato"] == ["table", "prn"]
    body = form.build_body(
        linha="Munic-BR", coluna="--Não-Ativa--",
        incrementos=form.values("Incremento"), arquivos=["indmun24.dbf"],
    )
    assert b"Coluna=--N%E3o-Ativa--" in body
    fields = parse_qsl(body.decode("ascii"), encoding="latin-1")
    assert ("SMunic-BR", "TODAS_AS_CATEGORIAS__") in fields
    assert ("formato", "prn") in fields and ("mostre", "Mostra") in fields
    assert [v for k, v in fields if k == "Incremento"] == form.values("Incremento")
    with pytest.raises(ValueError):
        form.build_body(linha="Inexistente", coluna="Ano", incrementos=[], arquivos=[])


def test_prn_drops_total_and_ampersand_and_unescapes():
    table = parse_prn(PRN_MUN_2024)
    assert table.header == [
        "Munic-BR", "População", "2.10 SUBFUNÇÕES ADMINISTRATIVAS", "D.Total Saúde",
    ]
    assert table.rows == [
        ["110001 Alta Floresta D'Oeste", "21494", "...", "31753563,38"],
        ["522230 Vila Propício", "5815", "...", "10704227,19"],
    ]


def test_prn_unescapes_per_cell_not_per_line():
    page = (
        '<PRE>\n"Munic-BR";"Valor"\n'
        '"Rua &quot;A&quot; &#59; B";"1,5"\n"Total";"1,5"\n&\n</PRE>'
    )
    table = parse_prn(page)
    assert table.rows == [['Rua "A" ; B', "1,5"]]


def _read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_municipios_download_one_post_per_year(tmp_path):
    fake = FakeTabnet(FORM_MUN, {
        "indmun24.dbf": PRN_MUN_2024,
        "indmun23.dbf": PRN_MUN_2024.replace("21494", "21000"),
    })
    source = SiopsIndicadoresMunicipiosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2023, end_year=2024)
    assert payload["failed_count"] == 0 and payload["downloaded_count"] == 2
    assert payload["rows"] == 6
    assert len(fake.posts) == 2 and len(fake.df_posts) == 2
    rows = _read(payload["exported_files"][0])
    assert rows[0] == [
        "ano", "cod_ibge", "municipio",
        "População", "2.10 SUBFUNÇÕES ADMINISTRATIVAS", "D.Total Saúde",
    ]
    assert rows[1] == ["2023", "110001", "Alta Floresta D'Oeste", "21000", "...", "31753563,38"]
    assert rows[5] == ["2024", "522230", "Vila Propício", "5815", "...", "10704227,19"]
    # O DF entra uma vez por ano, com o código do município de Brasília.
    assert rows[3] == ["2023", "530010", "Brasília", "2817381", "...", "5099437748,60"]
    assert rows[6] == ["2024", "530010", "Brasília", "2817381", "...", "5099437748,60"]
    assert dict(fake.df_posts[0])["Linha"] == "Distrito_Federal"


def test_estados_download_maps_uf_code(tmp_path):
    fake = FakeTabnet(FORM_UF, {"induf24.dbf": PRN_UF_2024})
    source = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2024, output_format="parquet")
    assert payload["exported_files"][0].endswith(".parquet")
    import polars as pl

    frame = pl.read_parquet(payload["exported_files"][0])
    assert frame.columns[:4] == ["ano", "cod_uf", "uf", "nome_uf"]
    assert frame.row(1)[:4] == ("2024", "35", "SP", "São Paulo")
    assert dict(fake.posts[0])["Linha"] == "UF"
    assert frame.row(2)[:4] == ("2024", "53", "DF", "Distrito Federal")
    assert frame.height == 3


def test_df_failure_keeps_the_year_and_is_reported(tmp_path):
    fake = FakeTabnet(
        FORM_UF, {"induf24.dbf": PRN_UF_2024},
        df_pages={"inddf24.dbf": TabnetClientError("caiu", category="timeout", retryable=True)},
    )
    source = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2024)
    assert payload["failed_count"] == 0 and payload["rows"] == 2
    assert payload["partial_years"] == ["2024 sem DF (caiu)"]


def test_df_failure_goes_to_the_warnings(tmp_path):
    fake = FakeTabnet(
        FORM_UF, {"induf24.dbf": PRN_UF_2024},
        df_pages={"inddf24.dbf": TabnetClientError("caiu", category="timeout", retryable=True)},
    )
    source = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2024)
    assert "2024 sem DF (caiu)" in payload["export_warning"]


def test_df_value_error_becomes_a_warning_not_a_crash(tmp_path):
    fake = FakeTabnet(
        FORM_UF, {"induf24.dbf": PRN_UF_2024},
        df_pages={"inddf24.dbf": ValueError("Incremento(s) fora do formulário")},
    )
    source = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2024)
    assert payload["failed_count"] == 0 and payload["rows"] == 2
    assert "fora do formulário" in payload["export_warning"]


def test_year_after_the_last_offered_is_not_a_failure(tmp_path):
    fake = FakeTabnet(FORM_UF, {"induf24.dbf": PRN_UF_2024})
    source = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2024, end_year=2026)
    assert payload["failed_count"] == 0 and payload["downloaded_count"] == 1
    assert payload["partial_years"] == []
    assert "2025, 2026 ainda não publicado(s)" in payload["export_warning"]
    only_future = source.download(start_year=2026)
    assert only_future["failed_count"] == 0 and only_future["exported_files"] == []


def test_year_not_offered_and_failed_post_are_counted(tmp_path):
    fake = FakeTabnet(FORM_MUN, {
        "indmun24.dbf": TabnetClientError("caiu", category="timeout", retryable=True),
        "indmun23.dbf": PRN_MUN_2024,
    })
    source = SiopsIndicadoresMunicipiosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2022, end_year=2024)
    assert payload["failed_count"] == 2
    assert payload["downloaded_count"] == 1
    assert "2022: ano não oferecido" in payload["export_warning"]
    with pytest.raises(ValueError):
        source.download(start_year=1999)


MISSING_PAGE = """<html>Campo Incremento INDNUM1 nao encontrado em
siops\\serhist\\municipio\\indmun23.dbf<br>Nenhum registro selecionado</html>"""

PRN_MUN_2023_SEM_SUBFUNCAO = """<PRE>
"Munic-BR";"Popula&ccedil;&atilde;o";"D.Total Sa&uacute;de"
"110001 Alta Floresta D'Oeste";21000;100,00
"Total";21000;100,00
&
</PRE>"""


def test_old_year_without_some_field_keeps_the_others(tmp_path):
    def answer(fields):
        asked = [v for k, v in fields if k == "Incremento"]
        if any(item.startswith("2.10") for item in asked):
            return MISSING_PAGE
        if dict(fields)["Linha"] == "Ano":
            return "<PRE>\n\"Ano\";\"x\"\n\"2023\";1\n&\n</PRE>"
        return PRN_MUN_2023_SEM_SUBFUNCAO

    fake = FakeTabnet(FORM_MUN, {"indmun23.dbf": answer, "indmun24.dbf": PRN_MUN_2024})
    source = SiopsIndicadoresMunicipiosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2023, end_year=2024)
    assert payload["failed_count"] == 0
    assert payload["partial_years"] == ["2023 sem 1"]
    rows = _read(payload["exported_files"][0])
    assert rows[1] == ["2023", "110001", "Alta Floresta D'Oeste", "21000", "", "100,00"]
    assert rows[2][4] == "..."
    # 1 POST completo + 3 testes isolados + 1 POST final para 2023, 1 para 2024.
    assert len(fake.posts) == 6


PRN_DF_SEM_SUBFUNCAO = """<PRE>
"Distrito Federal";"Popula&ccedil;&atilde;o";"D.Total Sa&uacute;de"
"Distrito Federal";2817381;100,00
&
</PRE>"""


def test_df_refused_indicators_are_reported(tmp_path):
    def answer(fields):
        asked = [v for k, v in fields if k == "Incremento"]
        if any(item.startswith("2.10") for item in asked):
            return MISSING_PAGE
        if dict(fields)["Linha"] == "Ano":
            return '<PRE>\n"Ano";"x"\n"2024";1\n&\n</PRE>'
        return PRN_DF_SEM_SUBFUNCAO

    fake = FakeTabnet(FORM_UF, {"induf24.dbf": PRN_UF_2024}, df_pages={"inddf24.dbf": answer})
    source = SiopsIndicadoresEstadosDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(start_year=2024)
    assert payload["failed_count"] == 0
    assert payload["partial_years"] == ["2024 DF sem 1"]
    assert "2024 DF sem 1" in payload["export_warning"]


def test_registry_exposes_both_keys():
    from guaraci.services.downloads import DownloadService

    service = DownloadService()
    for key, floor in (("siops_indicadores_municipios", 2000), ("siops_indicadores_estados", 2002)):
        schema = service.get_source_schema(key)
        assert schema["mode"] == "siops tabnet"
        params = {spec["name"]: spec for spec in schema["params"]}
        assert {"start_year", "end_year", "output_format", "keep_raw"} <= set(params)
        assert params["start_year"]["minimum"] == floor
