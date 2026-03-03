"""
Guaraci SNIS Module
===================

SNIS (Saneamento) data access.
"""

from guaraci.snis.snis import SnisDataSource
from guaraci.snis.sinisa import SinisaDataSource
from guaraci.snis.legacy import SnisLegacyBigQueryDataSource

__all__ = ["SnisDataSource", "SinisaDataSource", "SnisLegacyBigQueryDataSource"]
