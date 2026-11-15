"""Indicadores educacionais do INEP (taxas, distorção, docentes, Inse), um zip por ano e nível.

Origem: ``download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/<ano>/``. O INEP
publica cada indicador em três níveis: escolas, municípios e Brasil, regiões e UFs (o Inse
traz ainda os estados e o Brasil em xlsx soltos, sem zip). Os nomes dos arquivos mudam de
ano em ano (``tx_rend_municipios_2024.zip``, ``TDI_2025_MUNICIPIOS.zip``,
``AFD_2025_MUNICIPIOS.zip``, ``ICG_2024_ESCOLAS.zip``), e por isso o mapa abaixo foi
extraído das páginas de cada indicador em 2026-11-14 (as 476 URLs responderam 200 a um
HEAD e os zips tiveram os membros conferidos). Cada zip traz o xlsx, uma cópia em ods e um md5.

A planilha começa com algumas linhas de título (Ministério da Educação, Inep, nome do
indicador) e blocos de cabeçalho em dois ou três níveis, e só então vem a linha com os
nomes das colunas (``NU_ANO_CENSO``, ``UNIDGEO``, ``1_CAT_FUN``... nas edições recentes;
``ano``, ``TIPOLOCA``, ``tap_FUN`` nas de 2019 e antes). O número de linhas do preâmbulo varia
por indicador, por ano e por nível, então a linha de cabeçalho é achada por conteúdo
(``header_skip``) e as de cima são descartadas. Os valores são percentuais ou médias, como o INEP publica (ponto decimal).

Não há dado pessoal: as linhas são escolas (código e nome da instituição), municípios e UFs.
Ficam fora os zips das edições mais antigas, que trazem xls (até 2011 ou 2014, conforme o
indicador) ou vários xlsx por zip (Brasil, regiões e UFs separados, até 2016 ou 2018), e o
Inse 2015, que sai em outro formato (um zip único). O mapa cobre o que tem um xlsx por zip.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from guaraci.arquivos.http_files import (
    HttpFile,
    HttpFileDataSource,
    HttpResource,
    _is_xlsx,
    _open_member,
    datasource_for_spec,
)
from guaraci.fns.xlsx import iter_xlsx_rows, list_sheets

__all__ = [
    "DATASOURCES",
    "MODES",
    "NIVEIS",
    "SPECS",
    "InepIndicadoresDataSource",
    "header_skip",
]

_BASE = "https://download.inep.gov.br/informacoes_estatisticas/"
MODE = "inep files"
NIVEIS: Dict[str, str] = {
    "ESC": "escolas",
    "MUN": "municípios",
    "UF": "Brasil, regiões e UFs",
    "BR": "Brasil",
}
_TECHNICAL = re.compile(r"^[A-Z]{2,3}_[A-Z0-9_]+$|^\d_[A-Z0-9_]+$")
_YEAR = re.compile(r"(?:19|20)\d{2}")
_SCAN_ROWS = 40

# chave: (título, o que traz, ((ano, nível, caminho relativo a _BASE), ...))
_INDICADORES: Dict[str, Tuple[str, str, Tuple[Tuple[str, str, str], ...]]] = {
    "inep_taxas_rendimento": (
        "INEP Taxas de Rendimento Escolar",
        "taxas de aprovação, reprovação e abandono",
        (
            ("2012", "ESC", "indicadores_educacionais/2012/taxas_rendimento/tx_rendimento_escolas_2012.zip"),
            ("2012", "MUN", "indicadores_educacionais/2012/taxas_rendimento/tx_rendimento_municipios_2012.zip"),
            ("2013", "ESC", "indicadores_educacionais/2013/taxa_rendimento/tx_rendimento_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/taxa_rendimento/tx_rendimento_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/taxa_rendimento/tx_rendimento_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/taxa_rendimento/tx_rendimento_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/taxa_rendimento/tx_rendimento_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/taxa_rendimento/tx_rendimento_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/TAXA_REND_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/TAXA_REND_2016_MUNICIPIOS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/TAXA_REND_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/TAXA_REND_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/TX_REND_BRASIL_REGIOES_UFS_2018.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/TX_REND_ESCOLAS_2018.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/TX_REND_MUNICIPIOS_2018.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/tx_rend_brasil_regioes_ufs_2019.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/tx_rend_escolas_2019.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/tx_rend_municipios_2019.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/tx_rend_brasil_regioes_ufs_2020.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/tx_rend_escolas_2020.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/tx_rend_municipios_2020.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/tx_rend_brasil_regioes_ufs_2021.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/tx_rend_escolas_2021.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/tx_rend_municipios_2021.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/tx_rend_brasil_regioes_ufs_2022.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/tx_rend_escolas_2022.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/tx_rend_municipios_2022.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/tx_rend_brasil_regioes_ufs_2023.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/tx_rend_escolas_2023.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/tx_rend_municipios_2023.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/tx_rend_brasil_regioes_ufs_2024.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/tx_rend_escolas_2024.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/tx_rend_municipios_2024.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/tx_rend_brasil_regioes_ufs_2025.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/tx_rend_escolas_2025.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/tx_rend_municipios_2025.zip"),
        ),
    ),
    "inep_distorcao_idade_serie": (
        "INEP Taxas de Distorção Idade-Série",
        "percentual de alunos com dois anos ou mais de atraso escolar",
        (
            ("2012", "ESC", "indicadores_educacionais/2012/distorcao_idade_serie/tdi_escolas_2012.zip"),
            ("2012", "MUN", "indicadores_educacionais/2012/distorcao_idade_serie/tdi_municipios_2012.zip"),
            ("2013", "ESC", "indicadores_educacionais/2013/distorcao_idade_serie/tdi_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/distorcao_idade_serie/tdi_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/distorcao_idade_serie/tdi_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/distorcao_idade_serie/tdi_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/distorcao_idade_serie/tdi_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/distorcao_idade_serie/tdi_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/TDI_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/TDI_2016_MUNICIPIOS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/TDI_2017_BRASIL_REGIOES_UFS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/TDI_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/TDI_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/TDI_2018_BRASIL_REGIOES_UFS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/TDI_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/TDI_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/TDI_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/TDI_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/TDI_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/TDI_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/TDI_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/TDI_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/TDI_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/TDI_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/TDI_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/TDI_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/TDI_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/TDI_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/TDI_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/TDI_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/TDI_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/TDI_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/TDI_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/TDI_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/TDI_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/TDI_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/TDI_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_adequacao_formacao_docente": (
        "INEP Adequação da Formação Docente",
        "percentual de docentes por grupo de adequação da formação à disciplina que lecionam",
        (
            ("2013", "ESC", "indicadores_educacionais/2013/adequacao_formacao_docente/adequacao_formacao_docente_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/adequacao_formacao_docente/adequacao_formacao_docente_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/adequacao_formacao_docente/adequacao_formacao_docente_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/adequacao_formacao_docente/adequacao_formacao_docente_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/adequacao_formacao_docente/adequacao_formacao_docente_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/adequacao_formacao_docente/adequacao_formacao_docente_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/AFD_2016_ESCOLAS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/AFD_2017_BRASIL_REGIOES_UF.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/AFD_2017_ESCOLAS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/AFD_2018_BRASIL_REGIOES_UF.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/AFD_2018_ESCOLAS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/AFD_2019_BRASIL_REGIOES_UF.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/AFD_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/AFD_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/AFD_2020_BRASIL_REGIOES_UF.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/AFD_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/AFD_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/AFD_2021_BRASIL_REGIOES_UF.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/AFD_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/AFD_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/AFD_2022_BRASIL_REGIOES_UF.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/AFD_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/AFD_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/AFD_2023_BRASIL_REGIOES_UF.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/AFD_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/AFD_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/AFD_2024_BRASIL_REGIOES_UF.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/AFD_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/AFD_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/AFD_2025_BRASIL_REGIOES_UF.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/AFD_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/AFD_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_inse": (
        "INEP Indicador de Nível Socioeconômico (Inse)",
        "nível socioeconômico dos alunos do Saeb, com média e distribuição por nível",
        (
            ("2019", "ESC", "indicadores_educacionais/2019/nivel_socioeconomico/INSE_2019_ESCOLAS.xlsx"),
            ("2019", "UF", "indicadores_educacionais/2019/nivel_socioeconomico/INSE_2019_ESTADOS.xlsx"),
            ("2019", "MUN", "indicadores_educacionais/2019/nivel_socioeconomico/INSE_2019_MUNICIPIOS.xlsx"),
            ("2021", "BR", "indicadores_educacionais/2021/nivel_socioeconomico/INSE_2021__brasil.xlsx"),
            ("2021", "ESC", "indicadores_educacionais/2021/nivel_socioeconomico/INSE_2021_escolas.xlsx"),
            ("2021", "UF", "indicadores_educacionais/2021/nivel_socioeconomico/INSE_2021_estados.xlsx"),
            ("2021", "MUN", "indicadores_educacionais/2021/nivel_socioeconomico/INSE_2021_municipios.xlsx"),
            ("2023", "BR", "indicadores_educacionais/2023/nivel_socioeconomico/INSE_2023_brasil.xlsx"),
            ("2023", "ESC", "indicadores_educacionais/2023/nivel_socioeconomico/INSE_2023_escolas.xlsx"),
            ("2023", "UF", "indicadores_educacionais/2023/nivel_socioeconomico/INSE_2023_estados.xlsx"),
            ("2023", "MUN", "indicadores_educacionais/2023/nivel_socioeconomico/INSE_2023_municipios.xlsx"),
        ),
    ),
    "inep_esforco_docente": (
        "INEP Indicador de Esforço Docente",
        "distribuição dos docentes por nível de esforço (alunos, escolas, turnos e etapas)",
        (
            ("2013", "ESC", "indicadores_educacionais/2013/esforco_docente/esforco_docente_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/esforco_docente/esforco_docente_municipios_2013.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/esforco_docente/esforco_docente_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/esforco_docente/esforco_docente_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/IED_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/IED_2016_MUNICIPIOS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/IED_2017_BRASIL_REGIOES_UFS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/IED_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/IED_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/IED_2018_BRASIL_REGIOES_UFS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/IED_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/IED_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/IED_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/IED_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/IED_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/IED_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/IED_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/IED_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/IED_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/IED_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/IED_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/IED_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/IED_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/IED_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/IED_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/IED_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/IED_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/IED_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/IED_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/IED_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/IED_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/IED_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/IED_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_regularidade_docente": (
        "INEP Regularidade do Corpo Docente",
        "permanência dos docentes na mesma escola ao longo de cinco anos",
        (
            ("2013", "ESC", "indicadores_educacionais/2013/regularidade_corpo_docente/regularidade_corpo_docente_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/regularidade_corpo_docente/regularidade_corpo_docente_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/regularidade_corpo_docente/regularidade_corpo_docente_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/regularidade_corpo_docente/regularidade_corpo_docente_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/regularidade_corpo_docente/regularidade_corpo_docente_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/regularidade_corpo_docente/regularidade_corpo_docente_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/IRD_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/IRD_2016_MUNICIPIOS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/IRD_2017_BRASIL_REGIOES_UFS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/IRD_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/IRD_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/IRD_2018_BRASIL_REGIOES_UFS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/IRD_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/IRD_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/IRD_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/IRD_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/IRD_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/IRD_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/IRD_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/IRD_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/IRD_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/IRD_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/IRD_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/IRD_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/IRD_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/IRD_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/IRD_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/IRD_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/IRD_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/IRD_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/IRD_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/IRD_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/IRD_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/IRD_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/IRD_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_complexidade_gestao": (
        "INEP Complexidade de Gestão da Escola",
        "níveis de complexidade de gestão das escolas",
        (
            ("2013", "ESC", "indicadores_educacionais/2013/complexidade_gestao_escola/complexidade_gestao_escola_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/complexidade_gestao_escola/complexidade_gestao_escola_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/complexidade_gestao_escola/complexidade_gestao_escola_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/complexidade_gestao_escola/complexidade_gestao_escola_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/complexidade_gestao_escola/complexidade_gestao_escola_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/complexidade_gestao_escola/complexidade_gestao_escola_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/ICG_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/ICG_2016_MUNICIPIOS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/ICG_2017_BRASIL_REGIOES_UFS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/ICG_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/ICG_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/ICG_2018_BRASIL_REGIOES_UFS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/ICG_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/ICG_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/ICG_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/ICG_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/ICG_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/ICG_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/ICG_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/ICG_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/ICG_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/ICG_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/ICG_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/ICG_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/ICG_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/ICG_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/ICG_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/ICG_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/ICG_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/ICG_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/ICG_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/ICG_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/ICG_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/ICG_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/ICG_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_alunos_por_turma": (
        "INEP Média de Alunos por Turma",
        "média de alunos por turma por etapa",
        (
            ("2012", "ESC", "indicadores_educacionais/2012/alunos_turma/media_alunos_turma_escolas_2012.zip"),
            ("2012", "MUN", "indicadores_educacionais/2012/alunos_turma/media_alunos_turma_municipios_2012.zip"),
            ("2013", "ESC", "indicadores_educacionais/2013/alunos_turma/media_alunos_turma_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/alunos_turma/media_alunos_turma_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/alunos_turma/media_alunos_turma_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/alunos_turma/media_alunos_turma_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/alunos_turma/media_alunos_turma_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/alunos_turma/media_alunos_turma_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/ATU_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/ATU_2016_MUNICIPIOS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/ATU_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/ATU_2017_MUNICIPIOS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/ATU_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/ATU_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/ATU_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/ATU_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/ATU_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/ATU_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/ATU_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/ATU_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/ATU_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/ATU_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/ATU_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/ATU_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/ATU_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/ATU_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/ATU_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/ATU_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/ATU_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/ATU_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/ATU_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/ATU_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/ATU_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/ATU_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/ATU_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_horas_aula": (
        "INEP Média de Horas-Aula Diária",
        "média de horas-aula diárias por etapa",
        (
            ("2012", "ESC", "indicadores_educacionais/2012/horas_aula_diaria/horas_aula_escolas_2012.zip"),
            ("2012", "MUN", "indicadores_educacionais/2012/horas_aula_diaria/horas_aula_municipios_2012.zip"),
            ("2013", "ESC", "indicadores_educacionais/2013/horas_aula_diaria/horas_aula_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/horas_aula_diaria/horas_aula_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/horas_aula_diaria/horas_aula_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/horas_aula_diaria/horas_aula_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/horas_aula_diaria/horas_aula_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/horas_aula_diaria/horas_aula_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/HAD_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/HAD_2016_MUNICIPIOS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/HAD_2017_BRASIL_REGIOES_UFS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/HAD_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/HAD_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/HAD_2018_BRASIL_REGIOES_UFS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/HAD_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/HAD_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/HAD_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/HAD_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/HAD_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/HAD_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/HAD_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/HAD_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/HAD_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/HAD_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/HAD_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/HAD_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/HAD_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/HAD_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/HAD_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/HAD_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/HAD_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/HAD_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/HAD_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/HAD_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/HAD_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/HAD_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/HAD_2025_MUNICIPIOS.zip"),
        ),
    ),
    "inep_docentes_curso_superior": (
        "INEP Percentual de Docentes com Curso Superior",
        "percentual de docentes com ensino superior por etapa",
        (
            ("2011", "ESC", "indicadores_educacionais/2011/proporcao_docentes_formacao_superior/dsu_escolas_2011.zip"),
            ("2011", "MUN", "indicadores_educacionais/2011/proporcao_docentes_formacao_superior/dsu_municipios_2011.zip"),
            ("2012", "ESC", "indicadores_educacionais/2012/proporcao_docentes_formacao_superior/dsu_escolas_2012.zip"),
            ("2012", "MUN", "indicadores_educacionais/2012/proporcao_docentes_formacao_superior/dsu_municipios_2012.zip"),
            ("2013", "ESC", "indicadores_educacionais/2013/proporcao_docentes_formacao_superior/dsu_escolas_2013.zip"),
            ("2013", "MUN", "indicadores_educacionais/2013/proporcao_docentes_formacao_superior/dsu_municipios_2013.zip"),
            ("2014", "ESC", "indicadores_educacionais/2014/proporcao_docentes_formacao_superior/dsu_escolas_2014.zip"),
            ("2014", "MUN", "indicadores_educacionais/2014/proporcao_docentes_formacao_superior/dsu_municipios_2014.zip"),
            ("2015", "ESC", "indicadores_educacionais/2015/proporcao_docentes_formacao_superior/dsu_escolas_2015.zip"),
            ("2015", "MUN", "indicadores_educacionais/2015/proporcao_docentes_formacao_superior/dsu_municipios_2015.zip"),
            ("2016", "ESC", "indicadores_educacionais/2016/DSU_2016_ESCOLAS.zip"),
            ("2016", "MUN", "indicadores_educacionais/2016/DSU_2016_MUNICIPIOS.zip"),
            ("2017", "UF", "indicadores_educacionais/2017/DSU_2017_BRASIL_REGIOES_UFS.zip"),
            ("2017", "ESC", "indicadores_educacionais/2017/DSU_2017_ESCOLAS.zip"),
            ("2017", "MUN", "indicadores_educacionais/2017/DSU_2017_MUNICIPIOS.zip"),
            ("2018", "UF", "indicadores_educacionais/2018/DSU_2018_BRASIL_REGIOES_UFS.zip"),
            ("2018", "ESC", "indicadores_educacionais/2018/DSU_2018_ESCOLAS.zip"),
            ("2018", "MUN", "indicadores_educacionais/2018/DSU_2018_MUNICIPIOS.zip"),
            ("2019", "UF", "indicadores_educacionais/2019/DSU_2019_BRASIL_REGIOES_UFS.zip"),
            ("2019", "ESC", "indicadores_educacionais/2019/DSU_2019_ESCOLAS.zip"),
            ("2019", "MUN", "indicadores_educacionais/2019/DSU_2019_MUNICIPIOS.zip"),
            ("2020", "UF", "indicadores_educacionais/2020/DSU_2020_BRASIL_REGIOES_UFS.zip"),
            ("2020", "ESC", "indicadores_educacionais/2020/DSU_2020_ESCOLAS.zip"),
            ("2020", "MUN", "indicadores_educacionais/2020/DSU_2020_MUNICIPIOS.zip"),
            ("2021", "UF", "indicadores_educacionais/2021/DSU_2021_BRASIL_REGIOES_UFS.zip"),
            ("2021", "ESC", "indicadores_educacionais/2021/DSU_2021_ESCOLAS.zip"),
            ("2021", "MUN", "indicadores_educacionais/2021/DSU_2021_MUNICIPIOS.zip"),
            ("2022", "UF", "indicadores_educacionais/2022/DSU_2022_BRASIL_REGIOES_UFS.zip"),
            ("2022", "ESC", "indicadores_educacionais/2022/DSU_2022_ESCOLAS.zip"),
            ("2022", "MUN", "indicadores_educacionais/2022/DSU_2022_MUNICIPIOS.zip"),
            ("2023", "UF", "indicadores_educacionais/2023/DSU_2023_BRASIL_REGIOES_UFS.zip"),
            ("2023", "ESC", "indicadores_educacionais/2023/DSU_2023_ESCOLAS.zip"),
            ("2023", "MUN", "indicadores_educacionais/2023/DSU_2023_MUNICIPIOS.zip"),
            ("2024", "UF", "indicadores_educacionais/2024/DSU_2024_BRASIL_REGIOES_UFS.zip"),
            ("2024", "ESC", "indicadores_educacionais/2024/DSU_2024_ESCOLAS.zip"),
            ("2024", "MUN", "indicadores_educacionais/2024/DSU_2024_MUNICIPIOS.zip"),
            ("2025", "UF", "indicadores_educacionais/2025/DSU_2025_BRASIL_REGIOES_UFS.zip"),
            ("2025", "ESC", "indicadores_educacionais/2025/DSU_2025_ESCOLAS.zip"),
            ("2025", "MUN", "indicadores_educacionais/2025/DSU_2025_MUNICIPIOS.zip"),
        ),
    ),
}


def header_skip(xlsx: Path, sheet: str) -> int:
    """Linhas acima do cabeçalho: a linha de nomes técnicos ou, na falta dela, a anterior aos dados.

    Nas edições recentes a linha de cabeçalho tem nomes técnicos em maiúsculas
    (``NU_ANO_CENSO``). Nas anteriores (2019 e antes) os nomes são curtos e em minúsculas
    (``ano``, ``tap_FUN``); aí vale a linha logo acima da primeira cujo 1º campo é um ano.
    """
    rows = [row for _, row in zip(range(_SCAN_ROWS), iter_xlsx_rows(xlsx, sheet))]
    for index, row in enumerate(rows):
        first = row[0].strip() if row else ""
        if _TECHNICAL.match(first):
            return index
    for index, row in enumerate(rows):
        if index > 0 and row and _YEAR.fullmatch(row[0].strip()):
            return index - 1
    raise ValueError(
        f"Cabeçalho não encontrado nas {_SCAN_ROWS} primeiras linhas da aba '{sheet}'."
    )


class InepIndicadoresDataSource(HttpFileDataSource):
    """Como o leitor de xlsx comum, mas descobre sozinho a linha de cabeçalho de cada arquivo."""

    def _export_xlsx(self, raw_path, base_dir, fmt, base, resource=None):
        wrapper = base_dir / f"{base}.hdr.tmp.xlsx"
        try:
            source = raw_path
            if not _is_xlsx(raw_path):
                with _open_member(raw_path, self.spec) as src, open(wrapper, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                source = wrapper
            skip = header_skip(source, list_sheets(source)[0])
        finally:
            wrapper.unlink(missing_ok=True)
        resource = dataclasses.replace(resource, skip_rows=skip) if resource else HttpResource(
            base, "", "", skip_rows=skip
        )
        return super()._export_xlsx(raw_path, base_dir, fmt, base, resource)


def _spec(key: str) -> HttpFile:
    title, traz, files = _INDICADORES[key]
    anos = sorted({y for y, _, _ in files})
    niveis = sorted({n for _, n, _ in files}, key=list(NIVEIS).index)
    resources = tuple(
        HttpResource(f"{y}_{n}", _BASE + path, f"{title} {y} ({NIVEIS[n]})")
        for y, n, path in sorted(files, key=lambda f: (f[0], list(NIVEIS).index(f[1])))
    )
    extra = (
        " O Inse também traz a aba de dicionário, exportada como arquivo irmão."
        if key == "inep_inse"
        else ""
    )
    return HttpFile(
        key,
        title,
        f"{title}: {traz}, por escola, município e Brasil, regiões e UFs, de "
        f"{anos[0]} a {anos[-1]}. Cada ano e nível vira um arquivo (código AAAA_ESC, AAAA_MUN, "
        "AAAA_UF); as colunas seguem os nomes técnicos da planilha e os valores, como o INEP "
        "publica. Não traz dado pessoal." + extra,
        resources,
        file_format="xlsx",
        member_pattern=r"\.xlsx$",
        selector="periodo",
        period_required=True,
        year_window=True,
        subperiod_label="Níveis (" + ", ".join(f"{n} = {NIVEIS[n]}" for n in niveis)
        + "). Omita para todos.",
        anos_label=(
            f"Anos a baixar (obrigatório, {anos[0]} a {anos[-1]}). O arquivo de escolas "
            "de um ano pode passar de 60 MB; peça poucos anos por vez."
        ),
    )


SPECS: Tuple[HttpFile, ...] = tuple(_spec(key) for key in _INDICADORES)
MODES: Dict[str, str] = {spec.key: MODE for spec in SPECS}
DATASOURCES: Dict[str, type] = {}


def _datasource(spec: HttpFile) -> type:
    base = datasource_for_spec(spec)
    return type(base.__name__, (InepIndicadoresDataSource, base), {"DATASET": spec.key})


DATASOURCES.update({spec.key: _datasource(spec) for spec in SPECS})
