"""MapBiomas Brasil, coleção 11: estatísticas por município (fonte secundária aceita pelo dono).

A coleção 10 saiu do bucket público ``mapbiomas-public`` (HTTP 403 desde 2026-11-03). As
planilhas da coleção 11, publicadas em agosto e outubro de 2026, estão em
``brasil.mapbiomas.org/downloads/estatisticas`` e foram conferidas ao vivo em 2026-11-14:

- cobertura e uso da terra: zip de 78 MB no Google Drive com um xlsx (aba ``COVERAGE_11``, 55
  colunas, 77.406 linhas, ``y1985`` a ``y2025``). O endereço ``drive.usercontent.google.com``
  com ``confirm=t`` responde direto, sem a página de aviso de vírus e sem login;
- vegetação secundária: xlsx de 58 MB no site do MapBiomas (aba
  ``ANNUAL_SECONDARY_VEGETATION``, 57 colunas, 59.893 linhas, ``y1985`` a ``y2025``). O
  leiaute mudou em relação à coleção 10: agora traz ``TRANSITION_CLASS_ID`` e
  ``TRANSITION_CLASS_NAME`` e as colunas ``VERSION`` e ``COLLECTION``.

Cada planilha traz também abas de pivô, metadados e legenda, que ficam de fora. O endereço da
vegetação secundária leva o mês de publicação (``2026/10``) e muda se o MapBiomas reenviar o
arquivo.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

# Zip do Drive (id 1otOqymHuixvkRGVl65zTTNyfaHo46Gqk) que embrulha o xlsx da cobertura.
_COBERTURA_URL = (
    "https://drive.usercontent.google.com/download?"
    "id=1otOqymHuixvkRGVl65zTTNyfaHo46Gqk&export=download&confirm=t"
)
_COBERTURA_MEMBRO = "MAPBIOMAS_BRAZIL-COL.11-BIOME_STATE_MUNICIPALITY.xlsx"
_VEGETACAO_URL = (
    "https://brasil.mapbiomas.org/wp-content/uploads/sites/3/2026/10/"
    "MAPBIOMAS-BRAZIL-SECONDARY-VEGETATION-MUNICIPALITY-COLLECTION_11.xlsx"
)

# Origem, licença e citação oficial (aba READ_ME das planilhas, agosto de 2026).
_ORIGEM = (
    "Fonte secundária: o MapBiomas classifica imagens Landsat (USGS/NASA) com random forest no "
    "Google Earth Engine e publica as estatísticas por bioma, estado e município. Licença CC "
    "BY 4.0. Citação oficial: \"Projeto MapBiomas - Coleção 11 da Série Anual de Mapas de "
    "Cobertura e Uso da Terra do Brasil, acessado em [data] através do link: "
    "https://brasil.mapbiomas.org/\". O código da coluna class segue a legenda da coleção 11 "
    "(aba LEGEND_CODE da planilha original). Não traz dado pessoal."
)

MAPBIOMAS_COBERTURA_MUNICIPIOS = HttpFile(
    "mapbiomas_cobertura_municipios",
    "MapBiomas - Cobertura e uso da terra por município (coleção 11)",
    "Área em hectares de cada classe de cobertura e uso da terra, por bioma, estado e "
    "município (código IBGE em geocode), um ano por coluna de 1985 a 2025. " + _ORIGEM,
    (HttpResource("cobertura", _COBERTURA_URL),),
    member=_COBERTURA_MEMBRO,
    file_format="xlsx",
    sheets=("COVERAGE_11",),
)

MAPBIOMAS_VEGETACAO_SECUNDARIA_MUNICIPIOS = HttpFile(
    "mapbiomas_vegetacao_secundaria_municipios",
    "MapBiomas - Vegetação secundária por município (coleção 11)",
    "Área em hectares de vegetação primária, secundária e de recuperação por classe e por "
    "transição, bioma, estado e município (código IBGE em geocode), um ano por coluna de 1985 "
    "a 2025. " + _ORIGEM,
    (HttpResource("vegetacao_secundaria", _VEGETACAO_URL),),
    file_format="xlsx",
    sheets=("ANNUAL_SECONDARY_VEGETATION",),
)

SPECS: Tuple[HttpFile, ...] = (
    MAPBIOMAS_COBERTURA_MUNICIPIOS,
    MAPBIOMAS_VEGETACAO_SECUNDARIA_MUNICIPIOS,
)
MODES: Dict[str, str] = {spec.key: "mapbiomas files" for spec in SPECS}
