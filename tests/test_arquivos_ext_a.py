"""Extensões de ``http_files.py`` do Pacote A (turno 1) e as fontes novas que as usam, sem rede.

Cobre: probe por Range (host que recusa HEAD), User-Agent por spec, xlsx com abas e
preâmbulo, zip com vários membros, código de semestre/trimestre no seletor ``periodo``,
janela ``start_year``/``end_year`` e o registro (schema) de cada chave nova.
"""

from __future__ import annotations

import http.server
import threading
import zipfile
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.arquivos import (
    HttpFile,
    HttpFileClient,
    HttpFileClientError,
    HttpResource,
    RemoteFile,
    datasource_for_spec,
    ibama,
    seguranca,
    transito_sp,
)
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import arquivos as sources_arquivos
from tests.test_arquivos_http import _Client, _zip


class _Handler(http.server.BaseHTTPRequestHandler):
    seen: List[Dict[str, str]] = []

    def log_message(self, *args) -> None:  # silencia o stderr do pytest
        pass

    def do_HEAD(self) -> None:
        type(self).seen.append({"method": "HEAD", "ua": self.headers.get("User-Agent", "")})
        self.send_response(403)
        self.end_headers()

    def do_GET(self) -> None:
        type(self).seen.append(
            {
                "method": "GET",
                "ua": self.headers.get("User-Agent", ""),
                "range": self.headers.get("Range", ""),
            }
        )
        body = b"a;b\n1;2\n"
        if self.headers.get("Range"):
            self.send_response(206)
            self.send_header("Content-Range", "bytes 0-0/12345")
            self.send_header("Content-Length", "1")
            self.send_header("Last-Modified", "Mon, 08 Jan 2024 17:41:41 GMT")
            self.end_headers()
            self.wfile.write(body[:1])
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def server():
    _Handler.seen = []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/arquivo.csv"
    httpd.shutdown()
    httpd.server_close()


def test_probe_range_le_content_range_quando_head_da_403(server: str) -> None:
    client = HttpFileClient(timeout_seconds=5, max_attempts=1)
    with pytest.raises(HttpFileClientError) as failure:
        client.head(server)
    assert failure.value.status == 403

    remote = client.head(server, probe="range", user_agent="Mozilla/5.0 teste")
    assert remote.size == 12345
    assert remote.last_modified == "Mon, 08 Jan 2024 17:41:41 GMT"
    probe_call = _Handler.seen[-1]
    assert probe_call["method"] == "GET"
    assert probe_call["range"] == "bytes=0-0"
    assert probe_call["ua"] == "Mozilla/5.0 teste"


def test_probe_desconhecido_falha_cedo() -> None:
    with pytest.raises(ValueError):
        HttpFileClient(max_attempts=1).head("http://127.0.0.1:9/x", probe="post")


def test_download_envia_user_agent_da_spec(server: str, tmp_path: Path) -> None:
    client = HttpFileClient(timeout_seconds=5, max_attempts=1)
    written = client.download(server, tmp_path / "a.csv", user_agent="Mozilla/5.0 teste")
    assert written == len(b"a;b\n1;2\n")
    assert _Handler.seen[-1]["ua"] == "Mozilla/5.0 teste"
    client.download(server, tmp_path / "b.csv")
    assert _Handler.seen[-1]["ua"].startswith("guaraci/")


class _RecordingClient(_Client):
    def __init__(self, payloads: Dict[str, bytes]) -> None:
        super().__init__(payloads)
        self.head_kwargs: List[dict] = []
        self.download_kwargs: List[dict] = []

    def head(self, url: str, **kwargs) -> RemoteFile:
        self.head_kwargs.append(kwargs)
        return super().head(url)

    def download(self, url: str, destination: Path, **kwargs) -> int:
        self.download_kwargs.append({k: v for k, v in kwargs.items() if k != "progress_callback"})
        return super().download(url, destination)


def _spec(key: str = "teste_a", **kwargs) -> HttpFile:
    resources = kwargs.pop("resources", (HttpResource("unico", "http://x/unico.csv"),))
    return HttpFile(key, "Teste", "Teste", resources, separator=";", **kwargs)


