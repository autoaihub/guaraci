"""Testes offline do Transferegov (PostgREST) e do Obrasgov, com cliente falso."""

from __future__ import annotations

import io
from urllib.error import HTTPError

import polars as pl
import pytest

from guaraci.core.http import ApiClientError
from guaraci.gestao_publica import (
    ObrasgovProjetosDataSource,
    TransferegovFundoAFundoDataSource,
    TransferegovTransferenciasEspeciaisDataSource,
)
from guaraci.gestao_publica import rest
from guaraci.gestao_publica.rest import JsonApiClient, JsonApiError
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import gestao_publica as registro

OPENAPI = {
    "paths": {
        "/": {},
        "/rpc/algo": {},
        "/plano": {},
        "/sem_chave": {},
    },
    "definitions": {
        "plano": {"properties": {
            "id_plano": {"description": "Note:\nThis is a Primary Key.<pk/>", "type": "integer"},
            "nome": {"type": "string"},
            "valor": {"type": "number"},
        }},
        "sem_chave": {"properties": {"a": {"type": "string"}, "b": {"type": "string"}}},
    },
}

PLANO = [
    {"id_plano": "1", "nome": "A", "valor": "55000.00000000"},
    {"id_plano": "2", "nome": None, "valor": "1.50"},
    {"id_plano": "3", "nome": "C", "valor": "0"},
]
SEM_CHAVE = [{"a": "x", "b": "1"}, {"a": "x", "b": "1"}]


class FakePostgrest(JsonApiClient):
    """Entrega o OpenAPI na raiz e as linhas em páginas de no máximo 2 (teto do servidor)."""

    def __init__(self):
        super().__init__("https://exemplo.invalid/base")
        self.calls = []

    def get_json(self, path="", params=None, *, headers=None):
        self.calls.append((path, dict(params or {}), dict(headers or {})))
        if path == "":
            assert headers and headers["Accept"] == "application/openapi+json"
            return OPENAPI
        rows = {"plano": PLANO, "sem_chave": SEM_CHAVE}[path]
        offset, limit = int(params["offset"]), min(int(params["limit"]), 2)
        return rows[offset:offset + limit]


def test_transferegov_pagina_ate_a_pagina_vazia_e_ordena_por_chave(tmp_path):
    client = FakePostgrest()
    source = TransferegovTransferenciasEspeciaisDataSource(output_path=str(tmp_path), client=client)
    result = source.download(output_dir=str(tmp_path))

    assert result["failed_count"] == 0
    assert result["rows_by_table"] == {"plano": 3, "sem_chave": 2}
    page_calls = [c for c in client.calls if c[0] == "plano"]
    # Teto de 2 por resposta: offsets 0, 2 e a página vazia em 3.
    assert [c[1]["offset"] for c in page_calls] == [0, 2, 3]
    assert all(c[1]["order"] == "id_plano.asc" for c in page_calls)
    # Sem chave primária, a ordem usa todas as colunas.
    sem_chave_calls = [c for c in client.calls if c[0] == "sem_chave"]
    assert sem_chave_calls[0][1]["order"] == "a.asc,b.asc"

    frame = pl.read_csv(tmp_path / "transferegov_transferencias_especiais_plano.csv", infer_schema=False)
    assert frame.columns == ["id_plano", "nome", "valor"]
    assert frame["valor"].to_list() == ["55000.00000000", "1.50", "0"]
    assert frame["nome"].to_list() == ["A", None, "C"]
    assert not list(tmp_path.glob("*.spool")) and not list(tmp_path.glob("*.part"))


def test_transferegov_tabelas_filtra_e_rejeita_desconhecida(tmp_path):
    source = TransferegovFundoAFundoDataSource(output_path=str(tmp_path), client=FakePostgrest())
    result = source.download(tabelas=["sem_chave"], output_dir=str(tmp_path))
    assert result["rows_by_table"] == {"sem_chave": 2}
    assert [p.name for p in tmp_path.glob("*.csv")] == ["transferegov_fundo_a_fundo_sem_chave.csv"]
    with pytest.raises(ValueError, match="desconhecida"):
        source.download(tabelas=["nao_existe"], output_dir=str(tmp_path))


def test_transferegov_falha_numa_tabela_nao_derruba_as_outras(tmp_path):
    class Quebra(FakePostgrest):
        def get_json(self, path="", params=None, *, headers=None):
            if path == "sem_chave":
                raise ApiClientError("boom", category="http_error", retryable=False)
            return super().get_json(path, params, headers=headers)

    source = TransferegovFundoAFundoDataSource(output_path=str(tmp_path), client=Quebra())
    result = source.download(output_dir=str(tmp_path))
    assert result["failed_count"] == 1
    assert result["rows_by_table"] == {"plano": 3}
    assert "sem_chave" in result["export_warning"]


