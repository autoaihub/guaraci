"""Fontes de saúde da leva 7 (IARC CI5-XII, SB Brasil, PNDS 2006, Covitel, Cetic.br), sem rede.

Os casos que valem teste produziriam dado plausível e errado: DBF com número ou data
reinterpretados, largura fixa deslocada por acento, registro do CI5 fora do leiaute, membro
errado de zip (Covitel 2023 traz o mesmo dado em três formatos) e arquivo do portal do
Ministério que só responde com sonda por GET e User-Agent de navegador.
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import polars as pl
import pytest

from guaraci.arquivos import RemoteFile, datasource_for_spec
from guaraci.cetic import tic
from guaraci.iarc import ci5, monografias
from guaraci.inqueritos import covitel, pnds, sb_brasil
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import saude_leva7

MODULES = (ci5, monografias, sb_brasil, pnds, covitel, tic)
SPECS = [spec for module in MODULES for spec in module.SPECS]


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class _Client:
    """Serve bytes por URL e guarda as opções que a spec manda para ``head``."""

    def __init__(self, payloads: Dict[str, bytes]) -> None:
        self.payloads = payloads
        self.head_kwargs: List[dict] = []

    def head(self, url: str, **kwargs) -> RemoteFile:
        self.head_kwargs.append(kwargs)
        return RemoteFile(url=url, size=len(self.payloads[url]), last_modified="Wed", etag='"x"')

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payloads[url])
        return len(self.payloads[url])


def _dbf(campos: List[Tuple[str, str, int]], linhas: List[List[bytes]]) -> bytes:
    """DBF (dBase III) mínimo: ``campos`` = (nome, tipo, tamanho); valores já em bytes."""
    registro = 1 + sum(tamanho for _, _, tamanho in campos)
    cabecalho = 32 + 32 * len(campos) + 1
    saida = struct.pack("<BBBBIHH20x", 3, 126, 11, 14, len(linhas), cabecalho, registro)
    for nome, tipo, tamanho in campos:
        saida += struct.pack("<11sc4xBB14x", nome.encode(), tipo.encode(), tamanho, 0)
    saida += b"\r"
    for linha in linhas:
        saida += b" " + b"".join(v.ljust(t)[:t] for v, (_, _, t) in zip(linha, campos))
    return saida + b"\x1a"


def _run(tmp_path: Path, spec, payloads: Dict[str, bytes], cls=None, **kwargs) -> dict:
    out = tmp_path / "out"
    client = _Client(payloads)
    source = (cls or datasource_for_spec(spec))(output_path=str(out), client=client)
    payload = source.download(output_dir=str(out), output_format="csv", **kwargs)
    payload["_client"] = client
    return payload


# DBF ---------------------------------------------------------------------------------------

_CAMPOS = [("MUNICIPI", "C", 4), ("IDADE", "N", 3), ("DATA", "D", 8), ("OBS", "C", 6)]


def test_sb_1996_dbf_preserva_zeros_a_esquerda_e_trata_branco_como_nulo(tmp_path: Path) -> None:
    dbf = _dbf(_CAMPOS, [[b"0150", b" 07", b"19960102", "Sã".encode("cp1252")], [b"0151", b"", b"", b""]])
    url = sb_brasil.SB_BRASIL_1996.resources[0].url
    payload = _run(
        tmp_path, sb_brasil.SB_BRASIL_1996, {url: _zip({"SB96.DBF": dbf})},
        cls=sb_brasil.DATASOURCES["sb_brasil_1996"],
    )
    (exportado,) = payload["exported_files"]
    assert Path(exportado).name == "sb_brasil_1996.csv"
    frame = pl.read_csv(exportado, infer_schema=False)
    assert frame.columns == ["MUNICIPI", "IDADE", "DATA", "OBS"]
    assert frame.row(0) == ("0150", "07", "19960102", "Sã")
    assert frame.row(1) == ("0151", None, None, None)
    assert payload["export_warning"] is None


def test_dbf_com_byte_invalido_avisa_em_vez_de_calar(tmp_path: Path) -> None:
    dbf = _dbf([("NOME", "C", 4)], [[b"\x81\x8d\x8f\x90"]])
    url = sb_brasil.SB_BRASIL_1996.resources[0].url
    payload = _run(
        tmp_path, sb_brasil.SB_BRASIL_1996, {url: _zip({"SB96.DBF": dbf})},
        cls=sb_brasil.DATASOURCES["sb_brasil_1996"],
    )
    assert "U+FFFD" in payload["export_warning"]


def test_sb_2003_usa_sonda_por_range_e_um_arquivo_por_regiao(tmp_path: Path) -> None:
    dbf = _dbf(_CAMPOS, [[b"0150", b"12", b"20030101", b"x"]])
    pdf = b"%PDF-1.4"
    urls = {r.code: r.url for r in sb_brasil.SB_BRASIL_2003.resources}
    payloads = {u: _zip({f"SBBrasil_{c.upper()}.dbf": dbf, "Lista_Variaveis.pdf": pdf})
                for c, u in urls.items()}
    payload = _run(
        tmp_path, sb_brasil.SB_BRASIL_2003, payloads,
        cls=sb_brasil.DATASOURCES["sb_brasil_2003"], indicadores=["se", "su"],
    )
    nomes = sorted(Path(p).name for p in payload["exported_files"])
    assert nomes == ["sb_brasil_2003_se.csv", "sb_brasil_2003_su.csv"]
    assert payload["_client"].head_kwargs[0]["probe"] == "range"
    assert "Chrome" in payload["_client"].head_kwargs[0]["user_agent"]


def test_sb_2003_cinco_regioes_e_urls_fixas() -> None:
    assert [r.code for r in sb_brasil.SB_BRASIL_2003.resources] == ["co", "ne", "no", "se", "su"]
    assert all("/sb-brasil/arquivos/2020/sbbrasil_" in r.url for r in sb_brasil.SB_BRASIL_2003.resources)


# Largura fixa ------------------------------------------------------------------------------

_DCT = (
    'infix dictionary using "SeuDiretorio\\PNDS2006_BR_MULHERES.dat" {\n'
    "1 lines\n"
    "    str      REC_TYPE    1:   1-3   \n"
    "    long     id    1:   4-9   \n"
    "    str      nome    1:   10-15   \n"
    "}\n"
).encode("cp1252")


def test_pnds_le_o_dat_pelas_posicoes_do_dct_com_acento_e_brancos(tmp_path: Path) -> None:
    dat = "210000123Ação \r\n210000456      \r\n".encode("cp1252")
    outro = (b'infix dictionary using "x.dat" {\n1 lines\n    byte  a    1:   1-1   \n}\n', b"7\r\n")
    url = pnds.PNDS_2006.resources[0].url
    arquivo = _zip({
        "PNDS2006_BR_MULHERES.dat": dat, "PNDS2006_BR_MULHERES.dct": _DCT,
        "PNDS2006_BR_FILHOS.dct": outro[0], "PNDS2006_BR_FILHOS.dat": outro[1],
        "PNDS2006_BR_MULHERES.sav": b"binario",
    })
    payload = _run(tmp_path, pnds.PNDS_2006, {url: arquivo}, cls=pnds.DATASOURCES["pnds_2006"])
    nomes = sorted(Path(p).name for p in payload["exported_files"])
    assert nomes == ["pnds_2006_filhos.csv", "pnds_2006_mulheres.csv"]
    mulheres = pl.read_csv(
        next(p for p in payload["exported_files"] if "mulheres" in p), infer_schema=False
    )
    assert mulheres.columns == ["REC_TYPE", "id", "nome"]
    assert mulheres.rows() == [("210", "000123", "Ação"), ("210", "000456", None)]


def test_pnds_dat_sem_dct_falha_com_mensagem_clara(tmp_path: Path) -> None:
    url = pnds.PNDS_2006.resources[0].url
    with pytest.raises(ValueError, match="não tem o .dct"):
        _run(tmp_path, pnds.PNDS_2006, {url: _zip({"A.dat": b"1\r\n"})},
             cls=pnds.DATASOURCES["pnds_2006"])


def test_dct_de_varias_linhas_nao_e_lido_como_se_fosse_uma(tmp_path: Path) -> None:
    dct = b'infix dictionary using "a.dat" {\n2 lines\n    byte a    2:   1-1   \n}\n'
    url = pnds.PNDS_2006.resources[0].url
    with pytest.raises(ValueError, match="várias linhas"):
        _run(tmp_path, pnds.PNDS_2006, {url: _zip({"A.dat": b"1\r\n", "A.dct": dct})},
             cls=pnds.DATASOURCES["pnds_2006"])


# CI5-XII -----------------------------------------------------------------------------------

_REGISTRY = (
    "101200399 * Algeria, Batna                                                       2015-2017\r\n"
    "207600299 Brazil, Goiânia                                                        2013-2016\r\n"
    "207600399 * Brazil, Barretos                                                     2013-2017\r\n"
).encode("utf-8")
_CANCER = (
    "CANCER\tICD-10\tLABEL\r\n"
    "1\tC00             \tLip                      \r\n"
    "2\tC01-02          \tTongue                   \r\n"
).encode("utf-8")


def _ci5_zip(**trocas: bytes) -> bytes:
    membros = {
        "cases.csv": b"REGISTRY,SEX,CANCER,TOTAL\r\n207600299,1,1,0\r\n207600299,1,2,5\r\n",
        "pop.csv": b"REGISTRY,SEX,AGE_GROUP,P0_4\r\n207600299,1,16,198107\r\n",
        "Registry.txt": _REGISTRY,
        "cancer_summary.txt": _CANCER,
    }
    membros.update(trocas)
    return _zip(membros)


def test_ci5_gera_quatro_tabelas_e_separa_o_marcador_do_nome(tmp_path: Path) -> None:
    url = ci5.IARC_CI5_XII.resources[0].url
    payload = _run(tmp_path, ci5.IARC_CI5_XII, {url: _ci5_zip()}, cls=ci5.DATASOURCES["iarc_ci5_xii"])
    nomes = sorted(Path(p).name for p in payload["exported_files"])
    assert nomes == [f"iarc_ci5_xii_{t}.csv" for t in ("cancer", "cases", "pop", "registros")]
    por_nome = {Path(p).name: pl.read_csv(p, infer_schema=False) for p in payload["exported_files"]}
    assert por_nome["iarc_ci5_xii_registros.csv"].rows() == [
        ("101200399", "*", "Algeria, Batna", "2015-2017"),
        ("207600299", None, "Brazil, Goiânia", "2013-2016"),
        ("207600399", "*", "Brazil, Barretos", "2013-2017"),
    ]
    assert por_nome["iarc_ci5_xii_cancer.csv"].rows()[0] == ("1", "C00", "Lip")
    assert por_nome["iarc_ci5_xii_cases.csv"].row(1) == ("207600299", "1", "2", "5")


def test_ci5_registro_fora_do_leiaute_falha_em_vez_de_cortar_o_nome(tmp_path: Path) -> None:
    url = ci5.IARC_CI5_XII.resources[0].url
    ruim = _ci5_zip(**{"Registry.txt": b"207600299 Brazil, Goiania sem periodo\r\n"})
    with pytest.raises(ValueError, match="fora do leiaute"):
        _run(tmp_path, ci5.IARC_CI5_XII, {url: ruim}, cls=ci5.DATASOURCES["iarc_ci5_xii"])


def test_ci5_zip_sem_um_dos_membros_diz_quais_faltam(tmp_path: Path) -> None:
    url = ci5.IARC_CI5_XII.resources[0].url
    with pytest.raises(ValueError, match="registry.txt"):
        _run(tmp_path, ci5.IARC_CI5_XII, {url: _zip({"cases.csv": b"a\r\n1\r\n"})},
             cls=ci5.DATASOURCES["iarc_ci5_xii"])


# Monografias do IARC (lista dentro de um módulo JavaScript) ------------------------------

_LOC_JS = (
    "!function(e){}([function(e,a){e.exports={last_volume:\"142\",agents:["
    '{name:"Glyphosate",group:"2A",cas:["1071-83-6"],volume:["112"],year:2017,yeareval:2015},'
    '{name:"Aldrin (see Dieldrin)",cas:["309-00-2"]},'
    '{name:"Radon [222]",group:"1",volume:["43","100D"],in_prep:!0,year:2012,yeareval:2009,'
    "comment:'NB The \"evidence\" isn\\'t [final]'},"
    '{name:"Tag, \\"x\\"",group:"3",volume:["1"],year:1987}'
    "]}},function(e,a){e.exports='<table>[not data]</table>'}]);"
)


def _loc(tmp_path: Path, js: str):
    url = monografias.IARC_MONOGRAFIAS_CLASSIFICACOES.resources[0].url
    return _run(
        tmp_path, monografias.IARC_MONOGRAFIAS_CLASSIFICACOES, {url: js.encode("utf-8")},
        cls=monografias.DATASOURCES["iarc_monografias_classificacoes"],
    )


def test_monografias_le_a_lista_do_modulo_js_com_booleano_aspas_simples_e_colchete(tmp_path: Path) -> None:
    payload = _loc(tmp_path, _LOC_JS)
    (exportado,) = payload["exported_files"]
    frame = pl.read_csv(exportado, infer_schema=False)
    assert frame.columns == ["name", "group", "cas", "volume", "year", "yeareval", "in_prep", "comment"]
    assert frame.row(0) == ("Glyphosate", "2A", "1071-83-6", "112", "2017", "2015", None, None)
    assert frame.row(1)[:2] == ("Aldrin (see Dieldrin)", None)
    assert frame.row(2) == (
        "Radon [222]", "1", None, "43;100D", "2012", "2009", "true",
        "NB The \"evidence\" isn't [final]",
    )
    assert frame.row(3)[0] == 'Tag, "x"'


def test_monografias_sem_a_lista_agents_falha_em_vez_de_devolver_vazio(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mudou o arquivo"):
        _loc(tmp_path, "!function(){}();")


# Covitel e Cetic.br (transporte genérico) --------------------------------------------------


def test_covitel_2023_le_so_o_csv_e_ignora_dta_e_xls(tmp_path: Path) -> None:
    url = covitel.COVITEL_2023.resources[0].url
    arquivo = _zip({
        "Dados Covitel 2023/BD_Covitel_2023imputed_com_peso.csv": b"id_exp,cidade\n1,S\xc3\xa3o Paulo\n",
        "Dados Covitel 2023/BD_Covitel_2023imputed_com_peso.dta": b"\x00dta",
        "Dados Covitel 2023/BD_Covitel_2023imputed_com_peso.xls": b"\xd0\xcf",
    })
    payload = _run(tmp_path, covitel.COVITEL_2023, {url: arquivo})
    (exportado,) = payload["exported_files"]
    assert pl.read_csv(exportado, infer_schema=False).rows() == [("1", "São Paulo")]


def test_cetic_saude_pega_o_csv_do_zip_com_acento_no_nome(tmp_path: Path) -> None:
    url = tic.CETIC_TIC_SAUDE.resources[0].url
    assert "%C3%B3s" in url
    arquivo = _zip({
        "1. Base de microdados/tic_saude_2025_estabelecimentos_pós_cec_base_de_microdados_v1.0.csv":
            '"ID_QUEST";"PESO"\n"0001";"1,25"\n'.encode("utf-8"),
        "1. Base de microdados/tic_saude_2025_estabelecimentos_pós_cec_base_de_microdados_v1.0.sav": b"sav",
        "2. Dicionário de variáveis/dicionario.xlsx": b"xlsx",
    })
    payload = _run(tmp_path, tic.CETIC_TIC_SAUDE, {url: arquivo})
    (exportado,) = payload["exported_files"]
    assert pl.read_csv(exportado, infer_schema=False).rows() == [("0001", "1,25")]


# Registro e schema -------------------------------------------------------------------------


def test_chaves_novas_e_modulo_de_specs() -> None:
    chaves = [s.descriptor.source for s in saude_leva7.build_sources()]
    assert chaves == [
        "iarc_ci5_xii", "iarc_monografias_classificacoes", "sb_brasil_1986", "sb_brasil_1996", "sb_brasil_2003", "pnds_2006",
        "covitel_2022", "covitel_2023", "cetic_tic_saude_estabelecimentos", "cetic_tic_domicilios",
    ]


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.key)
def test_chave_responde_no_schema(spec) -> None:
    schema = DownloadService(sources=saude_leva7.build_sources()).get_source_schema(spec.key)
    nomes = {p["name"] for p in schema["params"]}
    assert {"output_dir", "output_format", "keep_raw", "timeout"} <= nomes


def test_sb_2003_expoe_as_regioes_como_valores_permitidos() -> None:
    schema = DownloadService(sources=saude_leva7.build_sources()).get_source_schema("sb_brasil_2003")
    params = {p["name"]: p for p in schema["params"]}
    assert params["indicadores"]["allowed_values"] == ["co", "ne", "no", "se", "su"]


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.key)
def test_descricao_sem_travessao_e_com_origem(spec) -> None:
    for texto in (spec.title, spec.description):
        assert chr(0x2014) not in texto and chr(0x2013) not in texto
    assert len(spec.description) > 150


def test_licencas_e_termos_ficam_na_descricao() -> None:
    assert "CC BY 4.0" in tic.CETIC_TIC_SAUDE.description
    assert "CC BY 4.0" in tic.CETIC_TIC_DOMICILIOS.description
    assert "comercial" in ci5.IARC_CI5_XII.description
    assert "não é declarada" in covitel.COVITEL_2022.description
