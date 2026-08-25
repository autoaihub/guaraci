"""IBGE data sources for Guaraci (SIDRA aggregates API, keyless JSON).

Exposed sources:
- ``ibge_populacao``: population estimates by locality x year (table 6579)
- ``ibge_pib_municipios``: municipal GDP / PIB (table 5938)
- ``ibge_populacao_idade_sexo``: census population by sex and age (table 9514)
- ``ibge_nascidos_vivos_rc``: live births, registro civil (table 2680)
- ``ibge_obitos_rc``: deaths, registro civil (table 2681)
- ``ibge_area_territorial``: area/density/population, census 2022 (table 4714)
- ``ibge_casamentos``: marriages, registro civil (table 4406)
- ``ibge_divorcios``: divorces, registro civil (table 5937)
- ``ibge_saneamento_agua``: households by water supply, census 2022 (table 6803)
- ``ibge_saneamento_esgoto``: households by sanitary sewage, census 2022 (table 6805)
- ``ibge_saneamento_lixo``: households by garbage disposal, census 2022 (table 6892)

These are the denominator / socioeconomic layers for health-rate analysis.
"""

from guaraci.ibge.client import IbgeClientError, IbgeSidraClient
from guaraci.ibge.population import IbgePopulacaoDataSource
from guaraci.ibge.registro_civil import (
    IbgeCasamentosDataSource,
    IbgeDivorciosDataSource,
    IbgeNascidosVivosRcDataSource,
    IbgeObitosRcDataSource,
)
from guaraci.ibge.saneamento import (
    IbgeSaneamentoAguaDataSource,
    IbgeSaneamentoEsgotoDataSource,
    IbgeSaneamentoLixoDataSource,
)
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
    "IbgeCasamentosDataSource",
    "IbgeDivorciosDataSource",
    "IbgeSaneamentoAguaDataSource",
    "IbgeSaneamentoEsgotoDataSource",
    "IbgeSaneamentoLixoDataSource",
]
