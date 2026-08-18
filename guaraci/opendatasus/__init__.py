"""OpenDataSUS integration module."""

from guaraci.opendatasus.client import OpenDataSUSClient, OpenDataSUSClientError
from guaraci.opendatasus.datasource import OpenDataSUSDataSource
from guaraci.opendatasus.portal_files import (
    PortalFileDataSource,
    PortalFilesClient,
    PortalFilesClientError,
)

__all__ = [
    "OpenDataSUSClient",
    "OpenDataSUSClientError",
    "OpenDataSUSDataSource",
    "PortalFileDataSource",
    "PortalFilesClient",
    "PortalFilesClientError",
]
