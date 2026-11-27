"""Microdados das amostras dos Censos Demográficos de 2010 e 2000, por UF.

Conferido ao vivo em 2026-11-14 (listagens, diretório central dos zips por Range, primeiras
linhas dos zips do AC e comprimento das linhas):

- **Censo 2010**: um zip por UF em ``Censos/Censo_Demografico_2010/Resultados_Gerais_da_Amostra/
  Microdados/`` (São Paulo em dois: ``SP1`` com o interior e ``SP2_RM`` com a região
  metropolitana), com quatro arquivos de largura fixa: domicílios (172 posições, 76
  variáveis), pessoas (540, 244), emigração (74, 19) e mortalidade (66, 19). O leiaute só
  existe em planilha (``Documentacao.zip`` traz ``Layout_microdados_Amostra.xls`` e ``.ods``),
  então foi extraído uma vez do ODS, conferido contra o comprimento das linhas e congelado em
  ``layouts/censo_2010_*.csv``, como na PeNSE 2009. As marcas de imputação (``M....``) são
  colunas do leiaute.
- **Censo 2000**: um zip por UF em ``Censos/Censo_Demografico_2000/Microdados/`` com
  domicílios (170 posições), famílias (118) e pessoas (até 390; o IBGE corta os brancos
  finais, e a leitura devolve campo vazio). O leiaute vem dos programas SAS ``LE DOMIC.sas``,
  ``LE FAMILIAS.sas`` e ``LE PESSOAS.sas`` do zip de documentação, lidos por
  ``parse_sas_input``.

O Censo de 1991 fica de fora: a amostra é um único zip de 674 MB com tabelas DBF e sem
programa de leitura publicado, e o Guaraci não lê DBF.

O peso amostral (V0010 em 2010, P001 em 2000) sai como o IBGE grava: inteiro com as casas
decimais implícitas, e interpretar é papel da camada prata.
"""

from __future__ import annotations

from typing import Dict, Tuple

from guaraci.ibge.microdados import _FROZEN, Edicao, Pesquisa, Recorte, Tabela

_CENSO = "Censos/"
_PASTA_2010 = _CENSO + "Censo_Demografico_2010/Resultados_Gerais_da_Amostra/Microdados/"
_PASTA_2000 = _CENSO + "Censo_Demografico_2000/Microdados/"

# sigla -> código IBGE da UF
_COD: Dict[str, str] = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}


def _partes_2010() -> Dict[str, Dict[str, str]]:
    partes: Dict[str, Dict[str, str]] = {}
    for uf, cod in _COD.items():
        if uf == "SP":
            partes["SP1"] = {"zip": "SP1", "cod": "35_outras"}
            partes["SP2_RM"] = {"zip": "SP2_RM", "cod": "35_RMSP"}
        else:
            partes[uf] = {"zip": uf, "cod": cod}
    return partes


def _partes_2000() -> Dict[str, Dict[str, str]]:
    return {uf: {"zip": uf, "cod": cod} for uf, cod in _COD.items()}


IBGE_CENSO2010_AMOSTRA = Pesquisa(
    "ibge_censo2010_amostra",
    "IBGE Censo Demográfico 2010, amostra (microdados)",
    "Microdados da amostra do Censo Demográfico 2010 por UF, em quatro tabelas de largura "
    "fixa: domicílios (características e saneamento), pessoas (demografia, educação, "
    "trabalho, rendimento, deficiência, fecundidade e migração), emigração internacional e "
    "mortalidade (óbitos de moradores de ago/2009 a jul/2010 por sexo e idade). Traz o peso "
    "amostral e a área de ponderação, mais as marcas de imputação. São Paulo vem em duas "
    "partes: SP1 (interior) e SP2_RM (região metropolitana). O leiaute é o do IBGE, "
    "congelado a partir da planilha publicada. Os microdados são anônimos, sem nome nem "
    "endereço.",
    {
        2010: Edicao(
            2010,
            "2010",
            {"dados": _PASTA_2010 + "{zip}.zip"},
            (
                Tabela(
                    "domicilios",
                    "dados",
                    "Amostra_Domicilios_{cod}.txt",
                    layout=(_FROZEN, "censo_2010_domicilios.csv"),
                ),
                Tabela(
                    "pessoas",
                    "dados",
                    "Amostra_Pessoas_{cod}.txt",
                    layout=(_FROZEN, "censo_2010_pessoas.csv"),
                ),
                Tabela(
                    "emigracao",
                    "dados",
                    "Amostra_Emigracao_{cod}.txt",
                    layout=(_FROZEN, "censo_2010_emigracao.csv"),
                ),
                Tabela(
                    "mortalidade",
                    "dados",
                    "Amostra_Mortalidade_{cod}.txt",
                    layout=(_FROZEN, "censo_2010_mortalidade.csv"),
                ),
            ),
        )
    },
    recorte=Recorte("ufs", "UF", _partes_2010(), obrigatorio=True),
)

IBGE_CENSO2000_AMOSTRA = Pesquisa(
    "ibge_censo2000_amostra",
    "IBGE Censo Demográfico 2000, amostra (microdados)",
    "Microdados da amostra do Censo Demográfico 2000 por UF, em três tabelas de largura "
    "fixa: domicílios, famílias e pessoas (demografia, educação, trabalho, rendimento, "
    "deficiência, fecundidade e migração), com o peso e a área de ponderação e as marcas de "
    "imputação. O leiaute é lido dos programas SAS de leitura do zip de documentação do "
    "IBGE. Os microdados são anônimos, sem nome nem endereço.",
    {
        2000: Edicao(
            2000,
            "2000",
            {
                "dados": _PASTA_2000 + "{zip}.zip",
                "doc": _PASTA_2000 + "1_Documentacao_20170908.zip",
            },
            (
                Tabela("domicilios", "dados", "Dom{cod}.txt", layout=("doc", "LE DOMIC.sas")),
                Tabela("familias", "dados", "FAMI{cod}.TXT", layout=("doc", "LE FAMILIAS.sas")),
                Tabela("pessoas", "dados", "Pes{cod}.txt", layout=("doc", "LE PESSOAS.sas")),
            ),
        )
    },
    recorte=Recorte("ufs", "UF", _partes_2000(), obrigatorio=True),
)

PESQUISAS_CENSOS: Tuple[Pesquisa, ...] = (IBGE_CENSO2010_AMOSTRA, IBGE_CENSO2000_AMOSTRA)
