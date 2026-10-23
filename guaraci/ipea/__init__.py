"""IPEADATA: séries sem par primário acessível e catálogo de metadados."""

from guaraci.ipea.ipeadata import IpeadataMetadadosDataSource, IpeadataSeriesDataSource
from guaraci.ipea.series import DEFAULT_SERIES, DEFAULT_SERIES_CODES

__all__ = [
    "DEFAULT_SERIES",
    "DEFAULT_SERIES_CODES",
    "IpeadataMetadadosDataSource",
    "IpeadataSeriesDataSource",
]