def test_spec_com_probe_e_user_agent_repassa_ao_cliente(tmp_path: Path) -> None:
    spec = _spec(probe="range", user_agent="Mozilla/5.0 teste")
    client = _RecordingClient({"http://x/unico.csv": b"a;b\n1;2\n"})
    source = datasource_for_spec(spec)(output_path=str(tmp_path), client=client)
    source.download(output_dir=str(tmp_path), output_format="csv")
    assert client.head_kwargs == [{"user_agent": "Mozilla/5.0 teste", "probe": "range"}]
    assert client.download_kwargs == [{"user_agent": "Mozilla/5.0 teste"}]


def test_spec_padrao_nao_passa_argumento_extra(tmp_path: Path) -> None:
    client = _RecordingClient({"http://x/unico.csv": b"a;b\n1;2\n"})
    source = datasource_for_spec(_spec())(output_path=str(tmp_path), client=client)
    source.download(output_dir=str(tmp_path), output_format="csv")
    assert client.head_kwargs == [{}]
    assert client.download_kwargs == [{}]


def _workbook(path: Path, sheets: Dict[str, list]) -> None:
    """XLSX mínimo com textos compartilhados e uma folha por entrada."""
    shared: List[str] = []

    def sid(text: str) -> int:
        if text not in shared:
            shared.append(text)
        return shared.index(text)

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    parts = {}
    for number, rows in enumerate(sheets.values(), start=1):
        body = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, value in enumerate(row):
                ref = f"{chr(65 + c)}{r}"
                if isinstance(value, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                elif value is not None:
                    cells.append(f'<c r="{ref}" t="s"><v>{sid(str(value))}</v></c>')
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
        parts[f"xl/worksheets/sheet{number}.xml"] = (
            f'<worksheet {ns}><sheetData>{"".join(body)}</sheetData></worksheet>'
        )
    names = "".join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(sheets, start=1)
    )
    rels = "".join(
        f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
            f'relationships"><sheets>{names}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            f'relationships">{rels}</Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>",
        )
        for name, xml in parts.items():
            archive.writestr(name, xml)


_PREAMBULO = [["Tabela 1"], ["Fonte: teste"]]


def _xlsx_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "wb.xlsx"
    _workbook(
        path,
        {
            "Brasil": _PREAMBULO + [["uf", "valor"], ["AC", 1], ["AL", 2]],
            "Notas": _PREAMBULO + [["nota", "texto"], ["1", "ok"]],
        },
    )
    return path.read_bytes()


def test_xlsx_uma_saida_por_aba_pulando_o_preambulo(tmp_path: Path) -> None:
    url = "http://x/dados.xlsx"
    spec = _spec(resources=(HttpResource("dados", url),), file_format="xlsx", skip_rows=2)
    client = _Client({url: _xlsx_bytes(tmp_path)})
    out = tmp_path / "out"
    payload = datasource_for_spec(spec)(output_path=str(out), client=client).download(
        output_dir=str(out), output_format="csv"
    )
    assert sorted(Path(p).name for p in payload["exported_files"]) == [
        "teste_a_Brasil.csv",
        "teste_a_Notas.csv",
    ]
    brasil = pl.read_csv(out / "teste_a_Brasil.csv", infer_schema=False)
    assert brasil.columns == ["uf", "valor"]
    assert brasil.rows() == [("AC", "1"), ("AL", "2")]


def test_xlsx_com_sheets_escolhe_a_aba_e_nao_sufixa(tmp_path: Path) -> None:
    url = "http://x/dados.xlsx"
    spec = _spec(
        resources=(HttpResource("dados", url),), file_format="xlsx", skip_rows=2, sheets=("Brasil",)
    )
    client = _Client({url: _xlsx_bytes(tmp_path)})
    out = tmp_path / "out"
    payload = datasource_for_spec(spec)(output_path=str(out), client=client).download(
        output_dir=str(out), output_format="csv"
    )
    assert [Path(p).name for p in payload["exported_files"]] == ["teste_a.csv"]


