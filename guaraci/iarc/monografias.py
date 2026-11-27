"""IARC, classificação dos agentes das Monografias (Grupos 1, 2A, 2B e 3).

A página ``monographs.iarc.who.int/list-of-classifications`` monta a tabela no navegador a partir
de ``webapi.iarc.who.int/loc/loc.app.js`` (130 KB, URL fixa). O arquivo é um módulo JavaScript
minificado cujo objeto de dados, ``{last_volume, last_update, agents: [...]}``, é uma lista de
agentes com nome, grupo, número CAS, volumes das Monografias, ano de publicação e de avaliação.
Não existe CSV nem API: a leitura recorta a lista ``agents`` e a converte em JSON. Se o IARC
reorganizar o arquivo, a leitura falha com mensagem em vez de devolver tabela parcial.

Conferido ao vivo em 2026-11-14: volumes 1 a 142, atualização de 2026-07-23, 1.128 linhas (68 são remissões do tipo
"ver ...", sem grupo; as demais: Grupo 1 com 135, 2A com 98, 2B com 329 e 3 com 498).

Termos de uso do IARC (publications.iarc.who.int/Terms-Of-Use, linkados no rodapé do site):
os materiais têm direitos reservados; trechos podem ser reproduzidos para pesquisa, estudo,
ensino ou fins não comerciais, com a fonte do IARC reconhecida. Reprodução ampla ou fora desses
fins pede permissão escrita do IARC.
"""

import json
import re
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import polars as pl

from guaraci.arquivos.http_files import HttpFile, HttpResource
from guaraci.inqueritos.leitores import datasource_com_leitor

_URL = "https://webapi.iarc.who.int/loc/loc.app.js"

# Colunas na ordem do arquivo de origem; chaves novas entram no fim, em ordem alfabética.
_COLUNAS = ("name", "group", "cas", "volume", "year", "yeareval", "in_prep", "comment")

# Em uma passada só: texto entre aspas duplas (passa intacto), texto entre aspas simples
# (``comment:'...'``, vira aspas duplas), chave sem aspas (``name:``) e booleano minificado
# (``!0``/``!1``).
_TOKEN = re.compile(
    r'"(?:[^"\\]|\\.)*"'
    r"|('(?:[^'\\]|\\.)*')"
    r"|([{,])([A-Za-z_]\w*):"
    r"|(?<=:)!([01])(?=[,}\]])"
)


def _lista_agents(js: str) -> str:
    """Texto da lista ``agents:[...]`` (colchetes balanceados, respeitando as aspas)."""
    inicio = js.find("agents:[")
    if inicio < 0:
        raise ValueError("loc.app.js não tem a lista 'agents'; o IARC mudou o arquivo.")
    posicao = inicio + len("agents:")
    nivel = 0
    i = posicao
    while i < len(js):
        c = js[i]
        if c in "\"'":
            i += 1
            while js[i] != c:
                i += 2 if js[i] == "\\" else 1
        elif c == "[":
            nivel += 1
        elif c == "]":
            nivel -= 1
            if nivel == 0:
                return js[posicao : i + 1]
        i += 1
    raise ValueError("Lista 'agents' de loc.app.js sem fechamento.")


def _aspas_duplas(interno: str) -> str:
    """Conteúdo de um texto entre aspas simples como texto JSON (aspas duplas)."""
    saida = []
    i = 0
    while i < len(interno):
        c = interno[i]
        if c == "\\" and i + 1 < len(interno):
            proximo = interno[i + 1]
            saida.append(proximo if proximo == "'" else c + proximo)
            i += 2
            continue
        saida.append('\\"' if c == '"' else c)
        i += 1
    return '"' + "".join(saida) + '"'


def _json(lista: str) -> str:
    def troca(m: "re.Match[str]") -> str:
        if m.group(1):
            return _aspas_duplas(m.group(1)[1:-1])
        if m.group(2):
            return f'{m.group(2)}"{m.group(3)}":'
        if m.group(4):
            return "true" if m.group(4) == "0" else "false"
        return m.group(0)

    return _TOKEN.sub(troca, lista)


def _texto(valor: object) -> "str | None":
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, list):
        return ";".join(str(v) for v in valor) or None
    text = str(valor).strip()
    return text or None


def ler_loc(raw: Path, avisos: List[str]) -> Iterator[Tuple[str, pl.DataFrame]]:
    agentes = json.loads(_json(_lista_agents(raw.read_text(encoding="utf-8"))))
    if not agentes or not all(isinstance(a, dict) and "name" in a for a in agentes):
        raise ValueError("A lista 'agents' de loc.app.js não tem o formato esperado.")
    extras = sorted({k for a in agentes for k in a} - set(_COLUNAS))
    colunas = [c for c in _COLUNAS if any(c in a for a in agentes)] + extras
    linhas = [[_texto(a.get(c)) for c in colunas] for a in agentes]
    yield "", pl.DataFrame(linhas, schema={c: pl.String for c in colunas}, orient="row")


IARC_MONOGRAFIAS_CLASSIFICACOES = HttpFile(
    "iarc_monografias_classificacoes",
    "IARC - Classificação dos agentes das Monografias (Grupos 1, 2A, 2B e 3)",
    "Lista de agentes avaliados pelas Monografias do IARC (OMS) sobre carcinogenicidade para "
    "humanos: nome, grupo (1, 2A, 2B ou 3), número CAS, volumes das Monografias, ano de "
    "publicação e de avaliação, para cruzar agrotóxicos e outros agentes com o risco de câncer. "
    "O IARC publica a lista dentro do aplicativo da página, e não como arquivo de dados; vários "
    "números CAS e volumes saem separados por ponto e vírgula. Uso para pesquisa e fins não "
    "comerciais, com a fonte do IARC reconhecida. Não traz dado pessoal.",
    (HttpResource("lista", _URL),),
)

SPECS: Tuple[HttpFile, ...] = (IARC_MONOGRAFIAS_CLASSIFICACOES,)
MODES: Dict[str, str] = {spec.key: "iarc files" for spec in SPECS}
DATASOURCES: Dict[str, type] = {
    "iarc_monografias_classificacoes": datasource_com_leitor(
        IARC_MONOGRAFIAS_CLASSIFICACOES, ler_loc
    )
}
