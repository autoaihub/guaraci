"""SB Brasil: levantamentos nacionais de saúde bucal do Ministério da Saúde (1986, 1996, 2003).

Endereços conferidos ao vivo em 2026-11-14:

- 1986: ``levantamento-sb-1986.xlsx`` (1,5 MB) com duas abas, crianças (12.313 linhas, 15
  colunas) e adultos e adolescentes (10.402 linhas, 21 colunas), no portal do Ministério.
- 1996: ``sb96.zip`` (256 KB) no TabNet do DATASUS, com ``SB96.DBF`` (30.240 linhas, 32
  colunas: UF, município, idade, sexo e a condição de cada dente).
- 2003: cinco zips regionais (0,8 a 1,2 MB) com um DBF de 243 colunas cada (por exemplo,
  24.058 linhas no Sudeste) e a lista de variáveis em PDF. O portal guarda esses arquivos
  sob ``arquivos/2020/`` (ano do envio), mas o conteúdo é o levantamento de 2002-2003.

Os microdados do SB Brasil 2010 não estão publicados (só o dicionário de variáveis, em xls)
e os do SB Brasil 2020 ainda não foram divulgados. O portal do Ministério responde 403 ao
HEAD, por isso as fontes do portal usam sonda por GET de 1 byte e User-Agent de navegador.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource
from guaraci.inqueritos.leitores import datasource_com_leitor, ler_dbf

_PORTAL = "https://www.gov.br/saude/pt-br/composicao/saps/brasil-sorridente/sb-brasil/"
_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

_ORIGEM = (
    "Microdados do levantamento epidemiológico em saúde bucal do Ministério da Saúde "
    "(SAPS/Coordenação-Geral de Saúde Bucal). Amostra de pessoas examinadas, sem nome nem "
    "documento; traz município ou UF, idade e sexo."
)

SB_BRASIL_1986 = HttpFile(
    "sb_brasil_1986",
    "SB Brasil 1986 - Levantamento epidemiológico em saúde bucal",
    "Exame bucal de crianças e de adultos e adolescentes no levantamento nacional de 1986, "
    "uma saída por aba (crianças e adultos e adolescentes): idade, sexo, UF, dentes cariados, "
    "obturados e extraídos (CPO), uso de escova e índices periodontais. " + _ORIGEM,
    (HttpResource("1986", _PORTAL + "dados/1986/levantamento-sb-1986.xlsx"),),
    file_format="xlsx",
    user_agent=_NAVEGADOR,
    probe="range",
)

SB_BRASIL_1996 = HttpFile(
    "sb_brasil_1996",
    "SB Brasil 1996 - Cárie dentária em escolares das capitais",
    "Exame de cárie de escolares de 6 a 12 anos nas capitais em 1996: UF, município, idade, "
    "sexo e a condição de cada um dos 28 dentes permanentes (dentes 11 a 47). Tabela única "
    "em DBF, publicada no TabNet. " + _ORIGEM,
    (HttpResource("1996", "https://tabnet.datasus.gov.br/cgi/sbucal/sb96.zip"),),
    member="SB96.DBF",
)

_REGIOES = (
    ("co", "Centro-Oeste"),
    ("ne", "Nordeste"),
    ("no", "Norte"),
    ("se", "Sudeste"),
    ("su", "Sul"),
)

SB_BRASIL_2003 = HttpFile(
    "sb_brasil_2003",
    "SB Brasil 2003 - Condições de saúde bucal da população brasileira",
    "Levantamento nacional de 2002-2003 com crianças de 18 a 36 meses, 5 e 12 anos, "
    "adolescentes, adultos e idosos, um zip por região (co, ne, no, se, su) com 243 colunas: "
    "cárie, necessidade de prótese, fluorose, oclusão, condição periodontal, dentes por "
    "dente e uso de serviço odontológico. Cada zip traz também a lista de variáveis em PDF, "
    "que não é exportada. " + _ORIGEM,
    tuple(
        HttpResource(code, f"{_PORTAL}arquivos/2020/sbbrasil_{code}.zip", title)
        for code, title in _REGIOES
    ),
    selector="indicadores",
    member_pattern=r"\.dbf$",
    user_agent=_NAVEGADOR,
    probe="range",
)

SPECS: Tuple[HttpFile, ...] = (SB_BRASIL_1986, SB_BRASIL_1996, SB_BRASIL_2003)
MODES: Dict[str, str] = {spec.key: "saude bucal files" for spec in SPECS}
DATASOURCES: Dict[str, type] = {
    "sb_brasil_1996": datasource_com_leitor(SB_BRASIL_1996, ler_dbf()),
    "sb_brasil_2003": datasource_com_leitor(SB_BRASIL_2003, ler_dbf()),
}
