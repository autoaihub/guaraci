"""Conjuntos CKAN dos portais federais: MMA, INSS, SENATRAN, BNDES e MAPA.

Verificado ao vivo em 2026-10-23 (``package_show`` e primeiros bytes de cada
arquivo; relatórios em ``docs/sondagem_2026-10/``). Os nomes de arquivo do INSS
são inconsistentes de mês a mês e por isso os recursos são sempre descobertos
pelo CKAN, nunca gerados.
"""

from __future__ import annotations

from typing import Dict

from guaraci.ckan.datasets import CkanDataset

__all__ = [
    "CKAN_FEDERAL",
    "MMA_BASE_URL",
    "INSS_BASE_URL",
    "TRANSPORTES_BASE_URL",
    "BNDES_BASE_URL",
    "MAPA_BASE_URL",
]

MMA_BASE_URL = "https://dados.mma.gov.br/api/3/action/"
INSS_BASE_URL = "https://dadosabertos.inss.gov.br/api/3/action/"
TRANSPORTES_BASE_URL = "https://dados.transportes.gov.br/api/3/action/"
BNDES_BASE_URL = "https://dadosabertos.bndes.gov.br/api/3/action/"
MAPA_BASE_URL = "https://dados.agricultura.gov.br/api/3/action/"

_INSS_PLANO = "plano-de-dados-abertos-jun-2023-a-dez-2027"
_INSS_NOTA = (
    "Os nomes de arquivo mudam de mês a mês, por isso os recursos são descobertos pelo CKAN. "
    "Sem 'anos'/'meses' baixa só o mês mais novo publicado."
)

