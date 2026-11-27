"""Tabelas oficiais de códigos (``guaraci/referencias``), sem rede."""

from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl
import pytest

from guaraci.referencias import (
    Cid10DataSource,
    CnaeSubclassesDataSource,
    IbgeMunicipiosDataSource,
    SigtapDataSource,
    TseMunicipiosDataSource,
)
from guaraci.referencias import ibge_json, sigtap, zip_csv
from guaraci.referencias.ibge_json import achatar
from guaraci.referencias.sigtap import ler_layout, listar_competencias
from guaraci.services.sources import referencias

CHAVES = {
    "ibge_localidades_municipios",
    "ibge_localidades_distritos",
    "sigtap_tabela_unificada",
    "cid10_datasus",
    "cnae_subclasses",
    "cnae_classes",
    "tse_municipios_ibge",
}


def test_specs_trazem_as_chaves_sem_repeticao():
    fontes = referencias.build_sources()
    chaves = [f.descriptor.source for f in fontes]
    assert set(chaves) == CHAVES
    assert len(chaves) == len(set(chaves))


def test_specs_rejeitam_parametro_desconhecido():
    fonte = next(f for f in referencias.build_sources() if f.descriptor.source == "sigtap_tabela_unificada")
    fonte.validate_params({"competencia": "202611", "tabelas": ["tb_cid", "tb_ocupacao"]})
    with pytest.raises(Exception):
        fonte.validate_params({"parametro_inventado": 1})


def test_achatar_junta_chaves_e_troca_hifen():
    item = {"id": 1, "regiao-imediata": {"id": 2, "uf": {"sigla": "RO"}}, "obs": ["a", "b"], "vazio": None}
    assert dict(achatar(item)) == {
        "id": 1, "regiao_imediata_id": 2, "regiao_imediata_uf_sigla": "RO",
        "obs": ["a", "b"], "vazio": None,
    }


def test_municipios_gravam_csv_achatado(tmp_path, monkeypatch):
    payload = [
        {"id": 1100015, "nome": "Alta Floresta D'Oeste",
         "microrregiao": {"id": 11006, "nome": "Cacoal"},
         "regiao-imediata": {"id": 110005, "nome": "Cacoal"}},
        {"id": 1100023, "nome": "Ariquemes", "microrregiao": None,
         "regiao-imediata": {"id": 110002, "nome": "Ariquemes"}},
    ]
    monkeypatch.setattr(ibge_json.IbgeSidraClient, "_request_json", lambda self, url: payload)
    out = IbgeMunicipiosDataSource(str(tmp_path)).download(output_dir=str(tmp_path))
    assert out["rows"] == 2
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.columns == [
        "id", "nome", "microrregiao_id", "microrregiao_nome", "regiao_imediata_id", "regiao_imediata_nome",
    ]
    assert frame["id"].to_list() == ["1100015", "1100023"]
    assert frame["microrregiao_id"].to_list() == ["11006", None]


def test_cnae_lista_vira_texto_json(tmp_path, monkeypatch):
    payload = [{"id": "0111301", "descricao": "CULTIVO DE ARROZ", "classe": {"id": "01113"}, "observacoes": ["x"]}]
    monkeypatch.setattr(ibge_json.IbgeSidraClient, "_request_json", lambda self, url: payload)
    out = CnaeSubclassesDataSource(str(tmp_path)).download(output_dir=str(tmp_path))
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame["id"].to_list() == ["0111301"]
    assert frame["observacoes"].to_list() == ['["x"]']


def test_resposta_que_nao_e_lista_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(ibge_json.IbgeSidraClient, "_request_json", lambda self, url: {"erro": 1})
    with pytest.raises(ValueError):
        IbgeMunicipiosDataSource(str(tmp_path)).download(output_dir=str(tmp_path))


def _zip_com(path: Path, membros: dict) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for nome, conteudo in membros.items():
            zf.writestr(nome, conteudo)


def test_cid10_decodifica_latin1_e_descarta_coluna_final_vazia(tmp_path, monkeypatch):
    origem = tmp_path / "cid.zip"
    _zip_com(origem, {
        "CID-10-CAPITULOS.CSV": "NUMCAP;CATINIC;DESCRICAO;\r\n1;A00;Capítulo I\r\n".encode("latin-1"),
        "leiame.txt": b"ignorado",
    })
    monkeypatch.setattr(zip_csv.HttpFileClient, "download", lambda self, url, dest, **kw: dest.write_bytes(origem.read_bytes()))
    saida = tmp_path / "out"
    out = Cid10DataSource(str(saida)).download(output_dir=str(saida))
    assert out["rows"] == 1 and len(out["exported_files"]) == 1
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.columns == ["NUMCAP", "CATINIC", "DESCRICAO"]
    assert frame["DESCRICAO"].to_list() == ["Capítulo I"]
    assert not list(saida.glob("*.spool")) and not [p for p in saida.iterdir() if p.is_dir()]


