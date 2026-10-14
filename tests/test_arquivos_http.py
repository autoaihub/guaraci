"""Fontes de arquivo HTTP de URL fixa (Vigitel, IBAMA, Farmácia Popular), sem rede.

Os casos que valem teste produziriam dado plausível e errado: BOM virando parte
do nome da primeira coluna, número pt-BR ou negativo reinterpretado, acento
corrompido, membro errado do zip e arquivo inalterado baixado de novo.
"""

from __future__ import annotations

import http.client
import io
import zipfile
from pathlib import Path
from typing import Dict

import polars as pl
import pytest

from guaraci.arquivos import (
    FARMACIA_INDICADORES,
    HTTP_FILES,
    HttpFileDataSource,
    RemoteFile,
)
from guaraci.arquivos.http_files import HttpFileClientError
from guaraci.services.downloads import DownloadService


class _Client:
    """Serve bytes por URL no lugar da rede."""

    def __init__(self, payloads: Dict[str, bytes], fail: tuple = ()) -> None:
        self.payloads = payloads
        self.fail = fail
        self.downloads = 0

    def head(self, url: str) -> RemoteFile:
        return RemoteFile(url=url, size=len(self.payloads[url]), last_modified="Wed", etag='"x"')

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        if any(url.endswith(f) for f in self.fail):
            raise HttpFileClientError("boom", category="http_error", retryable=False)
        self.downloads += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payloads[url])
        return len(self.payloads[url])


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _url(key: str, index: int = 0) -> str:
    return HTTP_FILES[key].resources[index].url


def _source(tmp_path: Path, key: str, client: _Client) -> HttpFileDataSource:
    return HttpFileDataSource(output_path=str(tmp_path), dataset=key, client=client)


_IBAMA = (
    "﻿Classe de uso;Ingrediente ativo;SEMESTRE;ANO;Vendas a clientes (ton. produtos);"
    "Qtd. Vendas - Acre\r\n"
    "Herbicida;2,4-D;1;2020;1.874,061;-15\r\n"
    "Inseticida;Piretróide;2;2021;;0003\r\n"
).encode("utf-8")


def test_ibama_remove_bom_e_preserva_texto(tmp_path: Path) -> None:
    key = "ibama_agrotoxicos_comercializacao"
    client = _Client({_url(key): _IBAMA})
    payload = _source(tmp_path, key, client).download(output_dir=str(tmp_path), output_format="csv")
    assert payload["failed_count"] == 0
    (exported,) = payload["exported_files"]
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.columns[0] == "Classe de uso"
    assert frame.row(0) == ("Herbicida", "2,4-D", "1", "2020", "1.874,061", "-15")
    assert frame["Qtd. Vendas - Acre"].to_list() == ["-15", "0003"]
    assert frame["Vendas a clientes (ton. produtos)"].to_list() == ["1.874,061", None]
    assert not (tmp_path / "relatorios_comercializacao_agrotoxicos.csv").exists()


def test_cp1252_sem_bom_nao_corrompe_acento(tmp_path: Path) -> None:
    key = "ibama_agrotoxicos_comercializacao"
    raw = "Classe;Nome\r\nHerbicida;Piretróide açaí\r\n".encode("cp1252")
    client = _Client({_url(key): raw})
    payload = _source(tmp_path, key, client).download(output_dir=str(tmp_path), output_format="csv")
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame["Nome"].to_list() == ["Piretróide açaí"]


def test_vigitel_le_so_o_membro_declarado_do_zip(tmp_path: Path) -> None:
    member = HTTP_FILES["vigitel"].member
    body = "ano,cidade,q6,pesorake2025\n2006,1,10,\n2024,2,,0.5\n".encode("utf-8")
    archive = _zip({"LEIAME.txt": b"nao e dado", member: body})
    client = _Client({_url("vigitel"): archive})
    payload = _source(tmp_path, "vigitel", client).download(
        output_dir=str(tmp_path), output_format="csv"
    )
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns == ["ano", "cidade", "q6", "pesorake2025"]
    assert frame.row(1) == ("2024", "2", None, "0.5")


def test_zip_de_membro_unico_nao_exige_nome(tmp_path: Path) -> None:
    code = "pfpbben"
    body = b"co_anomes,co_ibge,vl_indicador_calculado_mun\n202401,3550308,12.5\n"
    client = _Client({_url("farmacia_popular_indicadores", FARMACIA_INDICADORES.index(code)): _zip({"x.csv": body})})
    payload = _source(tmp_path, "farmacia_popular_indicadores", client).download(
        output_dir=str(tmp_path), output_format="csv", indicadores=[code]
    )
    assert payload["documents_found"] == 1
    (exported,) = payload["exported_files"]
    assert Path(exported).name == "farmacia_popular_indicadores_pfpbben.csv"
    assert pl.read_csv(exported, infer_schema=False).row(0) == ("202401", "3550308", "12.5")


