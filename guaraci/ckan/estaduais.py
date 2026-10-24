"""Conjuntos CKAN estaduais e municipais: Recife, Porto Alegre (GERCON) e Minas Gerais.

Verificado ao vivo em 2026-10-23 (``package_show``, ``package_search`` e primeiros
bytes de cada arquivo; relatório em ``docs/sondagem_2026-10/estaduais_catalogos.md``).

Particularidades de cada portal:

- Recife: o download redireciona para um S3 assinado (o núcleo segue o
  redirecionamento sem guardar a URL). Os três agravos (dengue, chikungunya e
  zika) moram num só pacote e são separados pelo nome do recurso. Os arquivos
  de 2013 a 2015 têm outro leiaute (nomes em minúsculas e data com barra) que os
  de 2016 em diante (leiaute SINAN, maiúsculas).
- Porto Alegre: um CSV por ano, de 130 a 570 MB; por isso ``period_required``.
- Minas Gerais: o portal recusa o User-Agent padrão (``browser_user_agent``) e o
  ``datastore_search`` devolve ``total`` 0, então baixa-se sempre o recurso.
"""

from __future__ import annotations

from typing import Dict

from guaraci.ckan.datasets import CkanDataset

__all__ = [
    "CKAN_ESTADUAIS",
    "RECIFE_BASE_URL",
    "POA_BASE_URL",
    "MG_BASE_URL",
    "FHEMIG_QUERY",
]

RECIFE_BASE_URL = "https://dados.recife.pe.gov.br/api/3/action/"
POA_BASE_URL = "https://dadosabertos.poa.br/api/3/action/"
MG_BASE_URL = "https://dados.mg.gov.br/api/3/action/"
FHEMIG_QUERY = "organization:fundacao-hospitalar-do-estado-de-minas-gerais-fhemig"

_RECIFE_PACOTE = "casos-de-dengue-zika-e-chikungunya"
_RECIFE_NOTA = (
    "Registro individual no leiaute SINAN, com bairro, logradouro e CEP de residência e data de "
    "nascimento. Traz identificador pessoal indireto (NM_BAIRRO, NM_LOGRADO, NU_CEP e DT_NASC; "
    "sem CPF nem nome), publicado assim pelo órgão; o tratamento LGPD fica nas camadas prata e "
    "ouro do Sabiá. Um CSV por ano. Os arquivos de 2013 a 2015 usam outro leiaute (nomes de "
    "coluna em minúsculas, datas com barra) que os de 2016 em diante, e cada um sai separado. "
    "Sem 'anos' baixa todos os anos."
)

_MG_NOTA = (
    "Espelha o SINAN de residentes em Minas Gerais, com município e data de nascimento por "
    "caso e sem nome nem CPF; o município vem por extenso, não por código. Publicado assim pelo "
    "órgão; o tratamento LGPD fica nas camadas prata e ouro do Sabiá. Atualização semanal, "
    "arquivo único que substitui o anterior."
)

_ANO = r"(?P<year>(?:19|20)\d{2})"

