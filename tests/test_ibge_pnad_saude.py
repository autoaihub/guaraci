"""PNAD anual com suplemento de saúde (1998, 2003, 2008), sem rede.

Os zips falsos reproduzem o arranjo publicado: em 1998, dado e programa SAS
em zips separados, com INFILE genérico ('nome do arquivo a ser lido') e
informat ``$CHARw.``; em 2003 e 2008, a reponderação traz dado e INPUT no
mesmo zip, em pastas, com caixa diferente entre INFILE e membro.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.ibge.fixed_width import parse_sas_input
from guaraci.ibge.microdados import PESQUISAS, IbgeMicrodadosDataSource, RemoteFile
from guaraci.services.downloads import DownloadService

KEY = "ibge_pnad_saude"


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class _Client:
    def __init__(self, files: Dict[str, bytes]) -> None:
        self.files = files
        self.calls: List[str] = []

    def _payload(self, path: str) -> bytes:
        for suffix, data in self.files.items():
            if path.endswith(suffix):
                return data
        raise AssertionError(f"unexpected path {path}")

    def head(self, path: str) -> RemoteFile:
        self.calls.append(f"HEAD {path}")
        return RemoteFile(url=f"https://x/{path}", size=len(self._payload(path)), last_modified=None)

    def download(self, path: str, destination: Path, **_kwargs) -> int:
        self.calls.append(f"GET {path}")
        data = self._payload(path)
        destination.write_bytes(data)
        return len(data)


# Recorte do SAS_PES98.txt: cabeçalho, $CHARw., numérico sem $ e nome em
# minúscula (v4732), como no publicado.
_PES98_SAS = (
    "/* LAYOUT PARA LEITURA DOS DADOS DE PESSOAS DA PNAD 98*/\r\n"
    "DATA PESSOAS;\r\n"
    "     INFILE 'nome do arquivo a ser lido' LRECL=12 MISSOVER;\r\n"
    "     INPUT\r\n"
    "     @1          V0101   $CHAR2.   /* ANO DA PESQUISA                */\r\n"
    "     @3          UF      $CHAR2.   /* CODIGO DA UNIDADE DA FEDERACAO */\r\n"
    "     @5          V4729         5.  /* PESO PESSOA                    */\r\n"
    "     @10         v4732    $CHAR2.  /* PESO FAMÍLIA                   */\r\n"
    "     @12         V1303    $CHAR1.  /* CONSIDERA SEU ESTADO DE SAÚDE  */\r\n"
    "\r\nRUN;\r\n"
).encode("cp1252")
_DOM98_SAS = (
    "DATA DOMICS;\r\n"
    "     INFILE 'nome do arquivo a ser lido' LRECL=7 MISSOVER;\r\n"
    "     INPUT\r\n"
    "     @1          V0101   $CHAR2.   /* ANO DA PESQUISA */\r\n"
    "     @3          V4611        5.   /* PESO(TOTAL PESSOAS AMOSTRA) */\r\n"
    "\r\nRUN;\r\n"
).encode("cp1252")


def _client_1998() -> _Client:
    return _Client({
        "1998/Dados.zip": _zip({
            "Dados/Domicilio98.txt": b"9800321\r\n",
            "Dados/Pessoa98.txt": b"983300321012\r\n9811 4500   \r\n",
        }),
        "1998/Layout.zip": _zip({
            "Layout/SAS_DOM98.txt": _DOM98_SAS,
            "Layout/SAS_PES98.txt": _PES98_SAS,
        }),
    })


def _run(tmp_path: Path, client: _Client, **kwargs) -> dict:
    source = IbgeMicrodadosDataSource(output_path=str(tmp_path), dataset=KEY, client=client)
    return source.download(output_dir=str(tmp_path), **kwargs)


def test_char_informat_is_read_as_text_column():
    (block,) = parse_sas_input(_PES98_SAS.decode("cp1252"))
    assert [(c.name, c.start, c.width, c.is_char) for c in block.columns] == [
        ("V0101", 1, 2, True),
        ("UF", 3, 2, True),
        ("V4729", 5, 5, False),
        ("v4732", 10, 2, True),
        ("V1303", 12, 1, True),
    ]
    assert block.columns[-1].label == "CONSIDERA SEU ESTADO DE SAÚDE"
    assert block.layout_warning() is None


def test_1998_exports_pessoas_and_domicilios_from_separate_layout_zip(tmp_path):
    client = _client_1998()
    result = _run(tmp_path, client, start_year=1998, output_format="csv")
    assert result["documents_found"] == 2
    assert result["downloaded_count"] == 2  # Dados.zip e Layout.zip, uma vez cada
    names = [Path(p).name for p in result["exported_files"]]
    assert names == ["ibge_pnad_saude_1998_pessoas.csv", "ibge_pnad_saude_1998_domicilios.csv"]
    pessoas = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert pessoas.columns == ["V0101", "UF", "V4729", "v4732", "V1303"]
    assert pessoas.rows() == [("98", "33", "00321", "01", "2"), ("98", "11", "4500", "", "")]
    domicilios = pl.read_csv(result["exported_files"][1], infer_schema=False)
    assert domicilios.rows() == [("98", "00321")]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(names)


_PES2008_SAS = (
    "/* PROGRAMA DE LEITURA EM SAS DO ARQUIVO DE MICRODADOS DE PESSOAS */\r\n"
    "DATA PES2008;\r\n"
    "INFILE 'C:\\PNAD2008\\PES2008.TXT' LRECL=10;\r\n"
    "INPUT\r\n"
    "@00001 V0101 $4. /* ANO DE REFERÊNCIA */\r\n"
    "@00005 UF $2. /* UNIDADE DA FEDERAÇÃO */\r\n"
    "@00007 V1301 $1. /* TEM PLANO DE SAÚDE */\r\n"
    "@00008 V4729 3. /* PESO DA PESSOA */\r\n"
    ";\r\nRUN;\r\n"
).encode("cp1252")
_DOM2008_SAS = (
    "DATA DOM2008;\r\n"
    "INFILE 'C:\\PNAD2008\\DOM2008.TXT' LRECL=9;\r\n"
    "INPUT\r\n"
    "@00001 V0101 $4. /* ANO */\r\n"
    "@00005 V0233 $1. /* CADASTRO NA UNID.SAÚDE DA FAM */\r\n"
    "@00006 V4611 4. /* PESO */\r\n"
    ";\r\nRUN;\r\n"
).encode("cp1252")


def test_2008_reads_input_inside_the_reweighted_zip_and_filters_tabelas(tmp_path):
    client = _Client({
        "PNAD_reponderado_2008.zip": _zip({
            "2008/Dados/PES2008.TXT": "200843Á123\r\n".encode("cp1252"),
            "2008/Dados/DOM2008.txt": b"200810123\r\n",
            "2008/Input/input PES2008.txt": _PES2008_SAS,
            "2008/Input/input DOM2008.txt": _DOM2008_SAS,
        }),
    })
    result = _run(tmp_path, client, start_year=2008, tabelas=["domicilios"], output_format="parquet")
    assert result["downloaded_count"] == 1
    assert client.calls == [
        "HEAD Trabalho_e_Rendimento/Pesquisa_Nacional_por_Amostra_de_Domicilios_anual/"
        "microdados/reponderacao_2001_2012/PNAD_reponderado_2008.zip",
        "GET Trabalho_e_Rendimento/Pesquisa_Nacional_por_Amostra_de_Domicilios_anual/"
        "microdados/reponderacao_2001_2012/PNAD_reponderado_2008.zip",
    ]
    (exported,) = result["exported_files"]
    assert Path(exported).name == "ibge_pnad_saude_2008_domicilios.parquet"
    assert pl.read_parquet(exported).rows() == [("2008", "1", "0123")]

    pessoas = _run(tmp_path, client, start_year=2008, tabelas="pessoas", output_format="csv")
    frame = pl.read_csv(pessoas["exported_files"][0], infer_schema=False)
    assert frame.row(0) == ("2008", "43", "Á", "123")  # acento em cp1252 não desalinha


def test_editions_are_only_the_three_health_supplements():
    assert sorted(PESQUISAS[KEY].edicoes) == [1998, 2003, 2008]
    for edicao in PESQUISAS[KEY].edicoes.values():
        assert [t.nome for t in edicao.tabelas] == ["pessoas", "domicilios"]
    # 2003 e 2008 vêm da reponderação de 2001-2012, a versão mais recente.
    assert "reponderacao_2001_2012" in PESQUISAS[KEY].edicoes[2003].arquivos["dados"]
    assert "reponderacao_2001_2012" in PESQUISAS[KEY].edicoes[2008].arquivos["dados"]


def test_year_between_supplements_downloads_nothing(tmp_path):
    client = _client_1998()
    result = _run(tmp_path, client, start_year=1999, end_year=2002, output_format="csv")
    assert result["documents_found"] == 0 and client.calls == []
    assert "1998" in result["export_warning"]


def test_schema_restricts_years_and_tabelas():
    schema = DownloadService().get_source_schema(KEY)
    assert schema is not None
    text = str(schema)
    assert "1998, 2003, 2008" in text
    params = {p["name"]: p for p in schema["params"]}
    assert params["start_year"]["minimum"] == 1998
    assert params["start_year"]["maximum"] == 2008
    assert params["tabelas"]["allowed_values"] == ["domicilios", "pessoas"]


@pytest.mark.parametrize("ano", [1998, 2003, 2008])
def test_unknown_tabela_is_rejected(tmp_path, ano):
    with pytest.raises(ValueError, match="Unknown tabelas"):
        _run(tmp_path, _Client({}), start_year=ano, tabelas=["moradores"], output_format="csv")


@pytest.mark.smoke
@pytest.mark.skipif(
    os.environ.get("GUARACI_IBGE_MICRODADOS_SMOKE") != "1",
    reason="Set GUARACI_IBGE_MICRODADOS_SMOKE=1 to enable the live IBGE microdata smoke test",
)
def test_live_1998_layout_parses_to_lrecl(tmp_path):
    """Só o Layout.zip de 1998 (cerca de 100 KB); os INPUT de 2003 e 2008 vêm dentro dos zips de dados."""
    from guaraci.ibge.microdados import IbgeFtpClient, _find_member

    edicao = PESQUISAS[KEY].edicoes[1998]
    target = tmp_path / "layout.zip"
    IbgeFtpClient().download(edicao.arquivos["layout"], target)
    with zipfile.ZipFile(target) as archive:
        for tabela, lrecl, variaveis in (("pessoas", 1026, 442), ("domicilios", 154, 55)):
            (programa,) = [t.layout[1] for t in edicao.tabelas if t.nome == tabela]
            (block,) = parse_sas_input(archive.read(_find_member(archive, programa)).decode("cp1252"))
            assert block.lrecl == block.record_length == lrecl
            assert len(block.columns) == variaveis
