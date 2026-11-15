"""Conjuntos CKAN estaduais e municipais: Recife, Porto Alegre (GERCON), Minas Gerais, SEADE (SP) e SES-GO.

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
- SEADE (SP): um pacote por conteúdo; cada pacote traz o CSV de dados e o dicionário
  como outro CSV, que ``exclude_pattern`` tira. Os arquivos "ano corrente" mantêm a mesma
  URL e são regravados todo mês (na virada do ano o recurso passa a trazer o ano novo).
  Verificado ao vivo em 2026-11-14.
- SES-GO: o portal fica atrás de um WAF (F5) que responde 200 com HTML ("Acesso Negado" ou
  desafio em JavaScript) em vez do JSON. A resposta é intermitente e depende do cliente:
  o ``Mozilla/5.0`` literal falhou logo; o User-Agent do núcleo passou em dezenas de
  consultas seguidas e foi barrado depois de uma rajada (cerca de 70 chamadas em pouco
  mais de um minuto), com a liberação vindo em alguns minutos; um User-Agent de navegador
  completo passou no curl e falhou no urllib. Por isso as chaves usam o User-Agent padrão
  e não ``browser_user_agent``, e convém não paralelizar nem repetir as 14 chaves em
  rajada. Os recursos têm nome de arquivo fixo e sem ano (regravados), e cada pacote traz
  também um PDF de dicionário, que o ``file_format`` já descarta. Verificado em 2026-11-14.
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
    "SEADE_BASE_URL",
    "GO_BASE_URL",
]

RECIFE_BASE_URL = "https://dados.recife.pe.gov.br/api/3/action/"
POA_BASE_URL = "https://dadosabertos.poa.br/api/3/action/"
MG_BASE_URL = "https://dados.mg.gov.br/api/3/action/"
SEADE_BASE_URL = "https://repositorio.seade.gov.br/api/3/action/"
GO_BASE_URL = "https://dadosabertos.go.gov.br/api/3/action/"
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

_SEADE_EXCLUI_DICIONARIO = r"Dicion|/dic"
_SEADE_NOTA = (
    "Fundação SEADE, estatísticas vitais colhidas nos cartórios de registro civil de São Paulo, "
    "com código IBGE do município quando o recorte é municipal. Dado agregado, sem "
    "identificador pessoal. Um CSV por recurso, com leiautes próprios; o dicionário de "
    "variáveis do portal fica de fora."
)
_SEADE_CORRENTE = (
    " Arquivo do ano corrente: o portal regrava o mesmo recurso a cada mês e, na virada do ano, "
    "ele passa a trazer o ano novo; a série fechada está na chave de série histórica."
)


def _seade(key: str, title: str, description: str, package_id: str) -> CkanDataset:
    return CkanDataset(
        key=key,
        title=title,
        description=description,
        base_url=SEADE_BASE_URL,
        package_ids=(package_id,),
        exclude_pattern=_SEADE_EXCLUI_DICIONARIO,
        file_format="csv",
        separator=";",
    )


_GO_NOTA = (
    "Secretaria de Estado da Saúde de Goiás (portal de dados abertos), CSV com ';', um "
    "arquivo por recurso regravado pelo órgão, sem ano no nome. O dicionário de dados do "
    "portal é PDF e fica de fora."
)
_GO_INDIVIDUAL = (
    " Registro individual sem nome nem CPF, com número da notificação, publicado assim pelo "
    "órgão; o tratamento LGPD fica nas camadas prata e ouro do Sabiá."
)


def _go(key: str, title: str, description: str, *package_ids: str) -> CkanDataset:
    return CkanDataset(
        key=key,
        title=title,
        description=description,
        base_url=GO_BASE_URL,
        package_ids=tuple(package_ids),
        file_format="csv",
        separator=";",
    )


_SPECS_LEVA7 = (
    _seade(
        "seade_obitos_sp_serie",
        "SEADE Óbitos no Estado de SP (série histórica, 2000 a 2025)",
        "Óbitos do Estado de São Paulo por município e ano (2000 a 2025), por mês de ocorrência "
        "e área (2018 a 2025) e por sexo e faixa etária (2019 a 2025). " + _SEADE_NOTA,
        "obitos",
    ),
    _seade(
        "seade_obitos_sp_ano_corrente",
        "SEADE Óbitos no Estado de SP (ano corrente, por mês)",
        "Óbitos do Estado de São Paulo no ano corrente por município e mês de ocorrência e por "
        "sexo e faixa etária. " + _SEADE_NOTA + _SEADE_CORRENTE,
        "obitos-estado-de-sp-ano-corrente",
    ),
    _seade(
        "seade_nascidos_vivos_sp_serie",
        "SEADE Nascidos vivos no Estado de SP (série histórica, 2000 a 2025)",
        "Nascidos vivos do Estado de São Paulo por município e ano (2000 a 2025), por sexo "
        "(2019 a 2025) e por faixa etária da mãe (2000, 2010 e 2025). " + _SEADE_NOTA,
        "nascidos-vivos-estado-de-sp-serie-historica",
    ),
    _seade(
        "seade_nascidos_vivos_sp_ano_corrente",
        "SEADE Nascidos vivos no Estado de SP (ano corrente, por mês)",
        "Nascidos vivos do Estado de São Paulo no ano corrente por município e mês de ocorrência, "
        "por sexo e por faixa etária da mãe. " + _SEADE_NOTA + _SEADE_CORRENTE,
        "nascidos-vivos",
    ),
    _seade(
        "seade_mortalidade_geral_sp",
        "SEADE Mortalidade geral no Estado de SP (painel, 2000 a 2024)",
        "Painel de mortalidade geral do Estado de São Paulo, 2000 a 2024. " + _SEADE_NOTA,
        "mortalidade-no-estado-de-sao-paulo",
    ),
    _seade(
        "seade_mortalidade_infantil_sp",
        "SEADE Mortalidade infantil no Estado de SP (painel)",
        "Óbitos infantis do Estado de São Paulo ao longo do tempo e por principais causas. "
        + _SEADE_NOTA,
        "mortalidade-infantil",
    ),
    _seade(
        "seade_esperanca_vida_sp",
        "SEADE Esperança de vida ao nascer em São Paulo (painel)",
        "Esperança de vida ao nascer no Estado de São Paulo, estimada pela SEADE. " + _SEADE_NOTA,
        "esperanca-de-vida",
    ),
    _seade(
        "seade_fecundidade_sp",
        "SEADE Fecundidade e natalidade em São Paulo (painel)",
        "Taxa de fecundidade total, fecundidade e natalidade por município do Estado de São "
        "Paulo e por distrito do município de São Paulo, com a variação entre 2000, 2010 e o "
        "ano mais recente. " + _SEADE_NOTA,
        "seade-fecundidade",
    ),
    _seade(
        "seade_saude_painel_sp",
        "SEADE Recursos de saúde por município de SP (painel)",
        "Leitos por município (2010 a 2024), médicos e enfermeiros por município, médicos por "
        "tipo, estabelecimentos de saúde e profissionais por região de saúde do Estado de São "
        "Paulo, a partir do CNES, 2024. " + _SEADE_NOTA,
        "saude-painel",
    ),
    _seade(
        "seade_ipvs_2022",
        "SEADE Índice Paulista de Vulnerabilidade Social (IPVS 2022, tabelas)",
        "IPVS 2022 do Estado e do município de São Paulo: população, domicílios e setores "
        "censitários por grupo de vulnerabilidade. " + _SEADE_NOTA,
        "ipvs-populacao-domicilios-e-setores-censitarios",
    ),
    _seade(
        "seade_ipvs_2010",
        "SEADE Índice Paulista de Vulnerabilidade Social (IPVS 2010, por setor censitário)",
        "Base do IPVS 2010 por setor censitário do Estado de São Paulo (cerca de 28 MB). "
        + _SEADE_NOTA,
        "ipvs2010-base-de-dados",
    ),
    _go(
        "ses_go_mapa_leitos",
        "SES-GO Mapa de leitos (histórico por unidade e tipo de acomodação)",
        "Histórico diário de leitos das unidades de saúde de Goiás por tipo de acomodação: "
        "implantados, vagos, ocupados, bloqueados, reservados e taxa de ocupação. Sete recursos: "
        "o geral e os de UTI adulto, UTI neonatal, UTI pediátrica, enfermaria adulto, enfermaria "
        "pediátrica e UCIN. Dado agregado por unidade, sem identificador pessoal. " + _GO_NOTA,
        "mapa-de-leitos",
    ),
    _go(
        "ses_go_dengue",
        "SES-GO Dengue (casos notificados e sorotipos)",
        "Casos notificados de dengue em Goiás por município de residência, semana epidemiológica, "
        "classificação, critério de confirmação e evolução (cerca de 196 MB), e testes de "
        "sorotipo por município e semana. Sem identificador pessoal nem número de notificação. "
        + _GO_NOTA,
        "dengue",
    ),
    _go(
        "ses_go_zika_chikungunya",
        "SES-GO Zika e chikungunya (casos notificados)",
        "Casos notificados de zika e de chikungunya em Goiás por município de residência, "
        "semana epidemiológica, classificação e óbito. Sem identificador pessoal. " + _GO_NOTA,
        "aedes",
    ),
    _go(
        "ses_go_arboviroses_internacao",
        "SES-GO Solicitações de internação por arbovirose (regulação)",
        "Solicitações de internação por arbovirose (CID A90 e afins) reguladas pelo estado: "
        "prioridade, status, tempo de resolução, tipo de leito, município e região de saúde do "
        "paciente e hospitais solicitante e executante. Traz o código da ficha de regulação, "
        "sem nome nem CPF, publicado assim pelo órgão; o tratamento LGPD fica nas camadas prata e "
        "ouro do Sabiá. " + _GO_NOTA,
        "arbovirose",
    ),
    _go(
        "ses_go_srag",
        "SES-GO Síndrome respiratória aguda grave (casos notificados)",
        "Casos de SRAG notificados em Goiás: datas, município de residência, sexo, faixa etária, "
        "raça ou cor, classificação final, vírus identificados, evolução e comorbidades "
        "(cerca de 42 MB)." + _GO_INDIVIDUAL + " " + _GO_NOTA,
        "srag",
    ),
    _go(
        "ses_go_sindrome_gripal",
        "SES-GO Síndrome gripal (notificações)",
        "Notificações de síndrome gripal em Goiás: unidade notificadora (CNES), datas, município, "
        "sexo, faixa etária, classificação, vírus e comorbidades. Traz o número da notificação e "
        "o número do GAL, sem nome nem CPF, publicado assim pelo órgão; o tratamento LGPD fica "
        "nas camadas prata e ouro do Sabiá. " + _GO_NOTA,
        "sindrome-gripal-sg",
    ),
    _go(
        "ses_go_mortalidade",
        "SES-GO Mortalidade (geral, infantil, na infância e materna)",
        "Óbitos de residentes e ocorridos em Goiás por município, ano, faixa etária, sexo e CID-10 "
        "(cerca de 58 MB no recurso geral), em quatro recursos: geral, infantil, na infância e "
        "materna. Dado agregado, sem identificador pessoal. " + _GO_NOTA,
        "mortalidade",
    ),
    _go(
        "ses_go_hiv_aids",
        "SES-GO HIV e aids (casos, crianças, gestantes e óbitos)",
        "Casos de HIV e de aids em Goiás por data de diagnóstico, município, região de saúde, "
        "sexo, raça ou cor, faixa etária e escolaridade, mais as taxas em gestantes e os óbitos "
        "por aids. Dado por caso sem identificador pessoal. " + _GO_NOTA,
        "ist-hiv",
        "ist-aids",
    ),
    _go(
        "ses_go_sifilis",
        "SES-GO Sífilis (adquirida, em gestantes e congênita)",
        "Casos de sífilis adquirida, em gestantes e congênita em Goiás, com óbitos por sífilis "
        "congênita e taxas: data, município, região de saúde, sexo, raça ou cor, faixa etária, "
        "escolaridade e, na congênita, esquema de tratamento e pré-natal. Dado por caso sem "
        "identificador pessoal. " + _GO_NOTA,
        "ist-sifilis",
    ),
    _go(
        "ses_go_hepatites",
        "SES-GO Hepatites virais (casos e óbitos)",
        "Casos e óbitos por hepatites B e C em Goiás por município, região de saúde, sexo, raça "
        "ou cor, faixa etária, escolaridade e provável tipo de infecção. Dado por caso sem "
        "identificador pessoal. " + _GO_NOTA,
        "ist-hepatite",
    ),
    _go(
        "ses_go_tuberculose",
        "SES-GO Tuberculose (casos notificados)",
        "Casos de tuberculose notificados em Goiás: forma, populações vulneráveis, agravos "
        "associados, exames, baciloscopias mensais e situação de encerramento, com município de "
        "residência." + _GO_INDIVIDUAL + " " + _GO_NOTA,
        "tuberculose",
    ),
    _go(
        "ses_go_hanseniase",
        "SES-GO Hanseníase (casos notificados)",
        "Casos de hanseníase notificados em Goiás: município de notificação e de residência, "
        "classificação operacional, forma clínica, incapacidade, esquema terapêutico, contatos, "
        "sexo, raça ou cor, escolaridade e ocupação (cerca de 10 MB). Dado por caso sem "
        "identificador pessoal. " + _GO_NOTA,
        "hanseniase",
    ),
    _go(
        "ses_go_regulacao_indicadores",
        "SES-GO Regulação (indicadores de consulta, exame e cirurgia)",
        "Indicadores mensais da regulação estadual: vagas ofertadas, agendamentos, "
        "comparecimento, faltas, perdas e tempo médio de espera por unidade e especialidade "
        "(consultas e exames) e fila e procedimentos por especialidade (cirurgias). Dado "
        "agregado, sem identificador pessoal. " + _GO_NOTA,
        "transparencia-regulacao-indicadores",
    ),
    _go(
        "ses_go_oncologia",
        "SES-GO Oncologia (casos novos de câncer)",
        "Casos novos de câncer em Goiás (a partir de 2013) com unidade de diagnóstico e de "
        "tratamento, município de residência, CID, estadiamento, tratamento e tempo até o "
        "primeiro tratamento (cerca de 58 MB), mais o recurso agrupado por local. O recurso "
        "individual traz data de nascimento, sem nome nem CPF, publicado assim pelo órgão; o "
        "tratamento LGPD fica nas camadas prata e ouro do Sabiá. " + _GO_NOTA,
        "oncologia",
    ),
)

CKAN_ESTADUAIS: Dict[str, CkanDataset] = {spec.key: spec for spec in _SPECS + _SPECS_LEVA7}
