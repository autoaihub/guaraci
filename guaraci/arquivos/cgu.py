"""Portal da Transparência (CGU): Bolsa Família, BPC, despesas, transferências e emendas.

Bucket ``https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/`` (conferido
ao vivo em 2026-10-23: HEAD para os pisos, Range para as colunas). Um zip por competência
``AAAAMM_<Nome>.zip`` com um só CSV (``;``, cp1252, entre aspas); o das emendas traz três.
O bucket publica com defasagem: o mês M-1 e o corrente dão 403, então a competência mais
nova gerada é M-2 (em 2026-10-23, 202608), e o que ainda não existe cai como "não
publicado". Pisos medidos mês a mês: Novo Bolsa Família 2023-03 (2023-02 dá 403), BPC
2019-01 (2018-12 dá 403), despesas e transferências 2014-01 (2013 dá 403). Outros nomes de
arquivo (``despesas/2024_Despesas.zip``, ``convenios/Convenios.zip``) dão 403 e não são
usados.

O WAF do CloudFront aplica um desafio (HTTP 405 com ``x-amzn-waf-action: captcha``) a quem
dispara dezenas de requisições em poucos minutos; passados alguns minutos o bucket volta ao
normal. Não há como contornar, e o cliente não tenta.

Colunas conferidas: Novo Bolsa Família 9 (MÊS COMPETÊNCIA, MÊS REFERÊNCIA, UF, CÓDIGO
MUNICÍPIO SIAFI, NOME MUNICÍPIO, CPF FAVORECIDO...), BPC 14 (... NIS BENEFICIÁRIO...),
despesas 47 (Ano e mês do lançamento, Código Órgão Superior...), transferências 36 (ANO /
MÊS, TIPO TRANSFERÊNCIA, TIPO FAVORECIDO, UF...), emendas 28, 12 (Convenios) e 13
(PorFavorecido).
"""

from datetime import date
from typing import Dict, List, Optional, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_BASE = "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/"
# A competência mais nova publicada é M-2.
_LAG_MONTHS = 2

_PESSOAL = (
    "Traz identificador pessoal ({quais}), publicado assim pelo órgão; o tratamento LGPD "
    "fica nas camadas prata e ouro do Sabiá."
)


def latest_competencia(today: Optional[date] = None) -> Tuple[int, int]:
    """Ano e mês da competência mais nova que o bucket costuma ter (hoje menos dois meses)."""
    today = today or date.today()
    index = today.year * 12 + (today.month - 1) - _LAG_MONTHS
    return index // 12, index % 12 + 1


def competencias(first: Tuple[int, int], last: Tuple[int, int]) -> List[Tuple[int, int]]:
    start = first[0] * 12 + first[1] - 1
    end = last[0] * 12 + last[1] - 1
    return [(i // 12, i % 12 + 1) for i in range(start, end + 1)]


def _resources(folder: str, name: str, first: Tuple[int, int]) -> Tuple[HttpResource, ...]:
    return tuple(
        HttpResource(
            f"{y}_{m:02d}", f"{_BASE}{folder}/{y}{m:02d}_{name}.zip", f"{name} {y}-{m:02d}"
        )
        for y, m in competencias(first, latest_competencia())
    )


def _mensal(
    key: str,
    title: str,
    description: str,
    folder: str,
    name: str,
    first: Tuple[int, int],
    tamanho: str,
) -> HttpFile:
    return HttpFile(
        key,
        title,
        description,
        _resources(folder, name, first),
        separator=";",
        selector="periodo",
        period_required=True,
        year_window=True,
        anos_label=(
            f"Anos a baixar (obrigatório). Há um zip por mês, {tamanho} cada; use 'meses' "
            "para recortar."
        ),
    )


CGU_NOVO_BOLSA_FAMILIA = _mensal(
    "cgu_novo_bolsa_familia",
    "CGU Portal da Transparência - Novo Bolsa Família",
    "Pagamentos mensais do Novo Bolsa Família (MDS, via Portal da Transparência da CGU), "
    "um CSV por competência desde março de 2023: município (código SIAFI), favorecido e "
    "valor (9 colunas). " + _PESSOAL.format(quais="nome, CPF mascarado e NIS do favorecido")
    + " Cada zip tem cerca de 330 MB, com 2 GB de CSV.",
    "novo-bolsa-familia",
    "NovoBolsaFamilia",
    (2023, 3),
    "de 330 a 365 MB",
)
CGU_BPC = _mensal(
    "cgu_bpc",
    "CGU Portal da Transparência - BPC",
    "Pagamentos mensais do Benefício de Prestação Continuada (MDS, via Portal da "
    "Transparência da CGU), um CSV por competência desde janeiro de 2019, com município "
    "(código SIAFI), beneficiário e valor (14 colunas). "
    + _PESSOAL.format(quais="nome, CPF mascarado e NIS do beneficiário")
    + " Cada zip tem de 130 a 190 MB, com 1,2 GB de CSV.",
    "bpc",
    "BPC",
    (2019, 1),
    "de 130 a 190 MB",
)
CGU_DESPESAS_EXECUCAO = _mensal(
    "cgu_despesas_execucao",
    "CGU Portal da Transparência - Despesas executadas",
    "Documentos de despesa da União (empenho, liquidação e pagamento), um CSV por mês de "
    "lançamento desde janeiro de 2014: órgão, unidade gestora, função, subfunção, programa, "
    "ação, favorecido e valores (47 colunas). "
    + _PESSOAL.format(quais="código e nome do favorecido, com CPF ou CNPJ"),
    "despesas-execucao",
    "Despesas",
    (2014, 1),
    "de 4 a 10 MB",
)
CGU_TRANSFERENCIAS = _mensal(
    "cgu_transferencias",
    "CGU Portal da Transparência - Transferências de recursos da União",
    "Transferências da União a estados, municípios e outros favorecidos, um CSV por mês "
    "desde janeiro de 2014: tipo de transferência e de favorecido, município, órgão, "
    "função, programa, ação e valor (36 colunas). "
    + _PESSOAL.format(quais="código e nome do favorecido, com CPF ou CNPJ"),
    "transferencias",
    "Transferencias",
    (2014, 1),
    "de 1 a 3 MB",
)

CGU_EMENDAS_PARLAMENTARES = HttpFile(
    "cgu_emendas_parlamentares",
    "CGU Portal da Transparência - Emendas parlamentares",
    "Emendas parlamentares da União (CGU, Portal da Transparência), em três arquivos de um "
    "único zip de URL fixa, atualizado de forma contínua: as emendas (28 colunas, com autor, "
    "tipo, localidade e valores empenhado, liquidado e pago), os convênios ligados a elas "
    "(12 colunas) e os pagamentos por favorecido (13 colunas). "
    + _PESSOAL.format(quais="nome e código do autor da emenda e do favorecido, com CPF ou CNPJ"),
    (
        HttpResource(
            "emendas", _BASE + "emendas-parlamentares/EmendasParlamentares.zip", "Emendas"
        ),
    ),
    separator=";",
    members_pattern=r"\.csv$",
)

SPECS: Tuple[HttpFile, ...] = (
    CGU_NOVO_BOLSA_FAMILIA,
    CGU_BPC,
    CGU_DESPESAS_EXECUCAO,
    CGU_TRANSFERENCIAS,
    CGU_EMENDAS_PARLAMENTARES,
)
MODES: Dict[str, str] = {spec.key: "cgu files" for spec in SPECS}
