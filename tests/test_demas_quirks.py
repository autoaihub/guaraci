"""Regressão: os dois desvios de contrato do endpoint bps da DEMAS.

Verificado ao vivo em 2026-09-03 contra a origem:

* ``/economia-da-saude/bps`` ignora ``limit``/``offset`` em silêncio. Com
  ``cnpjInstituicao=46374500000194``, tanto ``limit=3`` quanto
  ``limit=3&offset=3`` devolvem as mesmas 100 linhas, enquanto
  ``pagina=2&tamanhoPagina=3`` avança de verdade. Paginado como os outros 83
  endpoints, ele renderia a mesma página repetida até esgotar ``max_pages``.
* O mesmo endpoint responde 400 sem ``codigoCatmat`` ou ``cnpjInstituicao``,
  embora o swagger declare os dois como opcionais.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.opendatasus import demas_quirks
from guaraci.opendatasus.datasource import OpenDataSUSDataSource

BPS = "/economia-da-saude/bps"


def test_endpoint_comum_pagina_por_linhas() -> None:
    assert demas_quirks.pagination_params("/cnes/estabelecimentos", page=2, page_size=50) == {
        "limit": 50,
        "offset": 100,
    }


def test_bps_pagina_por_numero_de_pagina_1_based() -> None:
    assert demas_quirks.pagination_params(BPS, page=0, page_size=3) == {
        "tamanhoPagina": 3,
        "pagina": 1,
    }
    assert demas_quirks.pagination_params(BPS, page=1, page_size=3) == {
        "tamanhoPagina": 3,
        "pagina": 2,
    }


def test_esquema_independe_da_barra_inicial() -> None:
    assert demas_quirks.pagination_params("economia-da-saude/bps", page=0, page_size=1) == {
        "tamanhoPagina": 1,
        "pagina": 1,
    }


def test_filtro_obrigatorio_ausente_falha_com_os_nomes_aceitos() -> None:
    with pytest.raises(ValueError) as exc:
        demas_quirks.check_required_filters(BPS, {"estado": "SP"})
    mensagem = str(exc.value)
    assert "codigoCatmat" in mensagem
    assert "cnpjInstituicao" in mensagem


@pytest.mark.parametrize(
    "params",
    [
        {"codigoCatmat": "267177"},
        {"cnpjInstituicao": "46374500000194"},
        {"codigoCatmat": "267177", "cnpjInstituicao": "46374500000194"},
    ],
)
def test_qualquer_um_dos_dois_filtros_basta(params) -> None:
    demas_quirks.check_required_filters(BPS, params)  # não deve levantar


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_filtro_em_branco_nao_conta_como_informado(vazio) -> None:
    with pytest.raises(ValueError):
        demas_quirks.check_required_filters(BPS, {"codigoCatmat": vazio})


def test_endpoint_sem_exigencia_passa_com_params_vazios() -> None:
    demas_quirks.check_required_filters("/cnes/estabelecimentos", {})


class _ClientePaginado:
    """Cliente falso que devolve uma página cheia enquanto houver páginas."""

    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self, paginas: int) -> None:
        self.paginas = paginas
        self.calls: list[dict[str, object]] = []

    def demas_get(self, path: str, params):  # noqa: ANN001, ANN201
        self.calls.append(dict(params))
        indice = len(self.calls)
        if indice > self.paginas:
            return {"bps": []}
        tamanho = int(params.get("tamanhoPagina") or params.get("limit") or 1)
        return {"bps": [{"linha": f"p{indice}_{i}"} for i in range(tamanho)]}


def test_coleta_do_bps_usa_pagina_e_nao_offset(tmp_path: Path) -> None:
    client = _ClientePaginado(paginas=2)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    datasource.download(
        dataset="economia-da-saude/bps",
        batch_size=3,
        max_pages=3,
        keep_raw=True,
        cnpjInstituicao="46374500000194",
    )

    assert client.calls, "nenhuma requisição foi feita"
    for chamada in client.calls:
        assert "limit" not in chamada
        assert "offset" not in chamada
    assert [c["pagina"] for c in client.calls] == [1, 2, 3]


def test_coleta_do_bps_sem_filtro_falha_antes_de_qualquer_requisicao(tmp_path: Path) -> None:
    client = _ClientePaginado(paginas=2)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="codigoCatmat"):
        datasource.download(
            dataset="economia-da-saude/bps",
            batch_size=3,
            max_pages=3,
            keep_raw=True,
        )

    assert client.calls == []