def test_farmacia_popular_gera_um_csv_por_indicador(tmp_path: Path) -> None:
    key = "farmacia_popular_indicadores"
    payloads = {
        res.url: _zip({f"{res.code}.csv": f"co_anomes,co_ibge\n202401,{i}\n".encode()})
        for i, res in enumerate(HTTP_FILES[key].resources)
    }
    client = _Client(payloads)
    payload = _source(tmp_path, key, client).download(output_dir=str(tmp_path), output_format="csv")
    assert payload["documents_found"] == len(FARMACIA_INDICADORES) == 14
    assert len(payload["exported_files"]) == 14
    assert payload["failed_count"] == 0
    assert Path(payload["exported_files"][0]).name == "farmacia_popular_indicadores_atfpbcop.csv"


def test_farmacia_popular_indicador_que_falha_conta_sem_abortar(tmp_path: Path) -> None:
    key = "farmacia_popular_indicadores"
    payloads = {
        res.url: _zip({"a.csv": b"co_anomes\n202401\n"}) for res in HTTP_FILES[key].resources
    }
    client = _Client(payloads, fail=("pfpbdm.csv.zip",))
    payload = _source(tmp_path, key, client).download(
        output_dir=str(tmp_path), output_format="csv", indicadores=["pfpbben", "pfpbdm"]
    )
    assert payload["failed_count"] == 1
    assert len(payload["exported_files"]) == 1
    assert "pfpbdm" in payload["export_warning"]


def test_indicador_desconhecido_e_rejeitado(tmp_path: Path) -> None:
    client = _Client({})
    with pytest.raises(ValueError, match="Unknown indicadores"):
        _source(tmp_path, "farmacia_popular_indicadores", client).download(
            output_dir=str(tmp_path), indicadores=["nao_existe"]
        )


def test_arquivo_inalterado_nao_baixa_de_novo(tmp_path: Path) -> None:
    key = "ibama_agrotoxicos_comercializacao"
    client = _Client({_url(key): _IBAMA})
    source = _source(tmp_path, key, client)
    first = source.download(output_dir=str(tmp_path), keep_raw=True)
    second = source.download(output_dir=str(tmp_path), keep_raw=True)
    assert (first["downloaded_count"], first["skipped_count"]) == (1, 0)
    assert (second["downloaded_count"], second["skipped_count"]) == (0, 1)
    assert client.downloads == 1


def test_parquet_guarda_texto(tmp_path: Path) -> None:
    key = "ibama_agrotoxicos_comercializacao"
    client = _Client({_url(key): _IBAMA})
    payload = _source(tmp_path, key, client).download(
        output_dir=str(tmp_path), output_format="parquet"
    )
    frame = pl.read_parquet(payload["exported_files"][0])
    assert set(frame.schema.values()) == {pl.String}


def test_registro_expoe_as_tres_chaves_e_modos() -> None:
    service = DownloadService()
    expected = {
        "vigitel": "svs files",
        "ibama_agrotoxicos_comercializacao": "ibama files",
        "farmacia_popular_indicadores": "demas s3 files",
    }
    for key, mode in expected.items():
        schema = service.get_source_schema(key)
        assert schema["mode"] == mode
        assert "output_format" in {p["name"] for p in schema["params"]}
    farmacia = service.get_source_schema("farmacia_popular_indicadores")
    assert "indicadores" in {p["name"] for p in farmacia["params"]}
    service.validate_source_params("farmacia_popular_indicadores", {"indicadores": ["pfpbben"]})
    with pytest.raises(ValueError):
        service.validate_source_params("farmacia_popular_indicadores", {"indicadores": ["xx"]})


MGDI_KEYS = {
    "mgdi_samu": 11,
    "mgdi_upa": 6,
    "mgdi_raps": 14,
    "mgdi_emulti": 8,
    "mgdi_academia_saude": 4,
    "mgdi_telessaude": 19,
    "mgdi_saude_bucal": 5,
}


