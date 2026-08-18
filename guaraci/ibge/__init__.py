"""IBGE data sources for Guaraci (SIDRA aggregates API, keyless JSON).

Exposed sources:
- ``ibge_populacao`` — population estimates by locality x year (table 6579)
- ``ibge_pib_municipios`` — municipal GDP / PIB (table 5938)
- ``ibge_populacao_idade_sexo`` — census population by sex and age (table 9514)
- ``ibge_nascidos_vivos_rc`` — live births, registro civil (table 2680)
- ``ibge_obitos_rc`` — deaths, registro civil (table 2681)
- ``ibge_area_territorial`` — area/density/population, census 2022 (table 4714)

These are the denominator / socioeconomic layers for health-rate analysis.
"""

from guaraci.ibge.client import IbgeClientError, IbgeSidraClient
from guaraci.ibge.population import IbgePopulacaoDataSource
from guaraci.ibge.registro_civil import IbgeNascidosVivosRcDataSource, IbgeObitosRcDataSource
from guaraci.ibge.sidra import (
    IbgePibMunicipiosDataSource,
    IbgePopulacaoIdadeSexoDataSource,
    SidraAggregateSource,
)
from guaraci.ibge.territorio import IbgeAreaTerritorialDataSource

__all__ = [
    "IbgeSidraClient",
    "IbgeClientError",
    "SidraAggregateSource",
    "IbgePopulacaoDataSource",
    "IbgePibMunicipiosDataSource",
    "IbgePopulacaoIdadeSexoDataSource",
    "IbgeNascidosVivosRcDataSource",
    "IbgeObitosRcDataSource",
    "IbgeAreaTerritorialDataSource",
]
