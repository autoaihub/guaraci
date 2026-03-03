"""
Guaraci Core DataSource
======================

Abstract base class for all data sources in the Guaraci platform.
Provides common functionality for data downloading and management.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

import polars as pl
from loguru import logger

from guaraci.core.config import config


class DataSource(ABC):
    """Abstract base class for all Guaraci data sources."""

    def __init__(self, name: str, output_path: Optional[Union[str, Path]] = None):
        """
        Initialize the data source.

        Parameters
        ----------
        name : str
            Name of the data source (e.g., 'sinan', 'climate').
        output_path : str or Path, optional
            Base path for saving data. If None, uses config default.
        """
        self.name = name
        self.output_path = Path(output_path) if output_path else config.get_datasus_path(name)
        
        # Ensure directories exist
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized {self.__class__.__name__} (output: {self.output_path})")

    @abstractmethod
    def download(self, *args, **kwargs) -> Any:
        """Run a download job and return its result payload."""
        pass

    @abstractmethod
    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:
        """Load data as a Polars DataFrame. Must be implemented by subclasses."""
        pass

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about this data source."""
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "output_path": str(self.output_path),
            "output_files": len(list(self.output_path.glob("*")))
        }

    def info(self) -> str:
        """Return a summary of the data source."""
        metadata = self.get_metadata()
        return (
            f"{metadata['class']}(\n"
            f"  name='{metadata['name']}',\n"
            f"  output_path='{metadata['output_path']}',\n"
            f"  output_files={metadata['output_files']}\n"
            f")"
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