@pytest.mark.parametrize("key,total", sorted(MGDI_KEYS.items()))
def test_mgdi_registra_um_csv_por_indicador_no_bucket_demas(key: str, total: int) -> None:
    resources = HTTP_FILES[key].resources
    assert len(resources) == total
    assert len({r.code for r in resources}) == total
    assert all(r.url.startswith("https://demas-dados-abertos.s3.amazonaws.com/csv/") for r in resources)
    assert all(r.url.endswith(f"{r.code}.csv.zip") for r in resources)
    schema = DownloadService().get_source_schema(key)
    names = {p["name"]: p for p in schema["params"]}
    assert set(names["indicadores"]["allowed_values"]) == {r.code for r in resources}


def test_mgdi_samu_exporta_um_csv_por_indicador(tmp_path: Path) -> None:
    key = "mgdi_samu"
    payloads = {
        res.url: _zip({f"{res.code}.csv": b"co_ano,co_ibge,vl_indicador_calculado_mun\n2024,1100015,3\n"})
        for res in HTTP_FILES[key].resources
    }
    payload = _source(tmp_path, key, _Client(payloads)).download(
        output_dir=str(tmp_path), output_format="csv"
    )
    assert len(payload["exported_files"]) == 11
    assert payload["failed_count"] == 0
    assert Path(payload["exported_files"][0]).name == "mgdi_samu_samuaer.csv"


# --- transporte: truncamento, zip esperado, erros de socket, .part, encoding ---------------


class _Resp:
    """Resposta de urlopen: bytes em fluxo e cabeçalho Content-Length opcional."""

    def __init__(self, data: bytes, length=None) -> None:
        self._buf = io.BytesIO(data)
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _patch_urlopen(monkeypatch, fn) -> None:
    monkeypatch.setattr("guaraci.arquivos.http_files.urlopen", fn)


def test_download_truncado_pelo_content_length_e_erro_retentavel(tmp_path, monkeypatch):
    from guaraci.arquivos.http_files import HttpFileClient

    payload = _zip({"a.csv": b"x,y\n1,2\n"})
    _patch_urlopen(monkeypatch, lambda *_a, **_k: _Resp(payload[:-5], length=len(payload)))
    destination = tmp_path / "x.csv.zip"
    with pytest.raises(HttpFileClientError) as info:
        HttpFileClient(max_attempts=1).download("https://x/x.csv.zip", destination)
    assert info.value.retryable is True
    assert "truncated" in str(info.value)
    assert not destination.exists()
    assert not (tmp_path / "x.csv.zip.part").exists()


def test_download_truncado_e_tentado_de_novo(tmp_path, monkeypatch):
    from guaraci.arquivos.http_files import HttpFileClient

    payload = _zip({"a.csv": b"x,y\n1,2\n"})
    calls = []

    def fake(*_a, **_k):
        calls.append(1)
        if len(calls) == 1:
            return _Resp(payload[:-5], length=len(payload))
        return _Resp(payload, length=len(payload))

    _patch_urlopen(monkeypatch, fake)
    destination = tmp_path / "x.csv.zip"
    written = HttpFileClient(max_attempts=2).download("https://x/x.csv.zip", destination)
    assert written == len(payload) and len(calls) == 2
    assert zipfile.is_zipfile(destination)


def test_url_zip_sem_content_length_exige_zip_valido(tmp_path, monkeypatch):
    from guaraci.arquivos.http_files import HttpFileClient

    payload = _zip({"a.csv": b"x,y\n1,2\n"})
    _patch_urlopen(monkeypatch, lambda *_a, **_k: _Resp(payload[:20]))
    with pytest.raises(HttpFileClientError, match="not a valid zip"):
        HttpFileClient(max_attempts=1).download("https://x/a.csv.zip?v=1", tmp_path / "a.csv.zip")
    assert not (tmp_path / "a.csv.zip").exists()


def test_url_csv_nao_exige_zip(tmp_path, monkeypatch):
    from guaraci.arquivos.http_files import HttpFileClient

    _patch_urlopen(monkeypatch, lambda *_a, **_k: _Resp(b"a;b\n1;2\n", length=8))
    assert HttpFileClient(max_attempts=1).download("https://x/a.csv", tmp_path / "a.csv") == 8


def test_zip_esperado_que_nao_e_zip_falha_em_vez_de_virar_csv(tmp_path):
    code = "pfpbben"
    url = _url("farmacia_popular_indicadores", FARMACIA_INDICADORES.index(code))
    client = _Client({url: b"PK\x03\x04 truncado, nao fecha o diretorio central"})
    with pytest.raises(ValueError, match="should be a zip"):
        _source(tmp_path, "farmacia_popular_indicadores", client).download(
            output_dir=str(tmp_path), output_format="csv", indicadores=[code]
        )
    assert list(tmp_path.glob("*.csv")) == []