def test_parse_openapi_ignora_raiz_e_rpc():
    tables = TransferegovFundoAFundoDataSource.parse_openapi(OPENAPI)
    assert list(tables) == ["plano", "sem_chave"]
    assert tables["plano"] == (["id_plano", "nome", "valor"], ["id_plano"])


# --- Obrasgov -------------------------------------------------------------


def _projeto(n, **extra):
    return {
        "idUnico": f"P{n}", "nome": f"Obra {n}", "uf": "SP", "cep": None,
        "executores": [{"nome": "Prefeitura", "codigo": "123"}], "isModeladaPorBim": False,
        **extra,
    }


class FakeObras(JsonApiClient):
    """Três páginas de 2 e depois vazia; ``totalElements`` mente, como a API real."""

    def __init__(self, pages):
        super().__init__("https://exemplo.invalid/obrasgov/api")
        self.pages = pages
        self.calls = []

    def get_json(self, path="", params=None, *, headers=None):
        self.calls.append((path, dict(params)))
        page = params["pagina"]
        content = self.pages[page] if page < len(self.pages) else []
        return {"content": content, "totalElements": len(content), "empty": not content}


def test_obrasgov_vai_ate_a_pagina_vazia_apesar_do_total_errado(tmp_path):
    pages = [[_projeto(1), _projeto(2)], [_projeto(3), _projeto(4)], [_projeto(5)]]
    client = FakeObras(pages)
    source = ObrasgovProjetosDataSource(output_path=str(tmp_path), client=client)
    result = source.download(output_dir=str(tmp_path), tamanho_pagina=2)

    assert [c[1]["pagina"] for c in client.calls] == [0, 1, 2, 3]
    assert all(c[1]["tamanhoDaPagina"] == 2 for c in client.calls)
    assert result["rows"] == 5 and result["pages"] == 3 and result["duplicates"] == 0
    frame = pl.read_csv(tmp_path / "obrasgov_projetos_investimento.csv", infer_schema=False)
    assert frame.height == 5
    assert frame["executores"][0] == '[{"nome":"Prefeitura","codigo":"123"}]'
    assert frame["isModeladaPorBim"][0] == "false"
    assert frame["cep"][0] is None


def test_obrasgov_descarta_repeticao_entre_paginas_e_une_colunas(tmp_path):
    pages = [[_projeto(1), _projeto(2)], [_projeto(2), _projeto(3, novoCampo="x")]]
    source = ObrasgovProjetosDataSource(output_path=str(tmp_path), client=FakeObras(pages))
    result = source.download(output_dir=str(tmp_path), tamanho_pagina=2)
    assert result["rows"] == 3 and result["duplicates"] == 1
    assert "repetido" in result["export_warning"]
    frame = pl.read_csv(tmp_path / "obrasgov_projetos_investimento.csv", infer_schema=False)
    assert "novoCampo" in frame.columns
    assert frame["novoCampo"].to_list() == [None, None, "x"]


def test_obrasgov_max_paginas_avisa(tmp_path):
    pages = [[_projeto(1)], [_projeto(2)], [_projeto(3)]]
    source = ObrasgovProjetosDataSource(output_path=str(tmp_path), client=FakeObras(pages))
    result = source.download(output_dir=str(tmp_path), max_paginas=2)
    assert result["rows"] == 2 and "max_paginas" in result["export_warning"]


def test_obrasgov_parquet(tmp_path):
    source = ObrasgovProjetosDataSource(output_path=str(tmp_path), client=FakeObras([[_projeto(1)]]))
    result = source.download(output_dir=str(tmp_path), output_format="parquet")
    assert result["exported_files"] == [str(tmp_path / "obrasgov_projetos_investimento.parquet")]
    assert pl.read_parquet(result["exported_files"][0]).height == 1
    assert not (tmp_path / "obrasgov_projetos_investimento.csv").exists()


# --- Cliente e registro ----------------------------------------------------


def test_cliente_classifica_erro_http_e_numeros_ficam_texto(monkeypatch):
    def boom(request, timeout):
        raise HTTPError(request.full_url, 500, "x", {}, io.BytesIO(b""))

    monkeypatch.setattr(rest, "urlopen", boom)
    with pytest.raises(JsonApiError) as info:
        JsonApiClient("https://exemplo.invalid", max_attempts=1).get_json("x")
    assert info.value.retryable is True

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(rest, "urlopen", lambda request, timeout: Resp(b'{"v": 55000.00000000, "n": 7}'))
    assert JsonApiClient("https://exemplo.invalid").get_json("x") == {"v": "55000.00000000", "n": "7"}


def test_registro_responde_schema_das_tres_chaves():
    service = DownloadService(sources=registro.build_sources())
    for key in (
        "transferegov_transferencias_especiais",
        "transferegov_fundo_a_fundo",
        "obrasgov_projetos_investimento",
    ):
        assert service.get_source_schema(key)
