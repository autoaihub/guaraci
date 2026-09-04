"""Regressão: recorte de UF que a origem aceita e ignora.

Verificado ao vivo em 2026-09-03 contra
``/atencao-primaria/cadastro-vinculado-programa-previne-brasil``: o endpoint
responde 200 para qualquer valor de UF, com qualquer um dos nomes de parâmetro
que declara, e devolve sempre as mesmas linhas. Pela CLI, um pedido de SP
trazia 200 registros de 11 unidades da federação diferentes.

O recorte passa a ser reconferido nas linhas devolvidas, mas só quando elas
trazem uma sigla reconhecível: sem essa guarda, um recorte sobre uma resposta
sem coluna de UF trocaria um resultado largo demais por um resultado vazio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.opendatasus.datasource import OpenDataSUSDataSource


class _ClienteQueIgnoraOFiltro:
    """Devolve linhas de várias UFs, seja qual for o filtro pedido."""

    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self, linhas: list[dict], campo_chave: str = "records") -> None:
        self.linhas = linhas
        self.campo_chave = campo_chave
        self.calls: list[dict] = []

    def demas_get(self, path: str, params):  # noqa: ANN001, ANN201
        self.calls.append(dict(params))
        if len(self.calls) > 1:
            return {self.campo_chave: []}
        return {self.campo_chave: self.linhas}


def _linhas_de_varias_ufs(campo: str) -> list[dict]:
    return [
        {"id": "1", campo: "SP"},
        {"id": "2", campo: "MG"},
        {"id": "3", campo: "ES"},
        {"id": "4", campo: "SP"},
    ]


def _baixa(client, tmp_path: Path, **kwargs):
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]
    return datasource.download(
        dataset="atencao-primaria/cadastro-vinculado-programa-previne-brasil",
        batch_size=100,
        max_pages=2,
        keep_raw=True,
        **kwargs,
    )


@pytest.mark.parametrize(
    "campo, parametro",
    [
        ("sigla_unidade_federacao", "sigla_unidade_federacao"),
        ("sg_uf", "sg_uf"),
        ("uf", "uf"),
    ],
)
def test_recorte_e_reconferido_nas_linhas(tmp_path: Path, campo: str, parametro: str) -> None:
    client = _ClienteQueIgnoraOFiltro(_linhas_de_varias_ufs(campo))

    _baixa(client, tmp_path, **{parametro: "SP"})

    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]
    del datasource
    # O recorte foi aplicado sobre as linhas, não só enviado à origem.
    bruto = (tmp_path / "raw").glob("*.jsonl")
    conteudo = "\n".join(caminho.read_text(encoding="utf-8") for caminho in bruto)
    assert '"MG"' not in conteudo
    assert '"ES"' not in conteudo
    assert conteudo.count('"SP"') == 2


def test_filtro_continua_sendo_enviado_a_origem(tmp_path: Path) -> None:
    """A reconferência local não substitui o recorte na consulta.

    O recorte precisa viajar sob o nome que o endpoint declara no swagger:
    qualquer outro é descartado pela origem, que só aceita os parâmetros que
    publica.
    """
    client = _ClienteQueIgnoraOFiltro(_linhas_de_varias_ufs("uf"))

    _baixa(client, tmp_path, uf="SP")

    enviados = client.calls[0]
    nomes_de_uf = set(OpenDataSUSDataSource._UF_PARAM_NAMES) & set(enviados)
    assert nomes_de_uf, f"nenhum parâmetro de UF foi enviado: {enviados}"
    assert all(enviados[nome] == "SP" for nome in nomes_de_uf)


def test_sem_campo_de_uf_nada_e_descartado(tmp_path: Path) -> None:
    """Sem coluna de UF, filtrar apagaria tudo; o pedido segue com aviso."""
    linhas = [{"id": "1", "municipio": "Santos"}, {"id": "2", "municipio": "Ouro Preto"}]
    client = _ClienteQueIgnoraOFiltro(linhas)

    payload = _baixa(client, tmp_path, uf="SP")

    assert payload["downloaded_count"] == 2
    avisos = " ".join(str(item) for item in payload.get("warnings") or [])
    assert "could not be verified" in avisos


def test_uf_por_extenso_nao_zera_o_resultado(tmp_path: Path) -> None:
    """A origem escrevendo o estado por extenso não casa com a sigla pedida."""
    linhas = [{"id": "1", "uf": "São Paulo"}, {"id": "2", "uf": "Minas Gerais"}]
    client = _ClienteQueIgnoraOFiltro(linhas)

    payload = _baixa(client, tmp_path, uf="SP")

    assert payload["downloaded_count"] == 2
    avisos = " ".join(str(item) for item in payload.get("warnings") or [])
    assert "could not be verified" in avisos


def test_sem_pedido_de_uf_nada_muda(tmp_path: Path) -> None:
    client = _ClienteQueIgnoraOFiltro(_linhas_de_varias_ufs("sigla_unidade_federacao"))

    payload = _baixa(client, tmp_path)

    assert payload["downloaded_count"] == 4
    avisos = " ".join(str(item) for item in payload.get("warnings") or [])
    assert "could not be verified" not in avisos