_SPECS = (
    CkanDataset(
        key="mma_unidades_conservacao",
        title="MMA Cadastro Nacional de Unidades de Conservação (CNUC)",
        description=(
            "Cadastro das unidades de conservação federais, estaduais e municipais, com categoria "
            "de manejo, UF, ano de criação, ato legal, órgão gestor e área por bioma. Uma edição "
            "por semestre (2018 em diante); sem 'anos'/'meses' baixa a mais nova. Os municípios "
            "abrangidos vêm em texto livre, como publicados (camada bronze). Edições em xlsx ou "
            "shapefile ficam de fora."
        ),
        base_url=MMA_BASE_URL,
        package_ids=("unidadesdeconservacao",),
        exclude_pattern=r"dicion|pol[ií]gono|shp|sharepoint",
        file_format="csv",
        separator=";",
        default_latest=True,
    ),
    CkanDataset(
        key="mma_especies_ameacadas",
        title="MMA Listas de espécies ameaçadas de extinção",
        description=(
            "Listas nacionais oficiais de espécies da fauna e da flora ameaçadas, edições 2014 a "
            "2021, uma por arquivo (sem coluna de município). Um CSV por recurso; o conjunto "
            "tem leiautes diferentes entre as edições, por isso cada arquivo sai separado."
        ),
        base_url=MMA_BASE_URL,
        package_ids=("especies-ameacadas",),
        exclude_pattern=r"dicion",
        file_format="csv",
        separator=";",
    ),
    CkanDataset(
        key="inss_cat",
        title="INSS Comunicações de Acidente de Trabalho (CAT)",
        description=(
            "Comunicações de Acidente de Trabalho por mês (2023-06 em diante): agente causador, "
            "CID-10, CBO, CNAE, natureza da lesão, parte do corpo, município e UF. Traz "
            "identificador pessoal (data de nascimento do acidentado e CNPJ/CEI do empregador, que "
            "para pessoa física é CPF), publicado assim pelo órgão; o tratamento LGPD fica nas "
            "camadas prata e ouro do Sabiá. O zip traz o mesmo dado em csv, json e xml: só o csv "
            "é exportado. O cabeçalho repete nomes (CBO, CID-10, CNAE, Data Acidente). "
            "A série anterior (2012-2019, outro leiaute) não está nesta chave. "
            + _INSS_NOTA
        ),
        base_url=INSS_BASE_URL,
        package_ids=(f"comunicacoes-de-acidente-de-trabalho-cat-{_INSS_PLANO}",),
        file_format="zip",
        member_pattern=r"\.csv$",
        separator=";",
        default_latest=True,
    ),
    CkanDataset(
        key="inss_beneficios_concedidos",
        title="INSS Benefícios concedidos",
        description=(
            "Benefícios previdenciários e assistenciais concedidos por mês (2023-06 em diante), "
            "com espécie, CID, município de residência, ramo de atividade e datas. Traz "
            "identificador pessoal (data de nascimento do segurado), publicado assim pelo órgão; "
            "o tratamento LGPD fica nas camadas prata e ouro do Sabiá. A planilha tem uma linha "
            "de título antes do cabeçalho, que é descartada, e o cabeçalho repete nomes (APS, "
            "Espécie, CID, Despacho, CNAE). " + _INSS_NOTA
        ),
        base_url=INSS_BASE_URL,
        package_ids=(f"beneficios-concedidos-{_INSS_PLANO}",),
        file_format="xlsx",
        skip_rows=1,
        default_latest=True,
    ),
    CkanDataset(
        key="inss_beneficios_mantidos",
        title="INSS Benefícios mantidos (ativos e suspensos)",
        description=(
            "Estoque de benefícios em manutenção no mês (ativos e suspensos), com espécie, CID-10, "
            "município do titular, UF, datas e renda mensal. É o estoque de dezenas de milhões de "
            "benefícios: um zip de ativos tem centenas de MB, então use 'anos'/'meses' com cuidado. "
            "Traz identificador pessoal (data de nascimento do titular), publicado assim pelo "
            "órgão; o tratamento LGPD fica nas camadas prata e ouro do Sabiá. Os cessados estão "
            "na chave inss_beneficios_cessados. " + _INSS_NOTA
        ),
        base_url=INSS_BASE_URL,
        package_ids=(f"beneficios-mantidos-{_INSS_PLANO}",),
        resource_pattern=r"ativo|suspens",
        file_format="zip",
        separator=";",
        default_latest=True,
    ),
    CkanDataset(
        key="inss_beneficios_cessados",
        title="INSS Benefícios cessados",
        description=(
            "Benefícios cessados até o mês de referência, com espécie, CID-10, motivo da cessação, "
            "município do titular, UF e datas, no mesmo leiaute dos mantidos. O zip mensal passa "
            "de 3 GB: use 'anos'/'meses' com cuidado. Traz identificador pessoal (data de "
            "nascimento do titular), publicado assim pelo órgão; o tratamento LGPD fica nas "
            "camadas prata e ouro do Sabiá. " + _INSS_NOTA
        ),
        base_url=INSS_BASE_URL,
        package_ids=(f"beneficios-mantidos-{_INSS_PLANO}",),
        resource_pattern=r"cessad",
        file_format="zip",
        separator=";",
        default_latest=True,
    ),
    CkanDataset(
        key="inss_beneficios_indeferidos",
        title="INSS Benefícios indeferidos",
        description=(
            "Requerimentos indeferidos por mês (2023-06 em diante), com espécie, motivo do "
            "indeferimento, UF, ramo de atividade e datas. Traz identificador pessoal (data de "
            "nascimento do requerente), publicado assim pelo órgão; o tratamento LGPD fica nas "
            "camadas prata e ouro do Sabiá. A planilha tem uma linha de título antes do "
            "cabeçalho, que é descartada, e o cabeçalho repete nomes (Espécie, APS). " + _INSS_NOTA
        ),
        base_url=INSS_BASE_URL,
        package_ids=(f"beneficios-indeferidos-{_INSS_PLANO}",),
        file_format="xlsx",
        skip_rows=1,
        default_latest=True,
    ),
    CkanDataset(
        key="senatran_renaest",
        title="SENATRAN RENAEST (acidentes de trânsito)",
        description=(
            "Registro Nacional de Acidentes e Estatísticas de Trânsito, publicado pela SENATRAN: "
            "acidentes (data, hora, município, tipo, condições da pista e do tempo, endereço, CEP, "
            "latitude e longitude), vítimas (faixa de idade, gênero, gravidade da lesão), tipo de "
            "veículo e população e frota por município. Cada mês o portal publica um zip acumulado "
            "(cerca de 500 MB, dados de 2018 em diante) com quatro CSV (Acidentes, que passa de 2,7 GB "
            "descompactado, Vitimas, TipoVeiculo e Localidade); sem 'anos'/'meses' baixa só o zip "
            "mais novo e exporta um CSV por membro. Os registros vêm das UFs e a cobertura não é "
            "uniforme: há subnotificação por UF, então comparações entre UFs pedem cautela. "
            "Traz endereço e coordenada do local do acidente, sem nome nem CPF, publicado assim "
            "pelo órgão; o tratamento LGPD fica nas camadas prata e ouro do Sabiá."
        ),
        base_url=TRANSPORTES_BASE_URL,
        package_ids=("renaest",),
        period_pattern=r"(?P<month>\d{2})-(?P<year>\d{4})",
        file_format="zip",
        member_pattern=r"\.csv$",
        separator=";",
        default_latest=True,
    ),
    CkanDataset(
        key="bndes_operacoes_financiamento",
        title="BNDES Operações de financiamento",
        description=(
            "Operações de financiamento contratadas pelo BNDES, em dois arquivos: indiretas "
            "automáticas (cerca de 1,2 GB, via agente financeiro credenciado, com cliente, UF, "
            "município, valor, juros, prazos, produto, setor e subsetor CNAE, porte) e não "
            "automáticas (cerca de 20 MB, com número do contrato e descrição do projeto). Uma "
            "saída por recurso. Nas indiretas automáticas o CPF/CNPJ do cliente vem mascarado "
            "pelo órgão (**.*16.560/0001-**); nas não automáticas o CNPJ vem completo. Traz razão "
            "social ou nome do cliente (cliente) e o CNPJ, publicados assim pelo órgão; o "
            "tratamento LGPD fica nas camadas prata e ouro do Sabiá. Varredura de CPF com dígito "
            "verificador válido em amostra das duas planilhas (cerca de 24 mil e 60 mil linhas): "
            "nenhum achado. Os dicionários em PDF não entram."
        ),
        base_url=BNDES_BASE_URL,
        package_ids=("operacoes-financiamento",),
        file_format="csv",
        separator=";",
    ),
    CkanDataset(
        key="bndes_desembolsos_mensais",
        title="BNDES Desembolsos mensais",
        description=(
            "Desembolsos do BNDES por mês, desde 2002, agregados por forma de apoio, produto, "
            "instrumento, inovação, porte de empresa, região, UF, município, setor e subsetor "
            "CNAE e setor BNDES (cerca de 750 MB), mais a tabela de mapeamento entre os setores "
            "do BNDES e a CNAE. Uma saída por recurso. Sem nome nem CPF (dado agregado). O "
            "dicionário em PDF não entra."
        ),
        base_url=BNDES_BASE_URL,
        package_ids=("desembolsos-mensais",),
        file_format="csv",
        separator=";",
    ),
    CkanDataset(
        key="mapa_agrofit",
        title="MAPA AGROFIT (agrotóxicos e afins registrados)",
        description=(
            "Sistema de Agrotóxicos Fitossanitários do MAPA: produtos formulados (cerca de 390 MB, "
            "um registro por marca, cultura e praga, com ingrediente ativo, titular do registro, "
            "classe, classe toxicológica e ambiental, modo de ação, orgânico e situação) e produtos "
            "técnicos (cerca de 0,7 MB). Uma saída por recurso. O portal exige User-Agent de "
            "navegador e é lento. Traz a razão social do titular do registro (que pode ser pessoa "
            "física), publicada assim pelo órgão; o tratamento LGPD fica nas camadas prata e ouro "
            "do Sabiá. O texto vem com delimitadores soltos em alguns campos (aspas e ponto e "
            "vírgula dentro de marca comercial), como publicado."
        ),
        base_url=MAPA_BASE_URL,
        package_ids=("sistema-de-agrotoxicos-fitossanitarios-agrofit",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
    CkanDataset(
        key="mapa_sif",
        title="MAPA Serviço de Inspeção Federal (SIF)",
        description=(
            "Dados do SIGSIF, o sistema do Serviço de Inspeção Federal: animais abatidos por "
            "categoria, UF e município de procedência (2022 em diante), relatórios de abates "
            "(2002 em diante), condenações de carcaças e partes por espécie, diagnóstico e destino, "
            "doenças por procedência e as listas de estabelecimentos nacionais habilitados, "
            "registrados no SIF e estrangeiros habilitados. Onze CSV, uma saída por recurso, de "
            "0,5 MB a 240 MB. O portal exige User-Agent de navegador e é lento. A lista de "
            "estabelecimentos registrados traz CPF ou CNPJ, razão social, endereço, telefone e "
            "e-mail do estabelecimento (pode ser pessoa física), publicados assim pelo órgão; o "
            "tratamento LGPD fica nas camadas prata e ouro do Sabiá. Varredura de CPF com dígito "
            "verificador válido nas listas de estabelecimentos: 1 a 2 achados por lista (em até "
            "40 mil linhas), isto é, há CPF de pessoa física no lugar do CNPJ. Os dicionários em "
            "PDF não entram."
        ),
        base_url=MAPA_BASE_URL,
        package_ids=("servico-de-inspecao-federal-sif",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
    CkanDataset(
        key="mapa_sipeagro",
        title="MAPA SIPEAGRO (estabelecimentos registrados)",
        description=(
            "Sistema de Informação da Pasta Agropecuária: estabelecimentos registrados no MAPA por "
            "área de atuação (fertilizantes, qualidade vegetal, produto veterinário, vinhos e "
            "bebidas, alimentação animal, material de multiplicação animal, aves de reprodução e "
            "aviação agrícola, em registro e em autorização), com UF, município, número do "
            "registro, situação, atividade e classificação. Nove CSV de dados mais a lista de "
            "agrotóxicos (identificador, nome e situação), uma saída por recurso, de 0,3 MB a "
            "164 MB. O portal exige User-Agent de navegador e é lento. Traz razão social ou nome "
            "do estabelecimento (que pode ser pessoa física), CPF ou CNPJ (mascarado pelo órgão em "
            "várias listas e completo em outras), e na aviação agrícola nome do responsável "
            "técnico, e-mail e telefone, publicados assim pelo órgão; o tratamento LGPD fica nas "
            "camadas prata e ouro do Sabiá. Varredura de CPF com dígito verificador válido: há CPF "
            "completo de pessoa física onde o órgão não mascara (cerca de 270 achados em 67 mil "
            "linhas de produto veterinário, 240 em 28 mil de aviação agrícola, com 143 deles "
            "formatados, e 20 em 16 mil de fertilizantes). Os metadados em PDF não entram."
        ),
        base_url=MAPA_BASE_URL,
        package_ids=("sipeagro",),
        file_format="csv",
        separator=";",
        browser_user_agent=True,
    ),
)

CKAN_FEDERAL: Dict[str, CkanDataset] = {spec.key: spec for spec in _SPECS}
