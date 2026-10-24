"""Núcleo CKAN genérico: cliente, especificação de conjunto e datasource."""

from guaraci.ckan.client import (
    BROWSER_USER_AGENT,
    CkanClient,
    CkanClientError,
    CkanResource,
    resources_from_package,
)
from guaraci.ckan.datasets import CkanDataset, resource_kind, resource_period
from guaraci.ckan.datasource import CkanDataSource, ckan_datasource_for, select_resources

__all__ = [
    "BROWSER_USER_AGENT",
    "CkanClient",
    "CkanClientError",
    "CkanDataSource",
    "CkanDataset",
    "CkanResource",
    "ckan_datasource_for",
    "resource_kind",
    "resource_period",
    "resources_from_package",
    "select_resources",
]
