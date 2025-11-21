"""
Guaraci DATASUS Module
=====================

Integration with Brazilian DATASUS health information systems.
"""

from guaraci.datasus.sinan import SinanDataSource
from guaraci.datasus.sim import SimDataSource
from guaraci.datasus.sih import SihDataSource

__all__ = ["SinanDataSource", "SimDataSource", "SihDataSource"]
