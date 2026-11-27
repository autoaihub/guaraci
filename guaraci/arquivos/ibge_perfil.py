"""Perfil dos municípios e dos estados do IBGE (MUNIC, ESTADIC e suplementos de saneamento).

Conferido ao vivo em 2026-11-14 (listagens do FTP e ``HEAD``). As bases saem do FTP em
``Perfil_Municipios/`` e ``Perfil_Estados/``: um xlsx por edição, com uma aba por bloco
temático e uma aba de dicionário, e cada aba vira uma saída irmã.

- ``ibge_munic_edicoes``: as edições da MUNIC em xlsx que não são a de 2024 (essa é a
  ``ibge_munic``): 2018 (zip de um xlsx), 2019, 2020, 2021, 2023 e 2025. As edições de 2001
  a 2017 só existem em xls ou ods, formatos que o leitor do Guaraci não abre.
- ``ibge_estadic``: a Pesquisa de Informações Básicas Estaduais, uma linha por UF, edições
  2018, 2019, 2020, 2021, 2023, 2024 e 2025 em xlsx. As de 2012 a 2017 estão em xls (zip).
- ``ibge_munic_saneamento``: suplementos de saneamento da MUNIC com uma linha por município,
  2017 (abastecimento de água e esgotamento sanitário) e 2023 (dados gerais, resíduos sólidos e drenagem).
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_MUNIC = "https://ftp.ibge.gov.br/Perfil_Municipios/"
_ESTADIC = "https://ftp.ibge.gov.br/Perfil_Estados/"

IBGE_MUNIC_EDICOES = HttpFile(
    "ibge_munic_edicoes",
    "IBGE MUNIC: Perfil dos municípios, edições 2018 a 2025",
    "Pesquisa de Informações Básicas Municipais (IBGE), base completa de cada edição em xlsx "
    "(2018, 2019, 2020, 2021, 2023 e 2025; a de 2024 é a fonte ibge_munic): uma aba por bloco "
    "temático, com uma linha por município e as respostas em texto, e uma aba de dicionário. "
    "Os blocos mudam a cada edição: a de 2021 traz saúde, educação, cultura, esporte e covid, "
    "a de 2023 traz assistência social, segurança alimentar, política para mulheres e "
    "primeira infância, a de 2025 traz meio ambiente e gestão de riscos e desastres, e as "
    "demais trazem recursos humanos, habitação, transporte e governança. Cada aba sai como "
    "arquivo próprio; o parâmetro indicadores escolhe as edições. Sem identificador pessoal.",
    (
        HttpResource(
            "2018",
            _MUNIC + "2018/Base_de_Dados/Base_MUNIC_2018_xlsx_20201103.zip",
            "MUNIC 2018",
        ),
        HttpResource(
            "2019", _MUNIC + "2019/Base_de_Dados/Base_MUNIC_2019_20210817.xlsx", "MUNIC 2019"
        ),
        HttpResource("2020", _MUNIC + "2020/Base_de_Dados/Base_MUNIC_2020.xlsx", "MUNIC 2020"),
        HttpResource(
            "2021", _MUNIC + "2021/Base_de_Dados/Base_MUNIC_2021_20240425.xlsx", "MUNIC 2021"
        ),
        HttpResource("2023", _MUNIC + "2023/Base_de_Dados/Base_MUNIC_2023.xlsx", "MUNIC 2023"),
        HttpResource("2025", _MUNIC + "2025/Base_de_Dados/Base_MUNIC_2025.xlsx", "MUNIC 2025"),
    ),
    file_format="xlsx",
    selector="indicadores",
)

IBGE_ESTADIC = HttpFile(
    "ibge_estadic",
    "IBGE ESTADIC: Perfil dos estados",
    "Pesquisa de Informações Básicas Estaduais (IBGE), base completa de cada edição em xlsx "
    "(2018, 2019, 2020, 2021, 2023, 2024 e 2025): uma linha por unidade da federação, com a "
    "gestão estadual em blocos temáticos que mudam a cada edição (a de 2023 traz assistência "
    "social, direitos humanos, política para mulheres, primeira infância, recursos humanos, "
    "segurança alimentar, segurança pública e trabalho e inclusão produtiva) e uma aba de "
    "dicionário. Cada aba sai como arquivo próprio; o parâmetro indicadores escolhe as "
    "edições. Sem identificador pessoal.",
    (
        HttpResource(
            "2018", _ESTADIC + "2018/Base_ESTADIC_2018_20201215.xlsx", "ESTADIC 2018"
        ),
        HttpResource("2019", _ESTADIC + "2019/Base_ESTADIC_2019.xlsx", "ESTADIC 2019"),
        HttpResource("2020", _ESTADIC + "2020/Base_Estadic_2020.xlsx", "ESTADIC 2020"),
        HttpResource("2021", _ESTADIC + "2021/Base_Estadic_2021.xlsx", "ESTADIC 2021"),
        HttpResource("2023", _ESTADIC + "2023/Base_Estadic_2023.xlsx", "ESTADIC 2023"),
        HttpResource("2024", _ESTADIC + "2024/Base_Estadic_2024.xlsx", "ESTADIC 2024"),
        HttpResource("2025", _ESTADIC + "2025/Base_Estadic_2025.xlsx", "ESTADIC 2025"),
    ),
    file_format="xlsx",
    selector="indicadores",
)

IBGE_MUNIC_SANEAMENTO = HttpFile(
    "ibge_munic_saneamento",
    "IBGE MUNIC: Suplementos de saneamento básico (2017 e 2023)",
    "Suplementos de saneamento básico da MUNIC (IBGE), com uma linha por município: a "
    "edição de 2017 (abastecimento de água e esgotamento sanitário) e a de 2023 (dados gerais, "
    "resíduos sólidos e drenagem), cada aba como arquivo próprio e com uma aba de dicionário. "
    "O parâmetro indicadores escolhe a edição. Sem identificador pessoal.",
    (
        HttpResource(
            "2017",
            _MUNIC
            + "Gestao_do_Saneamento_Basico_2017/"
            + "base_abastecimento_agua_esgotamento_sanitario_MUNIC2017.xlsx",
            "Saneamento MUNIC 2017",
        ),
        HttpResource(
            "2023",
            _MUNIC
            + "Saneamento_2023/Base_de_Dados/Base_de_Dados_Suplemento_de_Saneamento_2023.xlsx",
            "Suplemento de saneamento MUNIC 2023",
        ),
    ),
    file_format="xlsx",
    selector="indicadores",
)

SPECS: Tuple[HttpFile, ...] = (IBGE_MUNIC_EDICOES, IBGE_ESTADIC, IBGE_MUNIC_SANEAMENTO)
MODES: Dict[str, str] = {spec.key: "ibge files" for spec in SPECS}
