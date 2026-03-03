"""
Guaraci Core Module
==================

Core functionality and base classes for the Guaraci platform.
"""

from guaraci.core.datasource import DataSource
from guaraci.core.config import GuaraciConfig
from guaraci.core.contracts import DownloadManifest, SourceParameterSpec, validate_source_params
from guaraci.core.results import JobResult

__all__ = [
    "DataSource",
    "GuaraciConfig",
    "SourceParameterSpec",
    "validate_source_params",
    "DownloadManifest",
    "JobResult",
]
