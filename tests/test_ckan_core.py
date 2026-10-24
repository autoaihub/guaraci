"""Núcleo CKAN sem rede externa: servidor HTTP local e cliente fake."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import polars as pl
import pytest

from guaraci.ckan import (
    BROWSER_USER_AGENT,
    CkanClient,
    CkanClientError,
    CkanDataset,
    CkanResource,
    ckan_datasource_for,
    resource_kind,
    resource_period,
    resources_from_package,
    select_resources,
)
from guaraci.ckan.federal import CKAN_FEDERAL
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import ckan_federal

CSV_TEXT = "nome;valor\r\nCoração;1\r\nÁgua;2\r\n"


def _zip(members: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _xlsx(rows: list) -> bytes:
    def cell(ref, text):
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    body = "".join(
        f'<row r="{n}">' + "".join(cell(f"{chr(65 + i)}{n}", v) for i, v in enumerate(row)) + "</row>"
        for n, row in enumerate(rows, start=1)
    )
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    return _zip({
        "xl/workbook.xml": (
            f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'
            '<sheet name="Plan1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>',
    })


class _Server:
    def __init__(self) -> None:
        self.seen_agents: list = []
        self.hits: list = []
        self.packages: dict = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencioso
                pass

            def _send(self, code, body=b"", ctype="application/octet-stream", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                outer.seen_agents.append(self.headers.get("User-Agent"))
                outer.hits.append(self.path)
                path, _, query = self.path.partition("?")
                if path == "/api/3/action/package_show":
                    pid = query.split("id=")[1].split("&")[0]
                    if pid not in outer.packages:
                        return self._send(404, b'{"success": false}', "application/json")
                    payload = {"success": True, "result": outer.packages[pid]}
                    return self._send(200, json.dumps(payload).encode(), "application/json")
                if path == "/api/3/action/package_search":
                    results = list(outer.packages.values())
                    payload = {"success": True, "result": {"count": len(results), "results": results}}
                    return self._send(200, json.dumps(payload).encode(), "application/json")
                if path == "/redir/a.csv":
                    return self._send(302, b"", extra={"Location": "/signed/a.csv?X-Amz-Signature=abc"})
                if path == "/signed/a.csv":
                    return self._send(200, CSV_TEXT.encode("cp1252"), "text/csv")
                if path == "/bad.zip":
                    return self._send(200, b"isto nao e um zip")
                if path == "/waf.csv":
                    return self._send(200, b"<html>Request Rejected</html>", "text/html")
                if path == "/forbidden.csv":
                    return self._send(403, b"no")
                if path == "/good.zip":
                    return self._send(200, _zip({"x.csv": CSV_TEXT.encode("cp1252")}))
                return self._send(404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture()
def server():
    srv = _Server()
    yield srv
    srv.close()


def _resource(name, url, fmt="CSV", rid=""):
    return CkanResource(package_id="p", id=rid or name, name=name, url=url, format=fmt)


# --- período e tipo -----------------------------------------------------------


def test_periodo_do_nome_e_da_url_em_varios_padroes():
    base = "https://s3/x/"
    cases = [
        (_resource("CAT - junho 2023", base + "D.SDA.PDA.005.CAT.202306.ZIP"), (2023, 6)),
        (_resource("Benefícios concedidos Setembro 2026", base + "CONCEDIDOS+ABERTOS_SETEMBRO+2026.xlsx"), (2026, 9)),
        (_resource("Mantidos Ativos Juho 2026", base + "ATIVO_202606.zip"), (2026, 6)),
        (_resource("Concedidos Jun 2026", base + "CONCEDIDOS_DADOS+ABERTOS_JUN+2026.xlsx"), (2026, 6)),
        (_resource("CNUC_2026_07", base + "cnuc_2026_07.csv"), (2026, 7)),
        (_resource("Unidades - 2018", base + "unidade-de-conservacao.csv"), (2018, None)),
        (_resource("SETEMBRO 2026", base + "download"), (2026, 9)),
        (_resource("sem data", base + "arquivo.csv"), None),
    ]
    for resource, expected in cases:
        assert resource_period(resource) == expected, resource.name


def test_periodo_com_regex_propria():
    resource = _resource("Casos 2019", "https://x/dengue_2024.csv")
    assert resource_period(resource) == (2019, None)
    assert resource_period(resource, r"dengue_(?P<year>\d{4})") == (2024, None)


def test_tipo_pela_extensao_da_url_e_nao_pelo_rotulo():
    assert resource_kind(_resource("a", "https://x/a.xlsx", "CSV")) == "xlsx"
    assert resource_kind(_resource("a", "https://x/a.ZIP", "CSV")) == "zip"
    assert resource_kind(_resource("a", "https://x/a.pdf", "CSV")) == "outro"
    assert resource_kind(_resource("a", "https://x/download", "zip")) == "zip"
    assert resource_kind(_resource("a", "https://sharepoint/:u:/g/x", "ZIP")) == "zip"


def test_package_show_com_recursos_mistos_descarta_pdf_e_seleciona_por_ano_e_mes():
    package = {
        "name": "p",
        "title": "P",
        "resources": [
            {"id": "1", "name": "Dicionário", "url": "https://x/dic.pdf", "format": "PDF"},
            {"id": "2", "name": "Janeiro 2024", "url": "https://x/a.csv", "format": "CSV"},
            {"id": "3", "name": "Fevereiro 2024", "url": "https://x/b.csv", "format": "CSV"},
            {"id": "4", "name": "Janeiro 2025", "url": "https://x/c.csv", "format": "CSV"},
            {"id": "5", "name": "Mapa", "url": "https://x/d.shp.zip", "format": "zip"},
            {"id": "6", "name": "apagado", "url": "https://x/e.csv", "state": "deleted"},
        ],
    }
    spec = CkanDataset(
        key="t", title="T", description="d", base_url="http://x/api/3/action/",
        package_ids=("p",), exclude_pattern=r"shp", default_latest=True,
    )
    resources = resources_from_package(package)
    assert [r.id for r in resources] == ["1", "2", "3", "4", "5"]
    chosen, warnings, latest = select_resources(spec, resources)
    assert latest and chosen[0][0].id == "4"  # mais novo primeiro; o datasource usa só o primeiro período
    chosen, _, latest = select_resources(spec, resources, anos=[2024])
    assert not latest and [c[0].id for c in chosen] == ["3", "2"]
    chosen, _, _ = select_resources(spec, resources, anos=["2024"], meses=["01"])
    assert [c[0].id for c in chosen] == ["2"]
    chosen, warn, _ = select_resources(spec, resources, anos=[2024, 2030])
    assert any("2030" in w for w in warn)
    chosen, _, _ = select_resources(spec, resources, start_year=2025)
    assert [c[0].id for c in chosen] == ["4"]
    chosen, _, _ = select_resources(spec, resources, recursos=["fevereiro"])
    assert [c[0].id for c in chosen] == ["3"]


def test_periodo_obrigatorio_recusa_sem_anos():
    spec = CkanDataset(
        key="t", title="T", description="d", base_url="http://x/", package_ids=("p",),
        period_required=True,
    )
    with pytest.raises(ValueError, match="anos"):
        select_resources(spec, [_resource("2024", "https://x/a.csv")])


# --- cliente ------------------------------------------------------------------


def test_cliente_package_show_e_ua_de_navegador(server):
    server.packages["p"] = {"name": "p", "resources": [{"id": "1", "name": "a", "url": "u.csv"}]}
    client = CkanClient(server.base + "/api/3/action", user_agent=BROWSER_USER_AGENT)
    assert client.package_show("p")["name"] == "p"
    assert [r.id for r in client.resources("p")] == ["1"]
    assert server.seen_agents[-1] == BROWSER_USER_AGENT
    assert client.package_search()["count"] == 1
    default = CkanClient(server.base + "/api/3/action/")
    default.package_show("p")
    assert server.seen_agents[-1].startswith("guaraci/")


def test_cliente_404_vira_erro_de_configuracao_sem_retentativa(server):
    client = CkanClient(server.base + "/api/3/action/", max_attempts=3)
    with pytest.raises(CkanClientError) as info:
        client.package_show("nao-existe")
    assert info.value.category == "configuration"
    assert sum("package_show" in h for h in server.hits) == 1


def test_download_segue_302_sem_guardar_a_url_assinada(server, tmp_path):
    client = CkanClient(server.base + "/api/3/action/")
    target = tmp_path / "a.csv"
    written = client.download(server.base + "/redir/a.csv", target)
    assert written == target.stat().st_size
    assert "/signed/a.csv?X-Amz-Signature=abc" in server.hits  # o urllib seguiu
    assert not (tmp_path / "a.csv.part").exists()


def test_download_zip_invalido_e_pagina_de_erro_falham_e_limpam_o_part(server, tmp_path):
    client = CkanClient(server.base + "/api/3/action/", max_attempts=1)
    with pytest.raises(CkanClientError) as info:
        client.download(server.base + "/bad.zip", tmp_path / "bad.zip")
    assert info.value.category == "incomplete" and info.value.retryable
    with pytest.raises(CkanClientError) as waf:
        client.download(server.base + "/waf.csv", tmp_path / "waf.csv")
    assert waf.value.category == "response_format"
    assert list(tmp_path.glob("*")) == []
    client.download(server.base + "/good.zip", tmp_path / "good.zip")
    assert zipfile.is_zipfile(tmp_path / "good.zip")


def test_url_assinada_nao_aparece_na_mensagem_de_erro(server, tmp_path):
    client = CkanClient(server.base + "/api/3/action/", max_attempts=1)
    with pytest.raises(CkanClientError) as info:
        client.download(server.base + "/forbidden.csv?X-Amz-Signature=segredo", tmp_path / "f.csv")
    assert "segredo" not in str(info.value)


# --- datasource ----------------------------------------------------------------


class _FakeClient:
    def __init__(self, package, files, fail=()):
        self.package = package
        self.files = files
        self.fail = set(fail)
        self.downloaded: list = []

    def resources(self, package_id):
        return resources_from_package(self.package)

    def package_search(self, q=None, fq=None, rows=1000, start=0):
        results = [self.package] if start == 0 else []
        return {"count": 1, "results": results}

    def download(self, url, destination, progress_callback=None):
        if url in self.fail:
            raise CkanClientError("403", category="http_error", retryable=False)
        self.downloaded.append(url)
        Path(destination).write_bytes(self.files[url])
        return len(self.files[url])


def _spec(**kwargs):
    base = dict(key="demo", title="Demo", description="d", base_url="http://x/api/3/action/",
                package_ids=("p",))
    base.update(kwargs)
    return CkanDataset(**base)


def _pkg(*resources):
    return {"name": "p", "resources": [
        {"id": str(i), "name": n, "url": u, "format": "CSV"} for i, (n, u) in enumerate(resources)
    ]}


def test_csv_vira_utf8_com_nome_de_coluna_como_publicado(tmp_path):
    url = "https://x/a_2024.csv"
    client = _FakeClient(_pkg(("Ano 2024", url)), {url: CSV_TEXT.encode("cp1252")})
    source = ckan_datasource_for(_spec())(output_path=str(tmp_path), client=client)
    payload = source.download(output_format="csv")
    (path,) = payload["exported_files"]
    frame = pl.read_csv(path, infer_schema=False)
    assert frame.columns == ["nome", "valor"]
    assert frame["nome"].to_list() == ["Coração", "Água"]
    assert payload["failed_count"] == 0 and payload["documents_found"] == 1
    assert not list(tmp_path.glob("*.orig.csv"))  # original descartado


def test_zip_com_csv_json_xml_exporta_so_o_csv_e_varios_membros_viram_irmaos(tmp_path):
    one = "https://x/CAT.202608.ZIP"
    many = "https://x/MULTI.zip"
    files = {
        one: _zip({"CAT.csv": CSV_TEXT.encode("cp1252"), "CAT.json": b"[]", "CAT.xml": b"<x/>"}),
        many: _zip({"a.csv": b"x;y\n1;2\n", "b.csv": b"x;y\n3;4\n", "leia.pdf": b"%PDF"}),
    }
    client = _FakeClient(_pkg(("CAT 2026", one), ("Multi 2025", many)), files)
    source = ckan_datasource_for(_spec(file_format="zip", period_required=True))(
        output_path=str(tmp_path), client=client
    )
    payload = source.download(output_format="csv", anos=[2026, 2025])
    names = sorted(Path(p).name for p in payload["exported_files"])
    assert names == ["demo__CAT_202608.csv", "demo__MULTI__a.csv", "demo__MULTI__b.csv"]
    only = ckan_datasource_for(_spec(file_format="zip", member_pattern=r"b\.csv$", period_required=True))(
        output_path=str(tmp_path / "o"), client=client
    )
    payload = only.download(output_format="csv", anos=[2025])
    assert [Path(p).name for p in payload["exported_files"]] == ["demo__MULTI.csv"]


def test_xlsx_com_preambulo_e_cabecalho_repetido(tmp_path):
    url = "https://x/CONCEDIDOS_SETEMBRO+2026.xlsx"
    book = _xlsx([["TITULO DA PLANILHA"], ["APS", "APS", "UF"], ["1", "Maceio", "AL"], ["2", "Recife", "PE"]])
    client = _FakeClient(_pkg(("Setembro 2026", url)), {url: book})
    spec = _spec(file_format="xlsx", skip_rows=1, default_latest=True)
    source = ckan_datasource_for(spec)(output_path=str(tmp_path), client=client)
    payload = source.download(output_format="csv")
    (path,) = payload["exported_files"]
    frame = pl.read_csv(path, infer_schema=False)
    assert frame.columns == ["APS", "APS_duplicated_0", "UF"]
    assert frame.height == 2 and frame["UF"].to_list() == ["AL", "PE"]
    assert "repete nomes" in payload["export_warning"]


def test_mais_novo_recua_quando_o_ultimo_periodo_esta_fora_do_ar(tmp_path):
    new, old = "https://x/D.202609.csv", "https://x/D.202608.csv"
    client = _FakeClient(
        _pkg(("Setembro 2026", new), ("Agosto 2026", old)),
        {new: b"a;b\n1;2\n", old: b"a;b\n3;4\n"},
        fail=[new],
    )
    source = ckan_datasource_for(_spec(default_latest=True))(output_path=str(tmp_path), client=client)
    payload = source.download(output_format="csv")
    assert client.downloaded == [old]
    assert payload["periods"] == ["2026-08"] and payload["failed_count"] == 0
    assert "403" in payload["export_warning"]


def test_recurso_unico_com_falha_sobe_o_erro_real(tmp_path):
    url = "https://x/a.csv"
    client = _FakeClient(_pkg(("A", url)), {}, fail=[url])
    source = ckan_datasource_for(_spec())(output_path=str(tmp_path), client=client)
    with pytest.raises(CkanClientError):
        source.download(output_format="csv")


def test_package_query_pagina_e_ua_de_navegador_na_spec(tmp_path, monkeypatch):
    url = "https://x/a.csv"
    client = _FakeClient(_pkg(("A", url)), {url: b"a;b\n1;2\n"})
    spec = _spec(package_ids=(), package_query="organization:fhemig", browser_user_agent=True)
    source = ckan_datasource_for(spec)(output_path=str(tmp_path), client=client)
    assert source.download(output_format="csv")["documents_found"] == 1
    made = ckan_datasource_for(spec)(output_path=str(tmp_path))._make_client(30)
    assert made.user_agent == BROWSER_USER_AGENT


# --- registro -------------------------------------------------------------------


def test_chaves_federais_respondem_ao_schema_e_so_as_com_periodo_trazem_anos():
    service = DownloadService(sources=ckan_federal.build_sources())
    keys = set(CKAN_FEDERAL)
    assert keys == {
        "mma_unidades_conservacao", "mma_especies_ameacadas", "inss_cat",
        "inss_beneficios_concedidos", "inss_beneficios_mantidos",
        "inss_beneficios_cessados", "inss_beneficios_indeferidos",
    }
    for key in keys:
        names = {p["name"] for p in service.get_source_schema(key)["params"]}
        assert "recursos" in names and "output_format" in names
        assert ("anos" in names) == CKAN_FEDERAL[key].has_period
    assert ckan_federal.ckan_api_source(_spec()).descriptor.mode == "ckan files"