def test_zip_esperado_que_nao_e_zip_entre_varios_vira_aviso(tmp_path):
    key = "farmacia_popular_indicadores"
    resources = HTTP_FILES[key].resources
    payloads = {res.url: _zip({"a.csv": b"co_anomes\n202401\n"}) for res in resources}
    payloads[resources[1].url] = b"lixo que nao e zip"
    payload = _source(tmp_path, key, _Client(payloads)).download(
        output_dir=str(tmp_path),
        output_format="csv",
        indicadores=[resources[0].code, resources[1].code],
    )
    assert payload["failed_count"] == 1
    assert resources[1].code in payload["export_warning"]
    assert "should be a zip" in payload["export_warning"]


def test_falha_de_um_recurso_pedido_relanca_a_causa_real(tmp_path):
    key = "farmacia_popular_indicadores"
    payloads = {res.url: _zip({"a.csv": b"co_anomes\n202401\n"}) for res in HTTP_FILES[key].resources}
    client = _Client(payloads, fail=("pfpbdm.csv.zip",))
    with pytest.raises(HttpFileClientError, match="boom"):
        _source(tmp_path, key, client).download(
            output_dir=str(tmp_path), output_format="csv", indicadores=["pfpbdm"]
        )


def test_codificacao_decidida_por_linha_alem_do_primeiro_mb(tmp_path):
    # Vigitel real: 71 MB em ASCII e depois linhas cp1252 misturadas a UTF-8.
    key = "ibama_agrotoxicos_comercializacao"
    head = "Classe;Nome\r\n"
    filler = "Herbicida;abcdefghij\r\n" * 60000
    raw = (
        (head + filler).encode("utf-8")
        + b"Herbicida;pir\xf3tr\xf3ide\r\n"
        + "Herbicida;glifosato sódico\r\n".encode("utf-8")
        + b"Herbicida;controle\x81\r\n"
    )
    assert len(head + filler) > (1 << 20)
    client = _Client({_url(key): raw})
    payload = _source(tmp_path, key, client).download(output_dir=str(tmp_path), output_format="csv")
    assert payload["failed_count"] == 0
    text = Path(payload["exported_files"][0]).read_text(encoding="utf-8")
    assert "pirótróide" in text and "glifosato sódico" in text
    # 0x81 não existe no cp1252: só esse byte vira U+FFFD, com aviso.
    warning = payload["export_warning"]
    assert "1 caracteres" in warning and "relatorios_comercializacao_agrotoxicos.csv" in warning


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        ConnectionResetError(10054, "reset"),
        http.client.IncompleteRead(b"abc", 10),
        OSError(104, "socket error"),
    ],
)
def test_erros_de_socket_viram_erro_retentavel_no_head_e_no_download(tmp_path, monkeypatch, error):
    from guaraci.arquivos.http_files import HttpFileClient

    def boom(*_a, **_k):
        raise error

    _patch_urlopen(monkeypatch, boom)
    client = HttpFileClient(max_attempts=1)
    with pytest.raises(HttpFileClientError) as head:
        client.head("https://x/a.csv")
    with pytest.raises(HttpFileClientError) as download:
        client.download("https://x/a.csv", tmp_path / "a.csv")
    assert head.value.retryable is True and download.value.retryable is True


def test_erro_no_meio_da_leitura_e_retentado(tmp_path, monkeypatch):
    from guaraci.arquivos.http_files import HttpFileClient

    class Broken(_Resp):
        def read(self, size: int = -1) -> bytes:
            raise ConnectionResetError(10054, "reset")

    calls = []

    def fake(*_a, **_k):
        calls.append(1)
        return Broken(b"") if len(calls) == 1 else _Resp(b"a,b\n", length=4)

    _patch_urlopen(monkeypatch, fake)
    assert HttpFileClient(max_attempts=2).download("https://x/a.csv", tmp_path / "a.csv") == 4
    assert len(calls) == 2


def test_exportacao_que_falha_nao_deixa_arquivo_final_nem_part(tmp_path, monkeypatch):
    key = "ibama_agrotoxicos_comercializacao"

    def broken_sink(self, path, *args, **kwargs):
        Path(path).write_text("parcial")
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(pl.LazyFrame, "sink_csv", broken_sink)
    client = _Client({_url(key): _IBAMA})
    with pytest.raises(RuntimeError, match="disco cheio"):
        _source(tmp_path, key, client).download(output_dir=str(tmp_path), output_format="csv")
    assert not (tmp_path / f"{key}.csv").exists()
    assert list(tmp_path.glob("*.part")) == []
    assert list(tmp_path.glob("*.tmp.csv")) == []
