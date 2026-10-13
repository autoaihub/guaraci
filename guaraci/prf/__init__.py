"""Acidentes em rodovias federais (PRF, dados abertos)."""

from guaraci.prf.acidentes import (
    PAGE_URL,
    PRF_SPECS,
    PrfAcidentesDataSource,
    PrfClient,
    PrfClientError,
    datasource_for,
)

__all__ = [
    "PAGE_URL",
    "PRF_SPECS",
    "PrfAcidentesDataSource",
    "PrfClient",
    "PrfClientError",
    "datasource_for",
]
