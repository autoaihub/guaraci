"""Segurança pública e violência: Disque 100, SISDEPEN e ISP-RJ, arquivos CSV por HTTP.

Verificado ao vivo em 2026-10-23 (HEAD ou Range e primeiros 3 a 20 MB de cada família).

- ``mdhc_disque100``: a página de cada semestre devolve o CSV direto no GET (sem
  ``Content-Length``); o HEAD dá 403, por isso ``probe="range"``. Os arquivos têm de 100 MB
  (1S2020) a 1,9 GB (1S2026), então ``anos`` é obrigatório. A lista de páginas foi raspada
  do índice ``.../dados-abertos/disque100`` e fica congelada aqui, pois os slugs mudam de
  grafia (``segundo-semestre-de-2023``, ``primeiro-semestre-2024``,
  ``disque100-segundo-semestre-2025``). O leiaute passa de 34 colunas (1S2020) para 62
  (2S2020 em diante; nomes com espaço até 1S2022, com sublinhado depois). Entre 2011 e 2019 o índice traz uma página por ano (``disque-100-AAAA``)
  e balanços temáticos, que ficam fora.
- ``senappen_sisdepen``: um CSV por ciclo semestral do SISDEPEN/Infopen, lista raspada de
  ``.../sisdepen/bases-de-dados``. Entre 1.117 e 1.737 colunas (contadas no cabeçalho
  com aspas) e rótulos que mudam entre ciclos: cada ciclo sai como arquivo
  próprio. O CSV é ``;`` em UTF-8.
- ``isp_rj_*``: duas bases mensais do Instituto de Segurança Pública do RJ, URL fixa,
  ``;``, cp1252, 2003 até hoje.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_DISQUE = "https://www.gov.br/mdh/pt-br/acesso-a-informacao/dados-abertos/disque100/"
# (código, slug da página do semestre). 2026_T3 é o terceiro trimestre de 2026, publicado
# à parte do primeiro semestre.
_DISQUE_PAGINAS: Tuple[Tuple[str, str], ...] = (
    ("2020_S1", "primeiro-semestre-de-2020"),
    ("2020_S2", "segundo-semestre-de-2020"),
    ("2021_S1", "primeiro-semestre-de-2021"),
    ("2021_S2", "segundo-semestre-de-2021"),
    ("2022_S1", "primeiro-semestre-de-2022"),
    ("2022_S2", "segundo-semestre-de-2022"),
    ("2023_S1", "primeiro-semestre-de-2023"),
    ("2023_S2", "segundo-semestre-de-2023"),
    ("2024_S1", "primeiro-semestre-2024"),
    ("2024_S2", "disque100-segundo-semestre-2024"),
    ("2025_S1", "disque100-primeiro-semestre-2025"),
    ("2025_S2", "disque100-segundo-semestre-2025"),
    ("2026_S1", "disque100-primeiro-semestre-2026"),
    ("2026_T3", "disque100-terceiro-trimestre-2026"),
)

MDHC_DISQUE100 = HttpFile(
    "mdhc_disque100",
    "MDHC Disque 100 - Violações de direitos humanos",
    "Denúncias do Disque 100 (Ouvidoria Nacional de Direitos Humanos, MDHC), um CSV por "
    "semestre de 2020 em diante (mais o 3º trimestre de 2026): violência contra criança e "
    "adolescente, pessoa idosa, pessoa com deficiência, população LGBT, pessoa em situação "
    "de rua e outros grupos, com cenário e tipo da violação, município e UF, perfil da "
    "vítima e do suspeito. O leiaute muda de 34 colunas (1S2020) para 62 (2S2020 em "
    "diante) e cada semestre sai como arquivo próprio, com as colunas como publicadas. "
    "Não traz nome nem documento; a coluna hash é um identificador anonimizado do par "
    "vítima e suspeito. Os arquivos vão de 100 MB a 1,9 GB, por isso o recorte por anos.",
    tuple(
        HttpResource(code, _DISQUE + slug, f"Disque 100 {code}")
        for code, slug in _DISQUE_PAGINAS
    ),
    separator=";",
    selector="periodo",
    probe="range",
    period_required=True,
    year_window=True,
)

_SISDEPEN = (
    "https://www.gov.br/senappen/pt-br/servicos/sisdepen/bases-de-dados/"
)
# (código, caminho relativo do CSV). Os nomes são irregulares (``-retificado``, o 14º ciclo
# no CSV e no XLSX com sufixos diferentes), por isso a lista é congelada, não gerada.
_SISDEPEN_CICLOS: Tuple[Tuple[str, str], ...] = (
    ("2014", "2014-e-2015/base-de-dados-infopen-2014.csv"),
    ("2015", "2014-e-2015/base-de-dados-infopen-2015.csv"),
    ("2016_S1", "2016/2016_basefinal_depen_publicacao_revisado_csv.csv"),
    ("2016_S2", "2016/1o-ciclo-base-de-dados-2016-2-semestre.csv"),
    ("2017_S1", "2017/2o-ciclo-base-de-dados-2017-1-semestre.csv"),
    ("2017_S2", "2017/3o-ciclo-base-de-dados-2017-2-semestre.csv"),
    ("2018_S1", "2018/4o-ciclo-base-de-dados-2018-1-semestre.csv"),
    ("2018_S2", "2018/5o-ciclo-base-de-dados-2018-2-semestre.csv"),
    ("2019_S1", "2019/6o-ciclo-base-de-dados-2019-1-semestre.csv"),
    ("2019_S2", "2019/7o-ciclo-base-de-dados-2019-2-semestre.csv"),
    ("2020_S1", "2020/8o-ciclo-base-de-dados-2020-1-semestre.csv"),
    ("2020_S2", "2020/9o-ciclo-base-de-dados-2020-2-semestre.csv"),
    ("2021_S1", "2021/10o-ciclo-base-de-dados-2021-1-semestre.csv"),
    ("2021_S2", "2021/11o-ciclo-base-de-dados-2021-2-semestre.csv"),
    ("2022_S1", "2022/12o-ciclo-base-de-dados-2022-1-semestre.csv"),
    ("2022_S2", "2022/13o-ciclo-base-de-dados-2022-2-semestre.csv"),
    ("2023_S1", "2023/14o-ciclo-base-de-dados-2023-1-semestre.csv"),
    ("2023_S2", "2023/15o-ciclo-base-de-dados-2023-2-semestre.csv"),
    ("2024_S1", "2024/16o-ciclo-base-de-dados-2024-1-semestre-retificado.csv"),
    ("2024_S2", "2024/17o-ciclo-base-de-dados-2024-2-semestre.csv"),
    ("2025_S1", "2025/18o-ciclo-base-de-dados-2025-1-semestre-retificado.csv"),
    ("2025_S2", "2025/19o-ciclo-base-de-dados-2025-2-semestre.csv"),
)

SENAPPEN_SISDEPEN = HttpFile(
    "senappen_sisdepen",
    "SENAPPEN SISDEPEN - Sistema prisional (Infopen)",
    "Base de dados do SISDEPEN (antigo Infopen, SENAPPEN): um registro por unidade prisional "
    "e ciclo, com capacidade, população privada de liberdade por regime, sexo e perfil, "
    "estrutura, saúde, educação, trabalho e mortes. Um CSV por ciclo, de 2014 a 2025 (2014 e "
    "2015 anuais; depois semestrais, o 2016_S1 sendo a base final de junho de 2016). O "
    "leiaute muda entre ciclos (1.117 a 1.737 colunas, rótulos reescritos) e cada ciclo sai "
    "como arquivo próprio, com os nomes de coluna como publicados. Traz identificador "
    "pessoal (Nome do Estabelecimento, Endereço e telefone da unidade e, nas bases de 2014 "
    "a 2016, o nome do responsável pelo preenchimento), publicado assim pelo órgão; o "
    "tratamento LGPD fica nas camadas prata e ouro do Sabiá. Sem identificação de pessoas "
    "privadas de liberdade.",
    tuple(
        HttpResource(code, f"{_SISDEPEN}{path}/@@download/file", f"SISDEPEN {code}")
        for code, path in _SISDEPEN_CICLOS
    ),
    separator=";",
    selector="periodo",
    period_required=False,
    year_window=True,
)

_ISP = "https://www.ispdados.rj.gov.br/Arquivos/"

ISP_RJ_DELEGACIAS_MENSAL = HttpFile(
    "isp_rj_delegacias_mensal",
    "ISP-RJ - Evolução mensal por delegacia (CISP)",
    "Indicadores mensais de segurança pública do estado do Rio de Janeiro por circunscrição "
    "de delegacia (CISP), de janeiro de 2003 em diante: homicídio doloso, letalidade "
    "violenta, roubos, furtos, estupro, apreensão de drogas, entre outros (65 colunas), com "
    "AISP, RISP, município e código do município. Arquivo único atualizado todo mês; "
    "cada download é um instantâneo. Não traz dado pessoal.",
    (HttpResource("cisp_mensal", _ISP + "BaseDPEvolucaoMensalCisp.csv"),),
    separator=";",
)

ISP_RJ_MUNICIPIOS_MENSAL = HttpFile(
    "isp_rj_municipios_mensal",
    "ISP-RJ - Evolução mensal por município",
    "Indicadores mensais de segurança pública do estado do Rio de Janeiro por município, "
    "de janeiro de 2003 em diante (62 colunas, código IBGE do município em fmun_cod): "
    "homicídio doloso, letalidade violenta, roubos, furtos, estupro, apreensão de drogas e "
    "policiais mortos em serviço, entre outros. Arquivo único atualizado todo mês; cada "
    "download é um instantâneo. Não traz dado pessoal.",
    (HttpResource("municipio_mensal", _ISP + "BaseMunicipioMensal.csv"),),
    separator=";",
)

SPECS: Tuple[HttpFile, ...] = (
    MDHC_DISQUE100,
    SENAPPEN_SISDEPEN,
    ISP_RJ_DELEGACIAS_MENSAL,
    ISP_RJ_MUNICIPIOS_MENSAL,
)
MODES: Dict[str, str] = {
    "mdhc_disque100": "mdhc files",
    "senappen_sisdepen": "senappen files",
    "isp_rj_delegacias_mensal": "isp rj files",
    "isp_rj_municipios_mensal": "isp rj files",
}
