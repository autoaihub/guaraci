"""Conjuntos CKAN dos portais federais: MMA (cadastros) e INSS (previdência e saúde do trabalhador).

Verificado ao vivo em 2026-10-23 (``package_show`` e primeiros bytes de cada
arquivo; relatórios em ``docs/sondagem_2026-10/``). Os nomes de arquivo do INSS
são inconsistentes de mês a mês e por isso os recursos são sempre descobertos
pelo CKAN, nunca gerados.
"""

from __future__ import annotations

from typing import Dict

from guaraci.ckan.datasets import CkanDataset

__all__ = ["CKAN_FEDERAL", "MMA_BASE_URL", "INSS_BASE_URL"]

MMA_BASE_URL = "https://dados.mma.gov.br/api/3/action/"
INSS_BASE_URL = "https://dadosabertos.inss.gov.br/api/3/action/"

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
)

CKAN_FEDERAL: Dict[str, CkanDataset] = {spec.key: spec for spec in _SPECS}
