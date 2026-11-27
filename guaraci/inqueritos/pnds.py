"""PNDS 2006: Pesquisa Nacional de Demografia e Saúde da Criança e da Mulher.

Um zip de 23 MB (``bvsms.saude.gov.br/bvs/pnds/bases/spss.zip``, publicado em janeiro de 2010)
traz seis tabelas em largura fixa (``.dat``) com o dicionário Stata (``.dct``) de cada uma, mais
os mesmos dados em ``.sav`` (SPSS), SAS, Stata e SPSS syntax. A exportação lê o par ``.dat`` e
``.dct``: domicílios e pessoas, mulheres, filhos, gravidezes, medicamentos e medicamentos por
domicílio. O ``.sav`` não é lido (sem leitor SPSS no projeto) e a base ``DOM_PESS_mulheres`` só
existe nesse formato.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource
from guaraci.inqueritos.leitores import datasource_com_leitor, ler_largura_fixa

PNDS_2006 = HttpFile(
    "pnds_2006",
    "PNDS 2006 - Pesquisa Nacional de Demografia e Saúde da Criança e da Mulher",
    "Inquérito domiciliar nacional de 2006 do Ministério da Saúde com o Cebrap: fecundidade, "
    "saúde reprodutiva, assistência à gestação e ao parto, amamentação, vacinação, "
    "antropometria e anemia de crianças e mulheres, segurança alimentar. Uma saída por tabela "
    "(domicílios e pessoas, mulheres, filhos, gravidezes, medicamentos), cada uma com os "
    "nomes de coluna do dicionário Stata publicado. Amostra de domicílios sem nome nem "
    "documento; traz região, estado, situação do domicílio e idades.",
    (HttpResource("2006", "https://bvsms.saude.gov.br/bvs/pnds/bases/spss.zip"),),
    member_pattern=r"\.dat$",
)

SPECS: Tuple[HttpFile, ...] = (PNDS_2006,)
MODES: Dict[str, str] = {spec.key: "pnds files" for spec in SPECS}
DATASOURCES: Dict[str, type] = {
    "pnds_2006": datasource_com_leitor(PNDS_2006, ler_largura_fixa(), prefixo="pnds2006_br_"),
}
