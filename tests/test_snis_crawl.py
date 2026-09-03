"""Regressão: três defeitos do crawl de saneamento no portal gov.br.

Verificado ao vivo em 2026-09-03:

* A página que o SNIS raspava saiu do ar sem responder 404: ela devolve 200 com
  o layout padrão do gov.br e nenhum link de arquivo, de modo que a coleta
  falhava com "No SNIS files matched" mesmo nos parâmetros padrão. Os arquivos
  passaram para a página de produtos.
* O menu lateral do portal repete arquivos de outros programas (planilhas de
  barragens, de emendas parlamentares) em toda página, e eles entravam no
  resultado como se fossem dados de saneamento.
* O SINISA publica planilhas em ``.rar``, formato que o crawler não reconhecia
  como documento. Sem reconhecê-lo, ele tentava abrir o arquivo como página, e
  o ``HTMLParser`` da biblioteca padrão levantava ``AssertionError`` sobre os
  bytes binários, derrubando a coleta inteira.
"""

from __future__ import annotations

from guaraci.snis.sinisa import SinisaDataSource, SinisaDocumentLink
from guaraci.snis.snis import SnisDataSource


def _link(url: str, kind: str = "planilhas", module: str | None = None) -> SinisaDocumentLink:
    return SinisaDocumentLink(url=url, text="", kind=kind, module=module)


SNIS_ARQUIVO = (
    "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/"
    "saneamento/snis/produtos-do-snis/diagnosticos/Planilhas_AP2022.zip"
)
LATERAL = (
    "https://www.gov.br/cidades/pt-br/assuntos/emendasparlamentares/"
    "PROSBDadosdasbarragens_V002atualizUSB29102020.xlsx"
)


def test_url_do_snis_aponta_para_a_pagina_que_tem_os_arquivos() -> None:
    """A página antiga responde 200 e vem vazia, o que não é distinguível de
    uma falha de coleta; o alvo passa a ser a de produtos."""
    assert SnisDataSource.DEFAULT_RESULTS_URL.endswith("produtos-do-snis/diagnosticos-snis")


def test_arquivo_do_menu_lateral_nao_entra_no_resultado() -> None:
    filtrados = SinisaDataSource._filter_documents(
        links=[_link(SNIS_ARQUIVO), _link(LATERAL)],
        selected_kinds=["all"],
        normalized_modules=None,
        path_markers=SnisDataSource.DOCUMENT_PATH_MARKERS,
    )

    assert [item.url for item in filtrados] == [SNIS_ARQUIVO]


def test_sem_marcadores_nada_e_descartado() -> None:
    """O filtro por caminho é opcional: sem marcadores, o comportamento é o
    antigo."""
    filtrados = SinisaDataSource._filter_documents(
        links=[_link(SNIS_ARQUIVO), _link(LATERAL)],
        selected_kinds=["all"],
        normalized_modules=None,
    )

    assert len(filtrados) == 2


def test_cada_fonte_restringe_ao_proprio_caminho() -> None:
    assert SnisDataSource.DOCUMENT_PATH_MARKERS == ("/saneamento/snis/",)
    assert SinisaDataSource.DOCUMENT_PATH_MARKERS == ("/saneamento/sinisa/",)


def test_rar_conta_como_documento_e_como_planilha() -> None:
    """As planilhas de resíduos e águas pluviais de 2023 vêm em `.rar`."""
    url = (
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/"
        "saneamento/sinisa/resultados-sinisa/SINISA_RESIDUOS_Planilhas_2023.rar"
    )

    assert SinisaDataSource._is_downloadable(url)
    assert SinisaDataSource._is_planilha_source(url)


def test_html_ilegivel_descarta_a_pagina_em_vez_de_abortar() -> None:
    """Bytes binários no lugar de uma página derrubavam a coleta inteira.

    O ``HTMLParser`` levanta ``AssertionError``, e não uma exceção de parsing,
    o que passava por qualquer ``except`` que se esperasse ali.
    """
    binario = '<![:e\x90\x02\xaa/\xdc4\xe6\x03\x17G\x92\xfd\x83\x0b\xa6'

    anchors = SinisaDataSource._extract_anchors(binario, "https://exemplo.gov.br/x.rar")

    assert anchors == []


def test_html_valido_continua_sendo_lido() -> None:
    html = '<a href="/saneamento/sinisa/planilha.zip">Planilha</a>'

    anchors = SinisaDataSource._extract_anchors(html, "https://www.gov.br/cidades/")

    assert len(anchors) == 1
    assert anchors[0][0].endswith("/saneamento/sinisa/planilha.zip")
