"""Ministério do Desenvolvimento e Assistência Social (MDS), SAGI."""

from guaraci.mds.campos import CAMPOS_CHAVE, GRUPOS, VERIFICADO_EM
from guaraci.mds.misocial import (
    ANO_PADRAO,
    BASE_URL,
    DATASET,
    MIN_YEAR,
    MisocialClient,
    MisocialClientError,
    MisocialDataSource,
    campos_dos_grupos,
)

__all__ = [
    "ANO_PADRAO",
    "BASE_URL",
    "CAMPOS_CHAVE",
    "DATASET",
    "GRUPOS",
    "MIN_YEAR",
    "MisocialClient",
    "MisocialClientError",
    "MisocialDataSource",
    "VERIFICADO_EM",
    "campos_dos_grupos",
]
