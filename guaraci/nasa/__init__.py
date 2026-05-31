"""NASA climate data integration module.

Hosts direct integrations with NASA primary data services (principle 20 of
the ``vogel-stack``: integrate the official publisher, never a third-party
mirror).

Integrations:
- NASA POWER (Prediction Of Worldwide Energy Resources): keyless REST API
  serving global meteorological and solar series that fully cover Brazil.
- NASA FIRMS (Fire Information for Resource Management System): active-fire
  and thermal-anomaly detections from MODIS/VIIRS (requires a free MAP_KEY).
- NASA GPM IMERG (precipitation) via GES DISC OPeNDAP point subsetting
  (requires an Earthdata Login token; experimental, see ``gpm`` module).
"""

from guaraci.nasa.client import (
    NasaFirmsClient,
    NasaFirmsClientError,
    NasaGesDiscClient,
    NasaGesDiscClientError,
    NasaPowerClient,
    NasaPowerClientError,
)
from guaraci.nasa.firms import NasaFirmsDataSource
from guaraci.nasa.gpm import NasaGpmDataSource
from guaraci.nasa.power import NasaPowerDataSource

__all__ = [
    "NasaPowerClient",
    "NasaPowerClientError",
    "NasaPowerDataSource",
    "NasaFirmsClient",
    "NasaFirmsClientError",
    "NasaFirmsDataSource",
    "NasaGesDiscClient",
    "NasaGesDiscClientError",
    "NasaGpmDataSource",
]
