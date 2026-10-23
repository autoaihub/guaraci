"""Camadas geográficas servidas por WFS (SGB, FUNAI), exportadas como tabelas com WKT."""

from guaraci.geo.wfs import (
    WFS_FAMILIES,
    WfsClient,
    WfsDataSource,
    WfsError,
    WfsFamily,
    WfsLayer,
)

__all__ = ["WFS_FAMILIES", "WfsClient", "WfsDataSource", "WfsError", "WfsFamily", "WfsLayer"]
