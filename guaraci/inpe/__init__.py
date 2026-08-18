"""INPE (Instituto Nacional de Pesquisas Espaciais) data integration module.

Hosts direct integrations with INPE primary data services (principle 20 of
the ``vogel-stack``: integrate the official publisher, never a third-party
mirror).

Integrations:
- INPE Queimadas (BDQueimadas): fire-spot detections aggregated by year (and,
  since 2023, by month) from the ``dataserver-coids.inpe.br`` file server.
  Complements ``nasa_firms`` (near-real-time, satellite-native detections)
  with INPE's own reference product for Brazil.
"""

from guaraci.inpe.client import InpeQueimadasClient, InpeQueimadasClientError
from guaraci.inpe.queimadas import InpeQueimadasDataSource

__all__ = [
    "InpeQueimadasClient",
    "InpeQueimadasClientError",
    "InpeQueimadasDataSource",
]