def test_xlsx_aba_inexistente_diz_quais_existem(tmp_path: Path) -> None:
    url = "http://x/dados.xlsx"
    spec = _spec(resources=(HttpResource("dados", url),), file_format="xlsx", sheets=("Nada",))
    client = _Client({url: _xlsx_bytes(tmp_path)})
    with pytest.raises(ValueError, match="Brasil"):
        datasource_for_spec(spec)(output_path=str(tmp_path / "o"), client=client).download(
            output_dir=str(tmp_path / "o"), output_format="csv"
        )


def test_members_pattern_gera_uma_saida_irma_por_membro(tmp_path: Path) -> None:
    url = "http://x/auto_infracao_csv.zip"
    archive = _zip(
        {
            "auto_infracao_2024.csv": "ID;NOME\n1;Ana\n".encode("utf-8"),
            "auto_infracao_2025.csv": "ID;NOME;EXTRA\n2;José;x\n".encode("utf-8"),
            "LEIAME.txt": b"nao e dado",
        }
    )
    spec = _spec(
        "teste_membros",
        resources=(HttpResource("auto_infracao", url), HttpResource("outro", "http://x/o.csv")),
        members_pattern=r"\.csv$",
        selector="indicadores",
    )
    client = _Client({url: archive, "http://x/o.csv": b"k;v\n1;2\n"})
    out = tmp_path / "out"
    payload = datasource_for_spec(spec)(output_path=str(out), client=client).download(
        output_dir=str(out), output_format="csv"
    )
    names = sorted(Path(p).name for p in payload["exported_files"])
    assert names == [
        "teste_membros_auto_infracao_2024.csv",
        "teste_membros_auto_infracao_2025.csv",
        "teste_membros_outro.csv",
    ]
    ano_25 = pl.read_csv(out / names[1], infer_schema=False)
    assert ano_25.columns == ["ID", "NOME", "EXTRA"]
    assert ano_25["NOME"].to_list() == ["José"]


def test_members_pattern_sem_membro_que_case_falha(tmp_path: Path) -> None:
    url = "http://x/z.zip"
    spec = _spec("teste_membros", resources=(HttpResource("z", url),), members_pattern=r"\.dat$")
    client = _Client({url: _zip({"a.csv": b"x;y\n1;2\n"})})
    with pytest.raises(ValueError, match="matched no member"):
        datasource_for_spec(spec)(output_path=str(tmp_path), client=client).download(
            output_dir=str(tmp_path), output_format="csv"
        )


_SEMESTRES = (
    HttpResource("2020_S1", "http://x/2020s1.csv"),
    HttpResource("2020_S2", "http://x/2020s2.csv"),
    HttpResource("2021_S1", "http://x/2021s1.csv"),
    HttpResource("2021_T3", "http://x/2021t3.csv"),
)
_PAYLOADS = {r.url: b"a;b\n1;2\n" for r in _SEMESTRES}


def _periodo(tmp_path: Path, **kwargs):
    spec = _spec("teste_sem", resources=_SEMESTRES, selector="periodo", **kwargs)
    client = _Client(dict(_PAYLOADS))
    return datasource_for_spec(spec)(output_path=str(tmp_path), client=client), client


def _codes(payload) -> List[str]:
    return sorted(Path(p).stem.removeprefix("teste_sem_") for p in payload["exported_files"])


def test_periodo_aceita_semestre_e_trimestre_em_meses(tmp_path: Path) -> None:
    source, _ = _periodo(tmp_path)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv", anos=[2020, 2021], meses=["S2", "t3"]
    )
    assert _codes(payload) == ["2020_S2", "2021_T3"]


def test_periodo_obrigatorio_por_padrao(tmp_path: Path) -> None:
    source, _ = _periodo(tmp_path)
    with pytest.raises(ValueError, match="anos"):
        source.download(output_dir=str(tmp_path), output_format="csv")


