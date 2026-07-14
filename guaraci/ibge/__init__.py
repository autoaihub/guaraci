"""IBGE data sources for Guaraci.

Currently exposes population estimates by locality x year from the IBGE SIDRA
aggregates API (keyless JSON) — the denominator layer for health rates.
"""

from guaraci.ibge.client import IbgeClientError, IbgeSidraClient
from guaraci.ibge.population import IbgePopulacaoDataSource

__all__ = ["IbgeSidraClient", "IbgeClientError", "IbgePopulacaoDataSource"]
