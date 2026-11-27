"""IDEB por município (INEP): anos iniciais, anos finais e ensino médio, bienal desde 2019.

Verificado ao vivo em 2026-10-23 (HEAD e membros de cada zip). O INEP guarda os dois últimos
ciclos em ``download.inep.gov.br/ideb/resultados/`` (2023 e 2025) e os anteriores em
``download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/<ano>/`` (2019 e
2021 existem; 2017 dá 404). Cada zip traz o xlsx, uma cópia em ods e um md5, então o membro
é achado por padrão. A planilha tem quatro linhas de título, duas de cabeçalho em bloco e,
na oitava linha, os nomes técnicos das colunas (``SG_UF``, ``CO_MUNICIPIO``,
``VL_APROVACAO_2005_SI_4``...), que o export usa; as seis linhas acima dele são descartadas.
O número de colunas cresce a cada ciclo (a série histórica começa em 2005), e cada
etapa e ciclo sai como arquivo próprio.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_NOVO = "https://download.inep.gov.br/ideb/resultados/"
_ANTIGO = "https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/"
_ETAPAS = (
    ("AI", "anos_iniciais", "anos iniciais do ensino fundamental"),
    ("AF", "anos_finais", "anos finais do ensino fundamental"),
    ("EM", "ensino_medio", "ensino médio"),
)
ANOS: Tuple[int, ...] = (2019, 2021, 2023, 2025)


def resource_url(year: int, etapa: str) -> str:
    base = _NOVO if year >= 2023 else f"{_ANTIGO}{year}/"
    return f"{base}divulgacao_{etapa}_municipios_{year}.zip"


def _resources() -> Tuple[HttpResource, ...]:
    return tuple(
        HttpResource(f"{year}_{sigla}", resource_url(year, etapa), f"IDEB {titulo} {year}")
        for year in ANOS
        for sigla, etapa, titulo in _ETAPAS
    )


INEP_IDEB_MUNICIPIOS = HttpFile(
    "inep_ideb_municipios",
    "INEP IDEB - Resultados por município",
    "Índice de Desenvolvimento da Educação Básica por município e rede (estadual, municipal, "
    "pública e privada, INEP), nos ciclos bienais de 2019, 2021, 2023 e 2025, para os anos "
    "iniciais, os anos finais e o ensino médio: taxa de aprovação, nota do Saeb padronizada, "
    "indicador de rendimento, IDEB observado e meta projetada, com a série desde 2005. Cada "
    "etapa e ciclo vira um arquivo (código AAAA_AI, AAAA_AF, AAAA_EM) e as colunas seguem os "
    "nomes técnicos da planilha. Não traz dado pessoal. Os ciclos anteriores a 2019 usam "
    "outro padrão de endereço e ficam fora.",
    _resources(),
    file_format="xlsx",
    skip_rows=7,
    member_pattern=r"\.xlsx$",
    selector="periodo",
    period_required=False,
    year_window=True,
    subperiod_label="Etapas (AI = anos iniciais, AF = anos finais, EM = ensino médio). "
    "Omita para todas.",
)



def escolas_url(year: int, etapa: str) -> str:
    base = _NOVO if year >= 2023 else f"{_ANTIGO}{year}/"
    return f"{base}divulgacao_{etapa}_escolas_{year}.zip"


def brasil_url(year: int) -> str:
    base = _NOVO if year >= 2023 else f"{_ANTIGO}{year}/"
    return f"{base}divulgacao_brasil_ideb_{year}.zip"


def ufs_url(year: int) -> str:
    base = _NOVO if year >= 2023 else f"{_ANTIGO}{year}/"
    return f"{base}divulgacao_regioes_ufs_ideb_{year}.zip"


INEP_IDEB_ESCOLAS = HttpFile(
    "inep_ideb_escolas",
    "INEP IDEB - Resultados por escola",
    "Índice de Desenvolvimento da Educação Básica por escola (INEP), nos ciclos bienais de "
    "2019, 2021, 2023 e 2025, para os anos iniciais, os anos finais e o ensino médio: taxa de "
    "aprovação, nota do Saeb padronizada, indicador de rendimento, IDEB observado e meta "
    "projetada, com a série desde 2005. Cada etapa e ciclo vira um arquivo (código AAAA_AI, "
    "AAAA_AF, AAAA_EM) e as colunas seguem os nomes técnicos da planilha. Identifica a escola "
    "pelo código do INEP e pelo nome; não traz dado pessoal de aluno.",
    tuple(
        HttpResource(f"{year}_{sigla}", escolas_url(year, etapa), f"IDEB escolas {titulo} {year}")
        for year in ANOS
        for sigla, etapa, titulo in _ETAPAS
    ),
    file_format="xlsx",
    skip_rows=7,
    member_pattern=r"\.xlsx$",
    selector="periodo",
    period_required=False,
    year_window=True,
    subperiod_label="Etapas (AI = anos iniciais, AF = anos finais, EM = ensino médio). "
    "Omita para todas.",
)

INEP_IDEB_BRASIL_UFS = HttpFile(
    "inep_ideb_brasil_ufs",
    "INEP IDEB - Resultados do Brasil, regiões e UFs",
    "Índice de Desenvolvimento da Educação Básica do Brasil, das regiões e das UFs por rede "
    "(INEP), nos ciclos bienais de 2019, 2021, 2023 e 2025, com a série desde 2005. Cada nível "
    "e ciclo vira um conjunto de arquivos (AAAA_BR para o Brasil, AAAA_UF para regiões e UFs); cada um tem "
    "as três etapas (anos iniciais, anos finais, ensino médio) em abas, e cada aba sai como arquivo próprio. "
    "Não traz dado pessoal.",
    tuple(
        HttpResource(f"{year}_BR", brasil_url(year), f"IDEB Brasil {year}") for year in ANOS
    )
    + tuple(HttpResource(f"{year}_UF", ufs_url(year), f"IDEB regiões e UFs {year}") for year in ANOS),
    file_format="xlsx",
    skip_rows=7,
    member_pattern=r"\.xlsx$",
    selector="periodo",
    period_required=False,
    year_window=True,
    subperiod_label="Nível (BR = Brasil, UF = regiões e UFs). Omita para os dois.",
)

SPECS: Tuple[HttpFile, ...] = (INEP_IDEB_MUNICIPIOS,)
# Registradas por ``guaraci.services.sources.trabalho_educacao``, não por ``arquivos``.
EXTRA_SPECS: Tuple[HttpFile, ...] = (INEP_IDEB_ESCOLAS, INEP_IDEB_BRASIL_UFS)
MODES: Dict[str, str] = {spec.key: "inep files" for spec in (*SPECS, *EXTRA_SPECS)}