def test_tse_mantem_codigo_com_zero_a_esquerda(tmp_path, monkeypatch):
    origem = tmp_path / "tse.zip"
    _zip_com(origem, {
        "municipio_tse_ibge.csv": '"CD_MUNICIPIO_TSE";"CD_MUNICIPIO_IBGE"\r\n"01007";1200138\r\n'.encode("latin-1"),
        "leiame.pdf": b"%PDF",
    })
    monkeypatch.setattr(zip_csv.HttpFileClient, "download", lambda self, url, dest, **kw: dest.write_bytes(origem.read_bytes()))
    out = TseMunicipiosDataSource(str(tmp_path / "o")).download(output_dir=str(tmp_path / "o"))
    assert Path(out["exported_files"][0]).name == "tse_municipios_ibge.csv"
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame["CD_MUNICIPIO_TSE"].to_list() == ["01007"]


LAYOUT_OCUPACAO = "Coluna,Tamanho,Inicio,Fim,Tipo\r\nCO_OCUPACAO,6,1,6,CHAR\r\nNO_OCUPACAO,20,7,26,VARCHAR2\r\n"


def test_ler_layout():
    assert ler_layout(LAYOUT_OCUPACAO) == [("CO_OCUPACAO", 0, 6), ("NO_OCUPACAO", 6, 26)]


def _fake_sigtap(monkeypatch, tmp_path: Path) -> Path:
    zpath = tmp_path / "sigtap.zip"
    _zip_com(zpath, {
        "tb_ocupacao_layout.txt": LAYOUT_OCUPACAO.encode("latin-1"),
        "tb_ocupacao.txt": ("010105" + "Oficial General".ljust(20) + "\r\n010110" + "Oficial do Exército".ljust(20) + "\r\n").encode("latin-1"),
        "tb_cid_layout.txt": b"Coluna,Tamanho,Inicio,Fim,Tipo\r\nCO_CID,4,1,4,VARCHAR2\r\n",
        "tb_cid.txt": b"A000\r\n",
        "tb_orfa_layout.txt": b"Coluna,Tamanho,Inicio,Fim,Tipo\r\nX,1,1,1,CHAR\r\n",
        "versao": b"1.1",
    })
    monkeypatch.setattr(sigtap, "listar_competencias", lambda **kw: {"202610": "a.zip", "202611": "TabelaUnificada_202611_v1.zip"})
    monkeypatch.setattr(sigtap.HttpFileClient, "download", lambda self, url, dest, **kw: (dest.write_bytes(zpath.read_bytes()), 0)[1])
    return zpath


def test_sigtap_largura_fixa_com_competencia_mais_recente(tmp_path, monkeypatch):
    _fake_sigtap(monkeypatch, tmp_path)
    saida = tmp_path / "o"
    out = SigtapDataSource(str(saida)).download(output_dir=str(saida), tabelas=["tb_ocupacao"])
    assert out["rows"] == 2
    assert out["source_url"].endswith("TabelaUnificada_202611_v1.zip")
    arquivo = Path(out["exported_files"][0])
    assert arquivo.name == "sigtap_tabela_unificada_202611_tb_ocupacao.csv"
    frame = pl.read_csv(arquivo, infer_schema=False)
    assert frame.to_dicts() == [
        {"CO_OCUPACAO": "010105", "NO_OCUPACAO": "Oficial General"},
        {"CO_OCUPACAO": "010110", "NO_OCUPACAO": "Oficial do Exército"},
    ]


def test_sigtap_sem_tabelas_traz_so_as_que_tem_arquivo_e_layout(tmp_path, monkeypatch):
    _fake_sigtap(monkeypatch, tmp_path)
    saida = tmp_path / "o"
    out = SigtapDataSource(str(saida)).download(output_dir=str(saida))
    assert sorted(Path(p).name for p in out["exported_files"]) == [
        "sigtap_tabela_unificada_202611_tb_cid.csv",
        "sigtap_tabela_unificada_202611_tb_ocupacao.csv",
    ]


def test_sigtap_rejeita_competencia_ausente_e_tabela_desconhecida(tmp_path, monkeypatch):
    _fake_sigtap(monkeypatch, tmp_path)
    fonte = SigtapDataSource(str(tmp_path / "o"))
    with pytest.raises(ValueError, match="não está no FTP"):
        fonte.download(output_dir=str(tmp_path / "o"), competencia="199001")
    with pytest.raises(ValueError, match="AAAAMM"):
        fonte.download(output_dir=str(tmp_path / "o"), competencia="2026-11")
    with pytest.raises(ValueError, match="inexistentes"):
        fonte.download(output_dir=str(tmp_path / "o"), tabelas=["tb_nao_existe"])


def test_listar_competencias_fica_com_a_versao_mais_nova(monkeypatch):
    nomes = [
        "/pub/x/TabelaUnificada_202611_v2611051737.zip",
        "/pub/x/TabelaUnificada_202611_v2611031000.zip",
        "/pub/x/TabelaUnificada_202610_v2610271043.zip",
        "/pub/x/sigtap-setup-1.4.exe",
    ]

    class FakeFtp:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self): ...
        def nlst(self, directory): return nomes

    monkeypatch.setattr(sigtap.ftplib, "FTP", FakeFtp)
    assert listar_competencias() == {
        "202610": "TabelaUnificada_202610_v2610271043.zip",
        "202611": "TabelaUnificada_202611_v2611051737.zip",
    }
