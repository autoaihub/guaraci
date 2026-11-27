"""Cetic.br (NIC.br): TIC Saúde e TIC Domicílios, microdados em CC BY 4.0.

Conferidos ao vivo em 2026-11-14 nas páginas ``cetic.br/pt/pesquisa/saude/microdados/`` e
``.../domicilios/microdados/``, que declaram a licença CC BY 4.0 e pedem a citação "Núcleo de
Informação e Coordenação do Ponto BR":

- TIC Saúde 2025, estabelecimentos de saúde (base pós CEC): zip de 2,3 MB com o CSV em UTF-8,
  separado por ``;`` (3.261 linhas, 348 colunas), mais ``.sav`` e ``.RData`` do mesmo dado. O zip ``tic_saude_2025_microdados``
  (14 MB) só traz dicionário, questionários e tabelas, sem a base, e não entra;
- TIC Domicílios 2025: CSV direto de 36 MB, separado por ``;`` (27.177 linhas, 271 colunas).

A URL leva um número de arquivo que o Cetic.br troca a cada edição (``1072`` e ``1018``): a
edição seguinte pede nova entrada. Só a edição mais recente de cada pesquisa fica na página.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_BASE = "https://cetic.br/media/microdados/"

_ORIGEM = (
    "Microdados do Cetic.br/NIC.br, licença Atribuição 4.0 Internacional (CC BY 4.0); citar "
    "Núcleo de Informação e Coordenação do Ponto BR. Amostra com peso, sem nome nem "
    "documento; as colunas seguem os códigos do dicionário de variáveis do Cetic.br."
)

CETIC_TIC_SAUDE = HttpFile(
    "cetic_tic_saude_estabelecimentos",
    "Cetic.br - TIC Saúde, estabelecimentos de saúde (2025)",
    "Pesquisa sobre o uso das tecnologias de informação e comunicação nos estabelecimentos de "
    "saúde brasileiros, edição 2025, base de estabelecimentos (3.261 respostas, 348 colunas), com região e peso "
    "amostral. " + _ORIGEM,
    (HttpResource("2025", _BASE + "1072/tic_saude_2025_estabelecimentos_p%C3%B3s_cec_base_de_microdados.zip"),),
    separator=";",
    member_pattern=r"base_de_microdados.*\.csv$",
)

CETIC_TIC_DOMICILIOS = HttpFile(
    "cetic_tic_domicilios",
    "Cetic.br - TIC Domicílios (2025)",
    "Pesquisa sobre o uso das tecnologias de informação e comunicação nos domicílios "
    "brasileiros, edição 2025 (27.177 respostas, 271 colunas): UF, área, renda familiar, posse de "
    "equipamentos e acesso à internet. " + _ORIGEM,
    (HttpResource("2025", _BASE + "1018/tic_domicilios_2025_domicilios_base_de_microdados_v1.0.csv"),),
    separator=";",
)

SPECS: Tuple[HttpFile, ...] = (CETIC_TIC_SAUDE, CETIC_TIC_DOMICILIOS)
MODES: Dict[str, str] = {spec.key: "cetic files" for spec in SPECS}
