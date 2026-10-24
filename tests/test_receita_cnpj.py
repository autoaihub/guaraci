"""CNPJ da Receita por WebDAV, sem rede: cliente e listagem falsos.

Os casos que valem teste dariam dado plausível e errado: competência incompleta
escolhida como a mais recente, parte trocada, Latin-1 virando lixo, colunas
nomeadas sobre arquivo de largura diferente e token recusado sem explicação.
"""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path
from typing import Dict, List
from urllib.error import HTTPError

import polars as pl
import pytest

from guaraci.receita import (
    CNPJ_FILES,
    ReceitaWebDavClient,
    ReceitaWebDavError,
    datasource_for,
)
from guaraci.receita.cnpj import ESTABELECIMENTOS_COLUMNS, SOCIOS_COLUMNS
from guaraci.receita.webdav import DavEntry, parse_propfind
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import receita as receita_sources

PROPFIND = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
<d:response><d:href>/public.php/webdav/</d:href><d:propstat><d:prop>
<d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/public.php/webdav/2026-09/</d:href><d:propstat><d:prop>
<d:getlastmodified>Mon, 14 Sep 2026 15:08:06 GMT</d:getlastmodified>
<d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/public.php/webdav/cnpj.tar.gz</d:href><d:propstat><d:prop>
<d:getcontentlength>123</d:getcontentlength><d:resourcetype/></d:prop></d:propstat></d:response>
</d:multistatus>"""


def _zip(member: str, text: str, encoding: str = "latin-1") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text.encode(encoding))
    return buffer.getvalue()


def _row(n: int) -> str:
    return ";".join(f'"{i}"' for i in range(n)) + "\n"


class _Dav:
    """Árvore ``{pasta: {arquivo: bytes}}`` no lugar do WebDAV."""

    def __init__(self, tree: Dict[str, Dict[str, bytes]]) -> None:
        self.tree = tree
        self.downloads: List[str] = []

    def list(self, path: str = "") -> List[DavEntry]:
        if not path:
            return [DavEntry(name, True, None, None) for name in self.tree]
        return [DavEntry(n, False, len(b), "2026-09-14T15:00:00") for n, b in self.tree[path].items()]

    def url(self, path: str) -> str:
        return f"https://fake/{path}"

    def download(self, path, destination, *, progress_callback=None, chunk_size=0):
        folder, name = path.split("/")
        self.downloads.append(path)
        destination.write_bytes(self.tree[folder][name])
        return destination.stat().st_size


def _ds(key: str, tmp_path: Path, dav: _Dav):
    return datasource_for(key)(str(tmp_path), client=dav)


def test_parse_propfind_lists_children_only():
    entries = parse_propfind(PROPFIND, "https://x/public.php/webdav", "")
    assert [(e.name, e.is_dir, e.size) for e in entries] == [
        ("2026-09", True, None),
        ("cnpj.tar.gz", False, 123),
    ]
    assert entries[0].last_modified.startswith("2026-09-14T15:08:06")


def test_latest_competencia_skips_incomplete_folder(tmp_path):
    estab = _zip("K.ESTABELE", _row(30))
    dav = _Dav({
        "2026-09": {f"Estabelecimentos{n}.zip": estab for n in range(10)},
        "2026-10": {"Estabelecimentos0.zip": estab},  # ainda subindo
    })
    out = _ds("receita_cnpj_estabelecimentos", tmp_path, dav).download(
        output_format="csv", partes=["1"]
    )
    # com 'partes' só a parte 1 é exigida, e 2026-10 não a tem
    assert out["competencia"] == "2026-09"
    assert dav.downloads == ["2026-09/Estabelecimentos1.zip"]
    assert Path(out["exported_files"][0]).name == (
        "receita_cnpj_estabelecimentos_202609_parte1.csv"
    )


def test_estabelecimentos_columns_named_and_latin1_decoded(tmp_path):
    fields = ["07396865", "0001", "68", "1", "CAFÉ & CIA", "08", "20170210", "01"] + [""] * 22
    line = ";".join(f'"{v}"' for v in fields) + "\n"
    dav = _Dav({"2026-09": {"Estabelecimentos3.zip": _zip("K.ESTABELE", line)}})
    out = _ds("receita_cnpj_estabelecimentos", tmp_path, dav).download(
        output_format="csv", partes=["3"], competencia="2026-09"
    )
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert tuple(frame.columns) == ESTABELECIMENTOS_COLUMNS
    assert frame.height == 1  # a primeira linha é dado, não cabeçalho
    assert frame["nome_fantasia"][0] == "CAFÉ & CIA"
    assert frame["cnpj_basico"][0] == "07396865"  # zeros à esquerda preservados
    assert not list(tmp_path.glob("*.zip"))  # raw apagado sem keep_raw


def test_socios_keeps_masked_cpf_as_published(tmp_path):
    line = '"07396865";"2";"GERSON HOFFMANN";"***240659**";"49";"20050518";"";"***000000**";"";"00";"6"\n'
    dav = _Dav({"2026-09": {"Socios1.zip": _zip("K.SOCIOCSV", line)}})
    out = _ds("receita_cnpj_socios", tmp_path, dav).download(
        output_format="csv", partes=[1], competencia="2026-09", keep_raw=True
    )
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert tuple(frame.columns) == SOCIOS_COLUMNS
    assert frame["cnpj_cpf_socio"][0] == "***240659**"
    assert (tmp_path / "receita_cnpj_socios_202609_Socios1.zip").exists()
    assert "LGPD" in CNPJ_FILES["receita_cnpj_socios"].description


def test_width_mismatch_is_isolated_per_part_and_never_named(tmp_path):
    dav = _Dav({"2026-09": {
        "Empresas0.zip": _zip("K.EMPRECSV", _row(7)),
        "Empresas1.zip": _zip("K.EMPRECSV", _row(8)),
    }})
    out = _ds("receita_cnpj_empresas", tmp_path, dav).download(
        output_format="csv", partes=[0, 1], competencia="2026-09"
    )
    assert out["failed_count"] == 1
    assert len(out["exported_files"]) == 1
    assert "8 colunas, esperadas 7" in out["export_warning"]
    single = _ds("receita_cnpj_empresas", tmp_path / "b", dav)
    with pytest.raises(ValueError, match="8 colunas"):
        single.download(output_format="csv", partes=[1], competencia="2026-09")


def test_tabelas_one_output_each_and_simples_single_file(tmp_path):
    names = {"Cnaes": "CNAECSV", "Municipios": "MUNICCSV"}
    files = {
        f"{n}.zip": _zip(f"F.{m}", '"0111301";"Cultivo de arroz"\n') for n, m in names.items()
    }
    files["Simples.zip"] = _zip("F.SIMPLES.CSV", _row(7))
    dav = _Dav({"2026-09": files})
    out = _ds("receita_cnpj_tabelas", tmp_path, dav).download(
        output_format="csv", tabelas=["cnaes", "municipios"]
    )
    assert sorted(Path(p).name for p in out["exported_files"]) == [
        "receita_cnpj_tabelas_202609_cnaes.csv",
        "receita_cnpj_tabelas_202609_municipios.csv",
    ]
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.columns == ["codigo", "descricao"]
    simples = _ds("receita_cnpj_simples", tmp_path, dav).download(output_format="csv")
    assert Path(simples["exported_files"][0]).name == "receita_cnpj_simples_202609.csv"


def test_bad_arguments(tmp_path):
    dav = _Dav({"2026-09": {}})
    estab = _ds("receita_cnpj_estabelecimentos", tmp_path, dav)
    with pytest.raises(ValueError, match="0 a 9"):
        estab.download(partes=[10])
    with pytest.raises(ValueError, match="começa em 2023-05"):
        estab.download(competencia="2023-04")
    with pytest.raises(ValueError, match="inválida"):
        estab.download(competencia="setembro")
    with pytest.raises(ValueError, match="desconhecidas"):
        _ds("receita_cnpj_tabelas", tmp_path, dav).download(tabelas=["cbo"])
    with pytest.raises(ValueError, match="sem Estabelecimentos0.zip"):
        estab.download(partes=[0], competencia="2026-09")


def test_client_sends_basic_token_and_explains_401(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["auth"] = request.get_header("Authorization")
        seen["method"] = request.get_method()
        seen["depth"] = request.get_header("Depth")
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("guaraci.receita.webdav.urlopen", fake_urlopen)
    client = ReceitaWebDavClient(token="TOKEN123", max_attempts=3)
    with pytest.raises(ReceitaWebDavError) as info:
        client.list("2026-09")
    assert seen["method"] == "PROPFIND" and seen["depth"] == "1"
    assert seen["auth"] == "Basic " + base64.b64encode(b"TOKEN123:").decode()
    assert info.value.retryable is False  # 401 não é repetido
    assert info.value.category == "configuration"
    assert "token" in (info.value.hint or "")


def test_registered_schema_for_every_key():
    service = DownloadService(sources=receita_sources.build_sources())
    for key in CNPJ_FILES:
        assert service.get_source_schema(key)
    names = {p.name for p in next(
        s for s in receita_sources.build_sources() if s.descriptor.source == "receita_cnpj_tabelas"
    ).params_schema()}
    assert {"tabelas", "competencia", "token"} <= names
    assert "partes" not in names
