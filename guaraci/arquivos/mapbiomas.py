"""MapBiomas Brasil, coleção 10: estatísticas por município (fonte secundária aceita pelo dono).

Os dois xlsx estão no bucket público ``mapbiomas-public`` (conferidos ao vivo em 2026-10-23
pela listagem JSON do bucket e pelas abas): ``COVERAGE_10`` (cobertura e uso da terra, 54
colunas, 79.285 linhas) e ``SECONDARY_VEGETATION`` (vegetação secundária, 52 colunas). Cada
planilha traz também abas de pivô, metadados e legenda, que ficam de fora. A leitura do xlsx
de 78 MB, em fluxo, usou cerca de 8 MB de memória Python (``sharedStrings`` incluído).
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_BASE = (
    "https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/collection_10/"
    "lulc/statistics/"
)

# Origem, licença e citação oficial (aba READ_ME das planilhas, agosto de 2025).
_ORIGEM = (
    "Fonte secundária: o MapBiomas classifica imagens Landsat (USGS/NASA) com random forest no "
    "Google Earth Engine e publica as estatísticas por bioma, estado e município. Licença CC "
    "BY 4.0. Citação oficial: \"Projeto MapBiomas - Coleção 10 da Série Anual de Mapas de "
    "Cobertura e Uso da Terra do Brasil, acessado em [data] através do link: "
    "https://brasil.mapbiomas.org/\". O código da coluna class segue a legenda da coleção 10 "
    "(aba LEGEND_CODE da planilha original). Não traz dado pessoal."
)

MAPBIOMAS_COBERTURA_MUNICIPIOS = HttpFile(
    "mapbiomas_cobertura_municipios",
    "MapBiomas - Cobertura e uso da terra por município (coleção 10)",
    "Área em hectares de cada classe de cobertura e uso da terra, por bioma, estado e "
    "município (código IBGE em geocode), um ano por coluna de 1985 a 2024. " + _ORIGEM,
    (HttpResource("cobertura", _BASE + "MAPBIOMAS_BRAZIL-COL.10-BIOME_STATE_MUNICIPALITY.xlsx"),),
    file_format="xlsx",
    sheets=("COVERAGE_10",),
)

MAPBIOMAS_VEGETACAO_SECUNDARIA_MUNICIPIOS = HttpFile(
    "mapbiomas_vegetacao_secundaria_municipios",
    "MapBiomas - Vegetação secundária por município (coleção 10)",
    "Área em hectares de vegetação primária, secundária e de recuperação por classe, bioma, "
    "estado e município (código IBGE em geocode), um ano por coluna de 1986 a 2024. "
    + _ORIGEM,
    (
        HttpResource(
            "vegetacao_secundaria",
            _BASE + "MAPBIOMAS_BRAZIL-COL.10-SECONDARY_VEGETATION_MUNICIPALITY.xlsx",
        ),
    ),
    file_format="xlsx",
    sheets=("SECONDARY_VEGETATION",),
)

SPECS: Tuple[HttpFile, ...] = (
    MAPBIOMAS_COBERTURA_MUNICIPIOS,
    MAPBIOMAS_VEGETACAO_SECUNDARIA_MUNICIPIOS,
)
MODES: Dict[str, str] = {spec.key: "mapbiomas files" for spec in SPECS}