def test_periodo_opcional_baixa_tudo_sem_anos(tmp_path: Path) -> None:
    source, client = _periodo(tmp_path, period_required=False)
    payload = source.download(output_dir=str(tmp_path), output_format="csv")
    assert len(payload["exported_files"]) == 4
    assert client.downloads == 4


def test_janela_start_end_year_recorta_e_ignora_ano_desconhecido(tmp_path: Path) -> None:
    source, _ = _periodo(tmp_path, year_window=True)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv", start_year=2021, end_year=2030
    )
    assert _codes(payload) == ["2021_S1", "2021_T3"]
    with pytest.raises(ValueError, match="não tem arquivo"):
        source.download(output_dir=str(tmp_path), output_format="csv", start_year=2010, end_year=2012)


def test_ano_desconhecido_em_anos_continua_erro(tmp_path: Path) -> None:
    source, _ = _periodo(tmp_path)
    with pytest.raises(ValueError, match="Unknown anos"):
        source.download(output_dir=str(tmp_path), output_format="csv", anos=[1999])


NOVAS = (
    "ibama_autos_infracao",
    "ibama_termos_embargo",
    "mdhc_disque100",
    "senappen_sisdepen",
    "isp_rj_delegacias_mensal",
    "isp_rj_municipios_mensal",
    "detran_sp_infosiga_sinistros",
    "detran_sp_infosiga_pessoas",
    "detran_sp_infosiga_veiculos",
    "ibama_rapp_emissoes_atmosfericas",
    "ibama_rapp_efluentes_liquidos",
)


@pytest.mark.parametrize("key", NOVAS)
def test_chave_nova_responde_no_schema(key: str) -> None:
    service = DownloadService(sources=sources_arquivos.build_sources())
    schema = service.get_source_schema(key)
    names = {p["name"] for p in schema["params"]}
    assert {"output_dir", "output_format", "timeout"} <= names


def test_schema_do_disque100_tem_anos_obrigatorios_e_semestres() -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema(
        "mdhc_disque100"
    )
    params = {p["name"]: p for p in schema["params"]}
    assert params["anos"]["required"] is True
    assert params["anos"]["allowed_values"][0] == "2020"
    assert params["meses"]["allowed_values"] == ["S1", "S2", "T3"]
    assert {"start_year", "end_year"} <= set(params)


def test_schema_do_infosiga_aceita_janela_sem_exigir_anos() -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema(
        "detran_sp_infosiga_pessoas"
    )
    params = {p["name"]: p for p in schema["params"]}
    assert params["anos"]["required"] is False
    assert "meses" not in params
    assert {"start_year", "end_year"} <= set(params)


def test_http_file_source_registra_spec_fora_de_http_files() -> None:
    source = sources_arquivos.http_file_source(_spec("teste_fora"), "teste files")
    assert source.descriptor.source == "teste_fora"
    assert source.descriptor.mode == "teste files"


def test_listas_congeladas_sao_coerentes() -> None:
    codes = [r.code for r in seguranca.MDHC_DISQUE100.resources]
    assert len(codes) == len(set(codes)) == 14
    urls = [r.url for r in seguranca.SENAPPEN_SISDEPEN.resources]
    assert len(urls) == len(set(urls)) == 22
    assert all(u.endswith(".csv/@@download/file") for u in urls)
    infosiga = transito_sp.DETRAN_SP_INFOSIGA_PESSOAS.resources
    assert infosiga[0].url.endswith("/pessoas_2015.csv")
    assert infosiga[-1].url.endswith(f"/pessoas_{transito_sp.MAX_YEAR}.csv")
    assert {r.code for r in ibama.IBAMA_AUTOS_INFRACAO.resources} == {
        "auto_infracao", "enquadramento", "especime", "coordenada", "bioma",
    }


def test_descricoes_com_dado_pessoal_trazem_a_nota_padrao() -> None:
    for spec in (
        ibama.IBAMA_AUTOS_INFRACAO,
        ibama.IBAMA_TERMOS_EMBARGO,
        seguranca.SENAPPEN_SISDEPEN,
    ):
        assert "Traz identificador pessoal" in spec.description
        assert "camadas prata e ouro do Sabiá" in spec.description
