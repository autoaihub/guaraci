"""Indicadores INEP, tabelas do Censo Escolar 2025 e IDEB de escola e Brasil/UFs, sem rede.

Os casos que valem teste dariam dado plausível e errado: cabeçalho de edição antiga (nomes
curtos em minúsculas) lido como dado, tabela de matrícula trocada por outra do mesmo zip,
ano anterior a 2025 aceito para as tabelas novas e nível BR confundido com UF no IDEB.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from guaraci.arquivos import inep_ideb, inep_indicadores
from guaraci.arquivos.inep_censo_escolar import (
    INEP_CENSO_ESCOLAR_TABELAS,
    tabela_datasource_for,
    year_url,
)
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import trabalho_educacao
from tests.test_arquivos_ext_a import _workbook
from tests.test_arquivos_http import _Client, _zip
from tests.test_inep_censo_escolar import _Client as _CensoClient
from tests.test_inep_censo_escolar import _zip as _censo_zip

_TITULO = [["Taxas de rendimento"], ["Fonte: INEP"], ["Brasil"]]


def test_header_skip_acha_nomes_tecnicos_em_maiusculas(tmp_path: Path) -> None:
    path = tmp_path / "a.xlsx"
    _workbook(path, {"P": _TITULO + [["NU_ANO_CENSO", "CO_MUNICIPIO"], ["2023", "1100015"]]})
    assert inep_indicadores.header_skip(path, "P") == 3


def test_header_skip_edicao_antiga_usa_a_linha_antes_do_primeiro_ano(tmp_path: Path) -> None:
    path = tmp_path / "b.xlsx"
    _workbook(path, {"P": _TITULO + [["ano", "tap_FUN"], ["2014", "93,1"]]})
    assert inep_indicadores.header_skip(path, "P") == 3


def test_header_skip_sem_cabecalho_falha_alto(tmp_path: Path) -> None:
    path = tmp_path / "c.xlsx"
    _workbook(path, {"P": [["so texto"], ["mais texto"]]})
    with pytest.raises(ValueError):
        inep_indicadores.header_skip(path, "P")


def test_indicador_exporta_edicao_antiga_com_cabecalho_certo(tmp_path: Path) -> None:
    path = tmp_path / "d.xlsx"
    _workbook(path, {"P": _TITULO + [["ano", "tap_FUN"], ["2014", "93,1"]]})
    spec = next(s for s in inep_indicadores.SPECS if s.key == "inep_taxas_rendimento")
    resource = next(r for r in spec.resources if r.code == "2018_UF")
    archive = _zip({"x/tx.xlsx": path.read_bytes()})
    out = tmp_path / "out"
    ds = inep_indicadores.DATASOURCES[spec.key](
        output_path=str(out), client=_Client({resource.url: archive})
    )
    ds.download(output_dir=str(out), output_format="csv", anos=[2018], meses=["UF"])
    frame = pl.read_csv(out / "inep_taxas_rendimento_2018_UF.csv", infer_schema=False)
    assert frame.columns == ["ano", "tap_FUN"]
    assert frame.rows() == [("2014", "93,1")]


def test_so_ha_indicadores_com_urls_do_inep_e_codigo_ano_nivel() -> None:
    assert len(inep_indicadores.SPECS) == 10
    for spec in inep_indicadores.SPECS:
        assert spec.resources
        for r in spec.resources:
            assert r.url.startswith("https://download.inep.gov.br/informacoes_estatisticas/")
            assert r.code[:4].isdigit()


def test_censo_tabelas_pega_so_a_tabela_pedida_e_recusa_ano_antigo(tmp_path: Path) -> None:
    zipped = _censo_zip(
        {
            "m/dados/Tabela_Docente_2025_V2.csv": "A;B\n9;9\n".encode("cp1252"),
            "m/dados/Tabela_Matricula_2025_V2.csv": "NU_ANO_CENSO;QT_MAT_BAS\n2025;12\n".encode(
                "cp1252"
            ),
            "m/dados/Tabela_Gestor_Escolar_2025_v2.csv": "A;B\n8;8\n".encode("cp1252"),
        }
    )
    client = _CensoClient({year_url(2025): zipped})
    source = tabela_datasource_for("inep_censo_escolar_matricula")(
        output_path=str(tmp_path), client=client
    )
    payload = source.download(output_dir=str(tmp_path), output_format="csv", start_year=2025)
    (exported,) = payload["exported_files"]
    assert Path(exported).name == "inep_censo_escolar_matricula.csv"
    assert pl.read_csv(exported, infer_schema=False).rows() == [("2025", "12")]
    gestor = tabela_datasource_for("inep_censo_escolar_gestor")(
        output_path=str(tmp_path), client=client
    )
    out = gestor.download(output_dir=str(tmp_path), output_format="csv", start_year=2025)
    assert pl.read_csv(out["exported_files"][0], infer_schema=False).rows() == [("8", "8")]
    with pytest.raises(ValueError):
        source.download(output_dir=str(tmp_path), output_format="csv", start_year=2024)


def test_registra_dezessete_chaves_com_schema() -> None:
    sources = trabalho_educacao.build_sources()
    service = DownloadService(sources=sources)
    keys = [s.descriptor.source for s in sources]
    assert len(keys) == 17 and len(set(keys)) == 17
    assert set(INEP_CENSO_ESCOLAR_TABELAS) <= set(keys)
    for key in keys:
        service.get_source_schema(key)


def test_ideb_escolas_e_brasil_ufs_tem_url_e_codigos_certos(tmp_path: Path) -> None:
    assert inep_ideb.escolas_url(2025, "ensino_medio").endswith(
        "ideb/resultados/divulgacao_ensino_medio_escolas_2025.zip"
    )
    assert "portal_ideb/planilhas_para_download/2021/" in inep_ideb.escolas_url(2021, "anos_finais")
    codes = {r.code for r in inep_ideb.INEP_IDEB_BRASIL_UFS.resources}
    assert codes == {f"{y}_{n}" for y in inep_ideb.ANOS for n in ("BR", "UF")}
    assert len(inep_ideb.INEP_IDEB_ESCOLAS.resources) == 12
    assert inep_ideb.brasil_url(2023).endswith("divulgacao_brasil_ideb_2023.zip")
    assert inep_ideb.ufs_url(2023).endswith("divulgacao_regioes_ufs_ideb_2023.zip")
    assert set(inep_ideb.MODES) == {s.key for s in inep_ideb.SPECS}


class _FakeSiconfi:
    """Só responde sem ``no_anexo``: com ele, o código novo estaria pedindo anexo a anexo."""

    base_url = "https://exemplo.invalid/tt"

    def __init__(self, nomes) -> None:
        self.nomes = nomes
        self.calls = []

    def paginate(self, path, params):
        self.calls.append((path, dict(params)))
        assert "no_anexo" not in params
        for nome in self.nomes:
            yield {
                "exercicio": params["an_exercicio"], "instituicao": "X", "cod_ibge": 1,
                "uf": "SP", "anexo": nome, "rotulo": "r", "coluna": "c", "cod_conta": "k",
                "conta": "10 - Saúde", "valor": 1.5, "populacao": 10, "periodo": 6,
            }

    def list_entes(self):
        return []


def test_dca_todos_os_anexos_aceita_com_e_sem_prefixo_e_filtra_localmente(tmp_path) -> None:
    from guaraci.tesouro.anexos import SiconfiDcaAnexosDataSource

    client = _FakeSiconfi(["Anexo I-E", "DCA-Anexo I-AB", "DCA-Anexo I-C"])
    source = SiconfiDcaAnexosDataSource(output_path=str(tmp_path), client=client)
    out = source.download(
        start_year=2013, entes=["1"], output_dir=str(tmp_path), anexos=["i-e", "I-AB"]
    )
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert sorted(frame["anexo"].to_list()) == ["Anexo I-E", "DCA-Anexo I-AB"]
    assert frame["conta"].to_list() == ["10 - Saúde"] * 2  # sem filtro de função
    assert len(client.calls) == 1  # uma consulta por ente e ano
    with pytest.raises(ValueError):
        source.download(start_year=2012, entes=["1"], output_dir=str(tmp_path))


def test_rreo_todos_os_anexos_sem_filtro_de_conta(tmp_path) -> None:
    from guaraci.tesouro.anexos import SiconfiRreoAnexosDataSource

    client = _FakeSiconfi(["RREO-Anexo 01", "RREO-Anexo 10 - RPPS"])
    source = SiconfiRreoAnexosDataSource(output_path=str(tmp_path), client=client)
    out = source.download(
        start_year=2022, periodos=[6], entes=["1"], output_dir=str(tmp_path)
    )
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame["anexo"].to_list() == ["RREO-Anexo 01", "RREO-Anexo 10 - RPPS"]
    out = source.download(
        start_year=2022, periodos=[6], entes=["1"], output_dir=str(tmp_path), anexos=["10 - rpps"]
    )
    assert pl.read_csv(out["exported_files"][0], infer_schema=False)["anexo"].to_list() == [
        "RREO-Anexo 10 - RPPS"
    ]
