"""Infosiga SP (Detran-SP): sinistros de trânsito, pessoas e veículos, um CSV por ano.

Padrão ``https://infosiga.detran.sp.gov.br/dados-abertos/<tabela>_AAAA.csv``, conferido ao
vivo em 2026-10-23 (HEAD e primeiros 3 MB). As três tabelas começam em 2015: o arquivo de
2014 existe, mas é um resíduo de cerca de 3 KB. O ano corrente responde 404 até o Detran
publicá-lo, e o zip ``dados_infosiga.zip`` responde 401 e não é usado. CSV em ``;``,
cp1252, com o mesmo leiaute em 2015 e 2025 (sinistros 48 colunas, pessoas 29, veículos 12).
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_BASE = "https://infosiga.detran.sp.gov.br/dados-abertos/"
MIN_YEAR = 2015
MAX_YEAR = 2026


def _resources(table: str) -> Tuple[HttpResource, ...]:
    return tuple(
        HttpResource(str(y), f"{_BASE}{table}_{y}.csv", f"Infosiga {table} {y}")
        for y in range(MIN_YEAR, MAX_YEAR + 1)
    )


def _spec(key: str, table: str, title: str, description: str) -> HttpFile:
    return HttpFile(
        key,
        title,
        description,
        _resources(table),
        separator=";",
        selector="periodo",
        period_required=False,
        year_window=True,
    )


DETRAN_SP_INFOSIGA_SINISTROS = _spec(
    "detran_sp_infosiga_sinistros",
    "sinistros",
    "Detran-SP Infosiga - Sinistros de trânsito",
    "Sinistros de trânsito do estado de São Paulo (Infosiga), um registro por sinistro, de "
    "2015 em diante: data, hora, logradouro, coordenada, município (código IBGE), tipo de "
    "via, tipo de sinistro e contagens de veículos e de vítimas por gravidade. Liga-se às "
    "tabelas de pessoas e veículos por id_sinistro. O ano corrente só existe depois que o "
    "Detran o publica. Traz endereço do sinistro (logradouro, número e coordenada), "
    "publicado assim pelo órgão; o tratamento LGPD fica nas camadas prata e ouro do Sabiá.",
)
DETRAN_SP_INFOSIGA_PESSOAS = _spec(
    "detran_sp_infosiga_pessoas",
    "pessoas",
    "Detran-SP Infosiga - Pessoas envolvidas em sinistros",
    "Vítimas de sinistros de trânsito do estado de São Paulo (Infosiga), um registro por "
    "pessoa, de 2015 em diante: sexo, idade, faixas etárias, gravidade da lesão, tipo de "
    "vítima, profissão, grau de instrução, nacionalidade e dados do óbito. Sem nome nem "
    "documento; liga-se ao sinistro por id_sinistro. O ano corrente só existe depois que o "
    "Detran o publica.",
)
DETRAN_SP_INFOSIGA_VEICULOS = _spec(
    "detran_sp_infosiga_veiculos",
    "veiculos",
    "Detran-SP Infosiga - Veículos envolvidos em sinistros",
    "Veículos envolvidos em sinistros de trânsito do estado de São Paulo (Infosiga), um "
    "registro por veículo, de 2015 em diante: marca e modelo, ano de fabricação e do "
    "modelo, cor e tipo. Sem placa; liga-se ao sinistro por id_sinistro. O ano corrente só "
    "existe depois que o Detran o publica.",
)

SPECS: Tuple[HttpFile, ...] = (
    DETRAN_SP_INFOSIGA_SINISTROS,
    DETRAN_SP_INFOSIGA_PESSOAS,
    DETRAN_SP_INFOSIGA_VEICULOS,
)
MODES: Dict[str, str] = {spec.key: "detran sp files" for spec in SPECS}
