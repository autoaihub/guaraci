"""NASA climate data integration module.

Hosts direct integrations with NASA primary data services (principle 20 of
the ``vogel-stack``: integrate the official publisher, never a third-party
mirror). The first integration is NASA POWER (Prediction Of Worldwide Energy
Resources), a no-authentication REST API serving global meteorological and
solar series that fully cover Brazil.
"""

from guaraci.nasa.client import NasaPowerClient, NasaPowerClientError
from guaraci.nasa.power import NasaPowerDataSource

__all__ = [
    "NasaPowerClient",
    "NasaPowerClientError",
    "NasaPowerDataSource",
]
