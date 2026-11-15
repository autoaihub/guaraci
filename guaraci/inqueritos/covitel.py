"""Covitel 2022 e 2023: inquérito telefônico de fatores de risco para doenças crônicas.

Vital Strategies e UFPel, com apoio da Umane. Os zips ficam no CloudFront do Observatório de
Saúde Pública (``d25b3ziafo7gx4.cloudfront.net/covitel/microdados/``), linkados da página
``observatoriosaudepublica.com.br/pesquisas/covitel/`` e conferidos em 2026-11-14:

- 2022: 7,3 MB, com ``covitel_observatorio.xlsx`` (9.004 linhas, 167 colunas) e o mesmo dado em
  ``.dta``;
- 2023: 7,2 MB, com ``BD_Covitel_2023imputed_com_peso.csv`` (9.038 linhas, 205 colunas) e o mesmo dado
  em ``.dta`` e ``.xls``.

Nem a página nem os zips declaram licença ou termos de uso (nada no rodapé nem nos arquivos).
O dado é de acesso público por link, e a entrada segue a regra das fontes secundárias com dado
próprio: cita-se a origem. A licença fica registrada como não declarada.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_BASE = "https://d25b3ziafo7gx4.cloudfront.net/covitel/microdados/"

_ORIGEM = (
    "Inquérito telefônico (telefone fixo e celular) com adultos das cinco regiões, "
    "representativo por região, da Vital Strategies com a Universidade Federal de Pelotas, "
    "divulgado pelo Observatório de Saúde Pública (Umane). A licença não é declarada na "
    "origem; use com a citação do Covitel. Traz município, DDD, data da entrevista e "
    "características do entrevistado, sem nome nem telefone."
)

COVITEL_2022 = HttpFile(
    "covitel_2022",
    "Covitel 2022 - Inquérito telefônico de fatores de risco para DCNT",
    "Entrevistas do Covitel 2022 (9.004 linhas): tabagismo, álcool, alimentação, "
    "atividade física, hipertensão, diabetes, saúde mental e uso de serviços, com peso "
    "amostral. " + _ORIGEM,
    (HttpResource("2022", _BASE + "covitel_microdados_2022.zip"),),
    member="covitel_observatorio.xlsx",
    file_format="xlsx",
)

COVITEL_2023 = HttpFile(
    "covitel_2023",
    "Covitel 2023 - Inquérito telefônico de fatores de risco para DCNT",
    "Entrevistas do Covitel 2023 (9.038 linhas), com dados imputados e peso amostral: "
    "tabagismo, álcool, alimentação, atividade física, hipertensão, diabetes, saúde mental e "
    "uso de serviços. " + _ORIGEM,
    (HttpResource("2023", _BASE + "covitel_microdados_2023.zip"),),
    member="Dados Covitel 2023/BD_Covitel_2023imputed_com_peso.csv",
)

SPECS: Tuple[HttpFile, ...] = (COVITEL_2022, COVITEL_2023)
MODES: Dict[str, str] = {spec.key: "covitel files" for spec in SPECS}
