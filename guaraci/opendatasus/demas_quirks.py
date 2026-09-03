"""Desvios de contrato de endpoints específicos da API DEMAS.

A API de dados abertos do Ministério da Saúde é quase uniforme: em 87 rotas
publicadas, 83 paginam com ``limit``/``offset``. As exceções não aparecem em
nenhum lugar do swagger de forma utilizável, então ficam registradas aqui, com
o que foi verificado ao vivo em cada caso.
"""

from __future__ import annotations

from typing import Dict, Mapping, Sequence, Tuple

# ``/economia-da-saude/bps`` pagina por número de página, 1-based, e ignora
# ``limit``/``offset`` em silêncio: verificado em 2026-09-03, ``limit=3`` e
# ``limit=3&offset=3`` devolvem as mesmas 100 linhas da página inicial. Paginar
# esse endpoint como os outros renderia a mesma página repetida até esgotar
# ``max_pages``, produzindo duplicatas em massa sem nenhum erro visível.
PAGE_NUMBER_ENDPOINTS: frozenset[str] = frozenset({"/economia-da-saude/bps"})

# O mesmo endpoint responde 400 a qualquer chamada que não traga um destes dois
# filtros, embora o swagger declare ambos como opcionais. Não há rota que liste
# os códigos CATMAT, de modo que a coleta é necessariamente pontual.
REQUIRED_ANY_OF: Dict[str, Tuple[str, ...]] = {
    "/economia-da-saude/bps": ("codigoCatmat", "cnpjInstituicao"),
}


# Nomes reservados à paginação, em qualquer um dos dois esquemas.
PAGINATION_PARAM_NAMES: frozenset[str] = frozenset(
    {"limit", "offset", "pagina", "tamanhoPagina"}
)


def _normalize(endpoint: str) -> str:
    return "/" + endpoint.strip().strip("/")


def pagination_params(endpoint: str, *, page: int, page_size: int) -> Dict[str, object]:
    """Parâmetros de paginação para ``page`` (0-based) no esquema do endpoint."""
    if _normalize(endpoint) in PAGE_NUMBER_ENDPOINTS:
        return {"tamanhoPagina": page_size, "pagina": page + 1}
    # DEMAS conta offset em LINHAS, não em páginas, apesar de o swagger dizer
    # "Número da página": limit=5&offset=1 sobrepõe 4 das 5 linhas de offset=0.
    return {"limit": page_size, "offset": page * page_size}


def required_filters(endpoint: str) -> Tuple[str, ...]:
    """Filtros dos quais ao menos um precisa ser informado, se houver."""
    return REQUIRED_ANY_OF.get(_normalize(endpoint), ())


def check_required_filters(endpoint: str, params: Mapping[str, object]) -> None:
    """Falha antes da primeira requisição se faltar o filtro obrigatório.

    Sem isso, o pedido só quebra no 400 da origem, cuja mensagem não diz de
    qual fonte do Guaraci se trata nem quais nomes de parâmetro usar.
    """
    exigidos: Sequence[str] = required_filters(endpoint)
    if not exigidos:
        return
    if any(_informado(params.get(nome)) for nome in exigidos):
        return
    nomes = " ou ".join(f"'{nome}'" for nome in exigidos)
    raise ValueError(
        f"Endpoint '{_normalize(endpoint)}' requires at least one of {nomes}. "
        "This source only answers point queries: the origin rejects requests "
        "without one of these filters, and publishes no catalogue endpoint to "
        "enumerate the accepted values."
    )


def _informado(value: object) -> bool:
    return value is not None and str(value).strip() != ""
