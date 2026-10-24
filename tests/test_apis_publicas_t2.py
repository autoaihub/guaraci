"""Testes offline do SICOR, PNCP e Compras.gov.br (turno 2 do Pacote F), com cliente falso."""

from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest

from guaraci.bcb import SicorInvestimentoMunicipioDataSource
from guaraci.gestao_publica import ComprasCatmatSaudeDataSource, PncpContratacoesDataSource
from guaraci.gestao_publica.pncp import flatten, parse_date, windows
from guaraci.gestao_publica.rest import JsonApiClient
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import bcb, gestao_publica


class FakeSicor(JsonApiClient):
    def __init__(self, months):
        super().__init__("https://exemplo.invalid/odata")
        self.months = months
        self.calls = []

    def get_json(self, path="", params=None, *, headers=None):
        self.calls.append((path, dict(params)))
        assert "$skip" not in params
        return {"value": self.months.get(params["$filter"], [])}


def test_sicor_uma_requisicao_por_mes_sem_skip_e_pula_mes_vazio(tmp_path):
    f = SicorInvestimentoMunicipioDataSource.month_filter
    client = FakeSicor({
        f(2020, 1): [{"AnoEmissao": "2020", "MesEmissao": "01", "VlInvest": "10.50", "nomeProduto": '"TRATOR"'}],
        f(2020, 3): [{"AnoEmissao": "2020", "MesEmissao": "03", "VlInvest": "7", "extra": "x"}],
    })
    source = SicorInvestimentoMunicipioDataSource(output_path=str(tmp_path), client=client)
    result = source.download(start_year=2020, meses=["1", "2", "3"], output_dir=str(tmp_path))
    assert [c[1]["$filter"] for c in client.calls] == [f(2020, 1), f(2020, 2), f(2020, 3)]
    assert client.calls[0][0] == "InvestMunicipioProduto"
    assert result["rows"] == 2 and result["skipped_count"] == 1
    assert "2020-02" in result["export_warning"]
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame["MesEmissao"].to_list() == ["01", "03"]
    assert frame["VlInvest"].to_list() == ["10.50", "7"]
    assert frame["extra"].to_list() == [None, "x"]


def test_sicor_nao_consulta_mes_futuro_e_valida_anos(tmp_path):
    client = FakeSicor({})
    source = SicorInvestimentoMunicipioDataSource(output_path=str(tmp_path), client=client)
    ano = datetime.now().year + 1
    result = source.download(start_year=ano, output_dir=str(tmp_path))
    assert client.calls == [] and result["rows"] == 0
    with pytest.raises(ValueError):
        source.download(start_year=2012, output_dir=str(tmp_path))
    with pytest.raises(ValueError):
        source.download(start_year=2020, meses=["13"], output_dir=str(tmp_path))


def _contratacao(n, modalidade=6):
    return {
        "numeroControlePNCP": f"0001-1-{n:06d}/2026",
        "objetoCompra": f"Objeto {n}",
        "valorTotalEstimado": 10.5,
        "orgaoEntidade": {"cnpj": "00000000000191", "razaoSocial": "MUNICIPIO X"},
        "unidadeOrgao": {"ufSigla": "SP", "codigoIbge": "3550308"},
        "fontesOrcamentarias": [{"codigo": 1}],
        "emendaParlamentar": None,
        "modalidadeId": modalidade,
    }


class FakePncp(JsonApiClient):
    """3 contratações por (janela, modalidade 6), em páginas de 2; as demais modalidades dão 204."""

    def __init__(self):
        super().__init__("https://exemplo.invalid/consulta")
        self.calls = []

    def get_json(self, path="", params=None, *, headers=None):
        self.calls.append(dict(params))
        if params["codigoModalidadeContratacao"] != 6:
            return None
        rows = [_contratacao(i) for i in range(1, 4)]
        page = params["pagina"]
        chunk = rows[(page - 1) * 2: page * 2]
        if not chunk:
            return None
        return {"data": chunk, "totalRegistros": 3, "totalPaginas": 2, "numeroPagina": page}


