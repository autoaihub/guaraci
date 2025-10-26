"""
Guaraci Core DataSource
======================

Abstract base class for all data sources in the Guaraci platform.
Provides common functionality for data downloading, caching, and management.
"""

import os
import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union
from datetime import datetime, timedelta

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
        self.cache_path = config.get_cache_path(name)
        
        # Ensure directories exist
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized {self.__class__.__name__} with output_path: {self.output_path}")

    @abstractmethod
    def download(self, *args, **kwargs) -> 'DataSource':
        """Download data from the source. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:
        """Load data as a Polars DataFrame. Must be implemented by subclasses."""
        pass

    def get_cache_key(self, **params) -> str:
        """Generate a cache key based on parameters."""
        # Sort parameters for consistent hashing
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        return hashlib.md5(sorted_params.encode()).hexdigest()

    def is_cache_valid(self, cache_file: Path, max_age_hours: int = 24) -> bool:
        """Check if cache file exists and is not too old."""
        if not cache_file.exists():
            return False
        
        file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        return file_age < timedelta(hours=max_age_hours)

    def save_to_cache(self, data: pl.DataFrame, cache_key: str) -> Path:
        """Save DataFrame to cache."""
        cache_file = self.cache_path / f"{cache_key}.parquet"
        data.write_parquet(cache_file)
        logger.debug(f"Saved data to cache: {cache_file}")
        return cache_file

    def load_from_cache(self, cache_key: str) -> Optional[pl.DataFrame]:
        """Load DataFrame from cache if available and valid."""
        cache_file = self.cache_path / f"{cache_key}.parquet"
        
        if self.is_cache_valid(cache_file):
            logger.debug(f"Loading data from cache: {cache_file}")
            return pl.read_parquet(cache_file)
        
        return None

    def clear_cache(self) -> None:
        """Clear all cached data for this source."""
        for cache_file in self.cache_path.glob("*.parquet"):
            cache_file.unlink()
        logger.info(f"Cleared cache for {self.name}")

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about this data source."""
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "output_path": str(self.output_path),
            "cache_path": str(self.cache_path),
            "cache_files": len(list(self.cache_path.glob("*.parquet"))),
            "output_files": len(list(self.output_path.glob("*")))
        }

    def info(self) -> str:
        """Return a summary of the data source."""
        metadata = self.get_metadata()
        return (
            f"{metadata['class']}(\n"
            f"  name='{metadata['name']}',\n"
            f"  output_path='{metadata['output_path']}',\n"
            f"  cache_files={metadata['cache_files']},\n"
            f"  output_files={metadata['output_files']}\n"
            f")"
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
