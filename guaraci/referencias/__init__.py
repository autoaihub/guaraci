"""Tabelas oficiais de códigos (IBGE, DATASUS, CONCLA, TSE), publicadas como estão.

O Guaraci só baixa cada tabela; a junção entre bases fica para quem consome.
"""

from guaraci.referencias.base import ReferenciaDataSource
from guaraci.referencias.cid10 import Cid10DataSource
from guaraci.referencias.ibge_json import (
    CnaeClassesDataSource,
    CnaeSubclassesDataSource,
    IbgeDistritosDataSource,
    IbgeMunicipiosDataSource,
)
from guaraci.referencias.sigtap import SigtapDataSource
from guaraci.referencias.tse import TseMunicipiosDataSource

__all__ = [
    "Cid10DataSource",
    "CnaeClassesDataSource",
    "CnaeSubclassesDataSource",
    "IbgeDistritosDataSource",
    "IbgeMunicipiosDataSource",
    "ReferenciaDataSource",
    "SigtapDataSource",
    "TseMunicipiosDataSource",
]
