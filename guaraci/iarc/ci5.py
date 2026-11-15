"""IARC, Cancer Incidence in Five Continents Volume XII (CI5-XII).

O zip de 1,2 MB (``gco.iarc.who.int/media/ci5/data/vol12/Download/CI5-XII.zip``, modificado em
2026-10-21) traz a base resumida do CI5-XII: casos por registro de base populacional, sexo,
faixa etária de 5 anos e câncer (categoria de 3 caracteres da CID-10), mais a população do
registro. Conferido ao vivo em 2026-11-14, tem 589 registros no mundo, dos quais nove
brasileiros (Goiânia, Barretos, Campinas, Aracaju, Curitiba, João Pessoa, Recife, Jaú e Belo
Horizonte; 2013-2017). A fonte entrega a base inteira, como publicada, e quem quiser só o Brasil
filtra pelo nome do registro (``Brazil``) na tabela ``registros``.

O zip tem quatro membros: ``cases.csv`` e ``pop.csv`` (CSV), ``Registry.txt`` (largura fixa:
código de 9 dígitos, marcador ``*`` opcional, nome e período) e ``cancer_summary.txt`` (TSV
com preenchimento de brancos). A exportação gera uma tabela de cada.

CI5plus (série anual 1953-2017) não entra: os 70 MB do zip detalhado (714 MB de CSV) e os 15 MB
do resumido não têm nenhum registro brasileiro no dicionário ``id_dict.csv``.

Termos de uso do CI5 (página de downloads do CI5-XII): os dados podem ser usados livremente,
mas não para venda nem para fins comerciais ou promocionais, e todo uso exige citação e
reconhecimento da fonte. Os Termos de Uso do IARC (publications.iarc.who.int/Terms-Of-Use)
permitem reprodução para pesquisa, estudo, ensino ou fins não comerciais, com a fonte
reconhecida.
"""

import io
import re
import zipfile
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import polars as pl

from guaraci.arquivos.http_files import HttpFile, HttpResource
from guaraci.inqueritos.leitores import datasource_com_leitor

_URL = "https://gco.iarc.who.int/media/ci5/data/vol12/Download/CI5-XII.zip"

_REGISTRO = re.compile(r"^(\d{9})\s+(\*\s+)?(.*?)\s+(\d{4}-\d{4})\s*$")


def _csv(archive: zipfile.ZipFile, membro: str) -> pl.DataFrame:
    frame = pl.read_csv(io.BytesIO(archive.read(membro)), infer_schema=False)
    return frame.rename({n: n.strip() for n in frame.columns})


def _registros(texto: str) -> pl.DataFrame:
    """``Registry.txt``: código, marcador ``*`` (como publicado), nome e período do registro."""
    linhas = []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        achou = _REGISTRO.match(linha)
        if not achou:
            raise ValueError(f"Linha fora do leiaute em Registry.txt: {linha!r}")
        codigo, marcador, nome, periodo = achou.groups()
        linhas.append((codigo, "*" if marcador else None, nome, periodo))
    return pl.DataFrame(linhas, schema=["REGISTRY", "MARKER", "NAME", "PERIOD"], orient="row")


def _cancer(texto: str) -> pl.DataFrame:
    """``cancer_summary.txt``: TSV com colunas preenchidas por brancos à direita."""
    frame = pl.read_csv(
        io.BytesIO(texto.encode("utf-8")), separator="\t", infer_schema=False, quote_char=None
    )
    frame = frame.rename({n: n.strip() for n in frame.columns})
    return frame.with_columns(pl.all().str.strip_chars())


def ler_ci5(raw: Path, avisos: List[str]) -> Iterator[Tuple[str, pl.DataFrame]]:
    with zipfile.ZipFile(raw) as archive:
        nomes = {n.lower(): n for n in archive.namelist()}
        faltam = [m for m in ("cases.csv", "pop.csv", "registry.txt", "cancer_summary.txt")
                  if m not in nomes]
        if faltam:
            raise ValueError(f"{raw.name} não tem os membros {faltam}: {sorted(nomes)}")
        yield "cases", _csv(archive, nomes["cases.csv"])
        yield "pop", _csv(archive, nomes["pop.csv"])
        yield "registros", _registros(archive.read(nomes["registry.txt"]).decode("utf-8"))
        yield "cancer", _cancer(archive.read(nomes["cancer_summary.txt"]).decode("utf-8"))


IARC_CI5_XII = HttpFile(
    "iarc_ci5_xii",
    "IARC - Câncer nos cinco continentes, volume XII (CI5-XII)",
    "Incidência de câncer por registro de base populacional, publicada pelo IARC (OMS) com os "
    "dados padronizados de 589 registros, nove deles brasileiros (Goiânia, Barretos, "
    "Campinas, Aracaju, Curitiba, João Pessoa, Recife, Jaú e Belo Horizonte, 2013-2017). Quatro "
    "saídas: casos (registro, sexo, câncer e faixa etária), população do registro, lista de "
    "registros com nome e período, e dicionário dos 3 caracteres da CID-10. Fonte secundária "
    "com curadoria própria do IARC; uso livre sem fim comercial ou promocional, com citação "
    "(Cancer Incidence in Five Continents Volume XII, IARC). Não traz dado pessoal.",
    (HttpResource("xii", _URL),),
    member_pattern=r"\.csv$",
)

SPECS: Tuple[HttpFile, ...] = (IARC_CI5_XII,)
MODES: Dict[str, str] = {spec.key: "iarc files" for spec in SPECS}
DATASOURCES: Dict[str, type] = {"iarc_ci5_xii": datasource_com_leitor(IARC_CI5_XII, ler_ci5)}
