"""Pacote A, turno 2: fontes de arquivo que usam as extensões de ``http_files.py``, sem rede.

Cobre: descoberta do zip mais novo no índice HTML do IBGE, xlsx com preâmbulo e abas por
recurso, xlsx embrulhado em zip (IDEB), etapa no sufixo do período e o schema de cada chave.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict

import polars as pl
import pytest

from guaraci.arquivos import HttpFile, HttpResource, datasource_for_spec, ibge_ftp, inep_ideb
from guaraci.arquivos import cgu, mapbiomas, seguranca
from guaraci.arquivos.http_files import _period_token
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import arquivos as sources_arquivos
from tests.test_arquivos_ext_a import _PREAMBULO, _workbook
from tests.test_arquivos_http import _Client, _zip

_INDICE = """
<a href="?C=N;O=D">Name</a>
<a href="Agregados_por_setores_alfabetizacao_BR.zip">x</a>
<a href="Agregados_por_setores_basico_BR_20250101.zip">velho</a>
<a href="Agregados_por_setores_basico_BR_20260520.zip">novo</a>
<a href="Agregados_por_setores_caracteristicas_domicilio1_BR_20261021.zip">x</a>
<a href="Agregados_por_setores_cor_ou_raca_BR.zip">x</a>
<a href="Agregados_por_municipios_basico_BR_20260520.zip">outro nivel</a>
<a href="Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip">renda</a>
<a href="Agregados_por_setores_renda_responsavel_BR_20260508_xlsx.zip">renda xlsx</a>
"""
_BASE = ibge_ftp._SETORES + "Agregados_por_Setor_csv/"


def test_latest_files_pega_a_edicao_mais_nova_e_ignora_outro_nivel() -> None:
    found = ibge_ftp.latest_files(_INDICE, "setores")
    assert found["basico"] == "Agregados_por_setores_basico_BR_20260520.zip"
    assert found["alfabetizacao"] == "Agregados_por_setores_alfabetizacao_BR.zip"
    assert found["caracteristicas_domicilio1"].endswith("_20261021.zip")
    assert "renda_responsavel" not in found  # sufixo _csv/_xlsx exige o parâmetro suffix


def test_latest_files_com_sufixo_separa_csv_de_xlsx() -> None:
    found = ibge_ftp.latest_files(_INDICE, "setores", "_csv")
    assert found == {
        "renda_responsavel": "Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip"
    }


def _censo(tmp_path: Path, nivel: str = "setor", files: Dict[str, bytes] = None):
    zipped = _zip({"Agregados_por_setores_basico_BR.csv": 'CD_SETOR;NM\n"1";"Rondônia"\n'.encode("cp1252")})
    url = _BASE + "Agregados_por_setores_basico_BR_20260520.zip"
    client = _Client(files or {url: zipped})
    source = ibge_ftp.IbgeCensoSetoresDataSource(
        output_path=str(tmp_path), client=client, fetch=lambda _u: _INDICE
    )
    return source, client, url


def test_censo_descobre_o_zip_e_exporta_utf8(tmp_path: Path) -> None:
    source, client, url = _censo(tmp_path)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv", indicadores=["basico"]
    )
    assert client.downloads == 1
    assert payload["source_url"] == url
    out = tmp_path / "ibge_censo2022_setores_basico.csv"
    assert pl.read_csv(out, infer_schema=False).rows() == [("1", "Rondônia")]


def test_censo_nivel_municipio_usa_a_pasta_e_o_plural_do_nivel(tmp_path: Path) -> None:
    asked = []
    url = ibge_ftp._SETORES + "Agregados_por_Municipio_csv/Agregados_por_municipios_basico_BR_20260520.zip"
    zipped = _zip({"m.csv": b"CD_MUN;NM\n1;a\n"})
    source = ibge_ftp.IbgeCensoSetoresDataSource(
        output_path=str(tmp_path),
        client=_Client({url: zipped}),
        fetch=lambda u: asked.append(u) or _INDICE,
    )
    source.download(
        output_dir=str(tmp_path), output_format="csv", indicadores=["basico"], nivel="municipio"
    )
    assert asked == [ibge_ftp._SETORES + "Agregados_por_Municipio_csv/"]
    assert (tmp_path / "ibge_censo2022_setores_municipio_basico.csv").exists()


def test_censo_nivel_invalido_e_tema_nao_listado_dao_erro(tmp_path: Path) -> None:
    source, _client, _url = _censo(tmp_path)
    with pytest.raises(ValueError, match="Unknown nivel"):
        source.download(output_dir=str(tmp_path), nivel="regiao")
    with pytest.raises(ValueError, match="não listados"):
        source.download(output_dir=str(tmp_path), indicadores=["obitos"])
    with pytest.raises(ValueError, match="Unknown indicadores"):
        source.download(output_dir=str(tmp_path), indicadores=["nao_existe"])


def test_renda_usa_a_pasta_unica_e_o_sufixo_csv(tmp_path: Path) -> None:
    url = ibge_ftp._RENDA + "Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip"
    asked = []
    source = ibge_ftp.IbgeCensoRendaDataSource(
        output_path=str(tmp_path),
        client=_Client({url: _zip({"r.csv": b"CD_SETOR;V06001\n1;2\n"})}),
        fetch=lambda u: asked.append(u) or _INDICE,
    )
    source.download(output_dir=str(tmp_path), output_format="csv")
    assert asked == [ibge_ftp._RENDA]
    assert (tmp_path / "ibge_censo2022_renda_responsavel.csv").exists()


def _projecoes_like(tmp_path: Path) -> bytes:
    path = tmp_path / "p.xlsx"
    _workbook(
        path,
        {
            "1) TAB": _PREAMBULO + [["IDADE", "SEXO", "2000"], ["0", "Ambos", 10]],
            "NOTAS": [["Fonte: IBGE"]],
        },
    )
    return path.read_bytes()


def test_xlsx_skip_rows_e_sheets_por_recurso(tmp_path: Path) -> None:
    url = "http://x/p.xlsx"
    spec = HttpFile(
        "teste_a2",
        "t",
        "d",
        (HttpResource("tab", url, skip_rows=2, sheets=("1) TAB",)),),
        file_format="xlsx",
        selector="indicadores",
    )
    out = tmp_path / "out"
    payload = datasource_for_spec(spec)(
        output_path=str(out), client=_Client({url: _projecoes_like(tmp_path)})
    ).download(output_dir=str(out), output_format="csv")
    assert [Path(p).name for p in payload["exported_files"]] == ["teste_a2.csv"]
    frame = pl.read_csv(out / "teste_a2.csv", infer_schema=False)
    assert frame.columns == ["IDADE", "SEXO", "2000"]
    assert frame.rows() == [("0", "Ambos", "10")]


def test_xlsx_dentro_de_zip_com_ods_e_md5_extrai_so_o_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "w.xlsx"
    _workbook(path, {"IDEB": _PREAMBULO + [["SG_UF", "CO_MUNICIPIO"], ["RO", "1100015"]]})
    url = "http://x/divulgacao_anos_finais_municipios_2025.zip"
    archive = _zip(
        {
            "div/divulgacao.ods": b"nao e xlsx",
            "div/divulgacao.xlsx": path.read_bytes(),
            "div/md5_divulgacao.txt": b"abc",
        }
    )
    spec = HttpFile(
        "teste_ideb",
        "t",
        "d",
        (HttpResource("2025_AF", url), HttpResource("2023_AF", url + "2")),
        file_format="xlsx",
        skip_rows=2,
        member_pattern=r"\.xlsx$",
        selector="periodo",
        period_required=False,
    )
    out = tmp_path / "out"
    datasource_for_spec(spec)(
        output_path=str(out), client=_Client({url: archive, url + "2": archive})
    ).download(output_dir=str(out), output_format="csv", anos=[2025], meses=["af"])
    assert sorted(p.name for p in out.glob("*.csv")) == ["teste_ideb_2025_AF.csv"]
    assert pl.read_csv(out / "teste_ideb_2025_AF.csv", infer_schema=False).rows() == [
        ("RO", "1100015")
    ]
    assert not list(out.glob("*.tmp.*"))


def test_period_token_aceita_etapa_alem_de_mes_e_semestre() -> None:
    assert _period_token("af") == "AF"
    assert _period_token("S1") == "S1"
    assert _period_token("3") == "03"
    assert _period_token(7) == "07"


NOVAS = (
    "mdhc_ligue180",
    "ibge_censo2022_setores",
    "ibge_censo2022_renda_responsavel",
    "ibge_projecoes_populacao_2024",
    "ibge_munic",
    "inep_ideb_municipios",
    "mapbiomas_cobertura_municipios",
    "mapbiomas_vegetacao_secundaria_municipios",
    "cgu_novo_bolsa_familia",
    "cgu_bpc",
    "cgu_despesas_execucao",
    "cgu_transferencias",
    "cgu_emendas_parlamentares",
)


@pytest.mark.parametrize("key", NOVAS)
def test_chave_nova_responde_no_schema(key: str) -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema(key)
    names = {p["name"] for p in schema["params"]}
    assert {"output_dir", "output_format", "timeout"} <= names


def test_schema_do_censo_tem_nivel_e_temas() -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema(
        "ibge_censo2022_setores"
    )
    params = {p["name"]: p for p in schema["params"]}
    assert params["nivel"]["default"] == "setor"
    assert set(params["nivel"]["allowed_values"]) == set(ibge_ftp.NIVEIS)
    assert "basico" in params["indicadores"]["allowed_values"]


def test_schema_do_ideb_tem_etapas_e_nao_exige_anos() -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema(
        "inep_ideb_municipios"
    )
    params = {p["name"]: p for p in schema["params"]}
    assert params["anos"]["required"] is False
    assert params["anos"]["allowed_values"] == ["2019", "2021", "2023", "2025"]
    assert params["meses"]["allowed_values"] == ["AF", "AI", "EM"]
    assert "AI = anos iniciais" in params["meses"]["description"]


def test_listas_congeladas_do_turno_2() -> None:
    ligue = seguranca.MDHC_LIGUE180.resources
    assert [r.code for r in ligue][0] == "2020_S1" and [r.code for r in ligue][-1] == "2024_S1"
    assert len(ligue) == 9 and seguranca.MDHC_LIGUE180.probe == "range"
    assert ligue[0].url == "https://dadosabertos.mdh.gov.br/ligue180-primeiro-semestre-2020.csv"
    assert len(inep_ideb.INEP_IDEB_MUNICIPIOS.resources) == 12
    assert inep_ideb.resource_url(2023, "ensino_medio") == (
        "https://download.inep.gov.br/ideb/resultados/divulgacao_ensino_medio_municipios_2023.zip"
    )
    assert inep_ideb.resource_url(2021, "anos_finais").startswith(
        "https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/2021/"
    )
    tabs = {r.code: r for r in ibge_ftp.IBGE_PROJECOES_POPULACAO_2024.resources}
    assert [tabs[c].skip_rows for c in ("tab1", "tab2", "tab3", "tab4", "tab5")] == [4, 4, 5, 5, 4]
    assert tabs["tab4"].sheets == ("4) INDICADORES",)


def test_mapbiomas_traz_origem_licenca_e_citacao() -> None:
    for spec in mapbiomas.SPECS:
        assert "CC BY 4.0" in spec.description
        assert "Projeto MapBiomas" in spec.description
        assert "Landsat" in spec.description
        assert spec.sheets and len(spec.sheets) == 1


def test_cgu_competencia_mais_nova_e_m_menos_2() -> None:
    from datetime import date

    assert cgu.latest_competencia(date(2026, 10, 23)) == (2026, 8)
    assert cgu.latest_competencia(date(2026, 1, 5)) == (2025, 11)
    assert cgu.competencias((2023, 11), (2024, 2)) == [(2023, 11), (2023, 12), (2024, 1), (2024, 2)]


def test_cgu_monta_url_por_competencia_com_pisos_medidos() -> None:
    bf = cgu.CGU_NOVO_BOLSA_FAMILIA.resources
    assert bf[0].code == "2023_03" and bf[0].url.endswith(
        "/novo-bolsa-familia/202303_NovoBolsaFamilia.zip"
    )
    assert cgu.CGU_BPC.resources[0].code == "2019_01"
    assert cgu.CGU_DESPESAS_EXECUCAO.resources[0].url.endswith("/despesas-execucao/201401_Despesas.zip")
    assert cgu.CGU_TRANSFERENCIAS.resources[0].code == "2014_01"
    last = cgu.latest_competencia()
    assert bf[-1].code == f"{last[0]}_{last[1]:02d}"
    assert cgu.CGU_EMENDAS_PARLAMENTARES.members_pattern


def test_cgu_schema_exige_anos_e_aceita_meses_numericos() -> None:
    schema = DownloadService(sources=sources_arquivos.build_sources()).get_source_schema("cgu_bpc")
    params = {p["name"]: p for p in schema["params"]}
    assert params["anos"]["required"] is True and "130 a 190 MB" in params["anos"]["description"]
    assert params["meses"]["allowed_values"][0] == "01" and {"start_year", "end_year"} <= set(params)


def test_cgu_emendas_exporta_um_csv_por_membro(tmp_path: Path) -> None:
    url = cgu.CGU_EMENDAS_PARLAMENTARES.resources[0].url
    archive = _zip(
        {
            "EmendasParlamentares.csv": b"a;b\n1;2\n",
            "EmendasParlamentares_Convenios.csv": b"c\n3\n",
        }
    )
    out = tmp_path / "out"
    payload = datasource_for_spec(cgu.CGU_EMENDAS_PARLAMENTARES)(
        output_path=str(out), client=_Client({url: archive})
    ).download(output_dir=str(out), output_format="csv")
    assert sorted(Path(p).name for p in payload["exported_files"]) == [
        "cgu_emendas_parlamentares_EmendasParlamentares.csv",
        "cgu_emendas_parlamentares_EmendasParlamentares_Convenios.csv",
    ]


def test_descricoes_com_dado_pessoal_do_turno_2_trazem_a_nota_padrao() -> None:
    for spec in cgu.SPECS:
        assert "Traz identificador pessoal" in spec.description