def test_pncp_janelas_modalidades_paginas_e_achatamento(tmp_path):
    client = FakePncp()
    source = PncpContratacoesDataSource(output_path=str(tmp_path), client=client, sleep=lambda s: None)
    result = source.download(
        start_date="2026-09-01", end_date="20260915", modalidades=["6", "8"],
        janela_dias=7, output_dir=str(tmp_path),
    )
    # 15 dias em janelas de 7 -> 3 janelas; modalidade 6: 2 páginas, modalidade 8: 1 chamada (204)
    assert len(client.calls) == 3 * (2 + 1)
    assert {c["dataInicial"] for c in client.calls} == {"20260901", "20260908", "20260915"}
    assert {c["dataFinal"] for c in client.calls} == {"20260907", "20260914", "20260915"}
    assert all(c["tamanhoPagina"] == 50 for c in client.calls)
    # as mesmas 3 contratações voltam em cada janela: só 3 ficam
    assert result["rows"] == 3 and result["duplicates"] == 6
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert {"orgaoEntidade_cnpj", "unidadeOrgao_codigoIbge", "fontesOrcamentarias"} <= set(frame.columns)
    assert frame["orgaoEntidade_cnpj"][0] == "00000000000191"
    assert frame["fontesOrcamentarias"][0] == '[{"codigo":1}]'
    assert frame["emendaParlamentar"][0] is None


def test_pncp_validacoes_e_max_paginas(tmp_path):
    source = PncpContratacoesDataSource(output_path=str(tmp_path), client=FakePncp(), sleep=lambda s: None)
    with pytest.raises(ValueError):
        source.download(start_date="2026-09-02", end_date="2026-09-01", output_dir=str(tmp_path))
    with pytest.raises(ValueError):
        source.download(start_date="2026-09-01", modalidades=["99"], output_dir=str(tmp_path))
    result = source.download(
        start_date="2026-09-01", modalidades=[6], max_paginas=1, tamanho_pagina=500,
        output_dir=str(tmp_path),
    )
    assert result["rows"] == 2 and "max_paginas" in result["export_warning"]


def test_pncp_datas_e_janelas():
    assert parse_date("20260901") == date(2026, 9, 1) == parse_date("2026-09-01")
    with pytest.raises(ValueError):
        parse_date("01/09/2026")
    assert list(windows(date(2026, 9, 1), date(2026, 9, 1), 7)) == [(date(2026, 9, 1), date(2026, 9, 1))]
    assert flatten({"a": {"b": 1}, "c": [1]}) == {"a_b": 1, "c": [1]}


class FakeCompras(JsonApiClient):
    def __init__(self, pages):
        super().__init__("https://exemplo.invalid")
        self.pages = pages
        self.calls = []

    def get_json(self, path="", params=None, *, headers=None):
        self.calls.append(dict(params))
        items = self.pages[params["pagina"] - 1] if params["pagina"] <= len(self.pages) else []
        return {"resultado": items, "totalRegistros": 3, "totalPaginas": len(self.pages)}


def test_compras_catalogo_pagina_ate_totalpaginas(tmp_path):
    pages = [[{"codigoItem": "1", "descricaoItem": "A"}, {"codigoItem": "2", "descricaoItem": None}],
             [{"codigoItem": "3", "descricaoItem": "C", "codigo_ncm": "3004"}]]
    client = FakeCompras(pages)
    source = ComprasCatmatSaudeDataSource(output_path=str(tmp_path), client=client)
    result = source.download(codigo_classe=6505, output_dir=str(tmp_path))
    assert len(client.calls) == 2 and result["rows"] == 3
    assert client.calls[0]["codigoGrupo"] == 65 and client.calls[0]["codigoClasse"] == 6505
    assert client.calls[0]["tamanhoPagina"] == 500
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame["codigoItem"].to_list() == ["1", "2", "3"]
    assert frame["codigo_ncm"].to_list() == [None, None, "3004"]


def test_registros_respondem_schema():
    service = DownloadService(sources=bcb.build_sources() + gestao_publica.build_sources())
    for key in (
        "bcb_sicor_custeio_municipio", "bcb_sicor_investimento_municipio",
        "bcb_sicor_comercializacao_uf", "pncp_contratacoes", "compras_gov_catmat_saude",
    ):
        names = {p.name for p in service.get_source_schema(key).parameters} if hasattr(
            service.get_source_schema(key), "parameters") else None
        assert service.get_source_schema(key) is not None, key
        assert names is None or "output_format" in names
    assert service.get_source_schema("pncp_contratacoes") is not None