_SPECS = (
    CkanDataset(
        key="recife_dengue",
        title="Recife Casos de dengue (SINAN, com bairro e logradouro)",
        description="Casos de dengue notificados em Recife, 2013 a 2025. " + _RECIFE_NOTA,
        base_url=RECIFE_BASE_URL,
        package_ids=(_RECIFE_PACOTE,),
        resource_pattern=r"^Casos de Dengue",
        file_format="csv",
        separator=";",
        period_pattern=_ANO,
    ),
    CkanDataset(
        key="recife_chikungunya",
        title="Recife Casos confirmados de chikungunya (SINAN, com bairro e logradouro)",
        description="Casos confirmados de chikungunya em Recife, 2015 a 2025. " + _RECIFE_NOTA,
        base_url=RECIFE_BASE_URL,
        package_ids=(_RECIFE_PACOTE,),
        resource_pattern=r"^Casos confirmados de Chikungunya",
        file_format="csv",
        separator=";",
        period_pattern=_ANO,
    ),
    CkanDataset(
        key="recife_zika",
        title="Recife Casos confirmados de zika (SINAN, com bairro e logradouro)",
        description="Casos confirmados de zika em Recife, 2015 a 2025. " + _RECIFE_NOTA,
        base_url=RECIFE_BASE_URL,
        package_ids=(_RECIFE_PACOTE,),
        resource_pattern=r"^Casos confirmados de Zika",
        file_format="csv",
        separator=";",
        period_pattern=_ANO,
    ),
    CkanDataset(
        key="poa_gercon_consultas",
        title="Porto Alegre GERCON Solicitações de consultas especializadas",
        description=(
            "Fila de consultas especializadas regulada pelo GERCON (SMS Porto Alegre e sistema de "
            "regulação do RS), uma linha por solicitação, 2017 a 2026: especialidade, CID, "
            "complexidade, dias de espera, município de residência, unidade solicitante e "
            "executante e situação da agenda. Traz identificador pessoal pseudonimizado "
            "(idpaciente) e idade, publicado assim pelo órgão; o tratamento LGPD fica nas camadas "
            "prata e ouro do Sabiá. Um CSV por ano, de 130 a 570 MB (cerca de 3,3 GB no total): "
            "'anos' é obrigatório, peça poucos por vez. Os arquivos são regravados com frequência "
            "(coluna data_extracao)."
        ),
        base_url=POA_BASE_URL,
        package_ids=("gercon-gerenciamento-de-consultas",),
        file_format="csv",
        separator=";",
        period_required=True,
    ),
    CkanDataset(
        key="fhemig_indicadores_hospitalares",
        title="FHEMIG Indicadores hospitalares por unidade (MG)",
        description=(
            "Indicadores de desempenho dos hospitais da Fundação Hospitalar do Estado de Minas "
            "Gerais, por unidade e mês: internações, saídas, óbitos, partos, giro de leitos, "
            "paciente-dia, média de permanência, CRIB, APACHE, case mix, readmissão e "
            "ineficiência operacional. São 27 conjuntos do portal dados.mg.gov.br, um CSV por "
            "recurso, com leiautes próprios (alguns recursos são anuais). Dado agregado, sem "
            "identificador pessoal. Para escolher conjuntos use 'recursos' com um trecho do nome "
            "do arquivo (por exemplo 'readmissao' ou 'case-mix'); o trecho 'internacoes' também "
            "casa com 'internacoes-via-urgencia'."
        ),
        base_url=MG_BASE_URL,
        package_query=FHEMIG_QUERY,
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
    CkanDataset(
        key="mg_hanseniase",
        title="SES-MG Hanseníase (SINAN, residentes em MG)",
        description="Casos de hanseníase notificados de residentes em Minas Gerais. " + _MG_NOTA,
        base_url=MG_BASE_URL,
        package_ids=("hanseniase",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
    CkanDataset(
        key="mg_aids_hiv",
        title="SES-MG Aids e HIV (SINAN, residentes em MG)",
        description=(
            "Casos de aids e infecção pelo HIV notificados de residentes em Minas Gerais. "
            + _MG_NOTA
        ),
        base_url=MG_BASE_URL,
        package_ids=("aids_hiv",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
    CkanDataset(
        key="mg_tuberculose",
        title="SES-MG Tuberculose (SINAN, residentes em MG)",
        description="Casos de tuberculose notificados de residentes em Minas Gerais. " + _MG_NOTA,
        base_url=MG_BASE_URL,
        package_ids=("dados-tuberculose",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
    CkanDataset(
        key="mg_acidentes_transporte",
        title="SES-MG Óbitos por acidentes de transporte terrestre (SIM, MG)",
        description=(
            "Óbitos por acidentes de transporte terrestre em Minas Gerais (SIM), com município de "
            "residência e de ocorrência, CID-10 da causa básica, sexo, raça ou cor e idade. Traz "
            "data de nascimento e do óbito, sem nome nem CPF, publicado assim pelo órgão; o "
            "tratamento LGPD fica nas camadas prata e ouro do Sabiá. Atualização semanal, "
            "arquivo único."
        ),
        base_url=MG_BASE_URL,
        package_ids=("acidentes-terrestres-transito",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
)

CKAN_ESTADUAIS: Dict[str, CkanDataset] = {spec.key: spec for spec in _SPECS}
