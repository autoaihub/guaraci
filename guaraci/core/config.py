"""
Guaraci Configuration Management
===============================

Centralized configuration system using Pydantic for validation and type safety.
"""

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class GuaraciConfig(BaseSettings):
    """Main configuration class for Guaraci platform."""
    
    # Data directories
    data_root: Path = Field(default=Path("data"), description="Root directory for all data")
    temp_dir: Path = Field(default=Path("data/.temp"), description="Temporary files directory")
    default_download_root: Optional[Path] = Field(
        default=None,
        description=(
            "Optional root folder for user-facing downloads. "
            "When set, source outputs are created under this directory."
        ),
    )
    
    # DATASUS settings
    datasus_base_url: str = Field(default="https://datasus.saude.gov.br", description="DATASUS base URL")
    max_concurrent_downloads: int = Field(default=5, ge=1, le=20, description="Max concurrent downloads")
    download_timeout: int = Field(default=300, ge=30, description="Download timeout in seconds")
    retry_attempts: int = Field(default=3, ge=1, le=10, description="Number of retry attempts")
    
    # Processing settings
    chunk_size: int = Field(default=10000, ge=1000, description="Processing chunk size")
    memory_limit_gb: float = Field(default=4.0, ge=0.5, description="Memory limit in GB")
    
    # Output settings
    default_format: Literal["csv", "parquet", "sqlite"] = Field(default="csv", description="Default output format")
    compression: Optional[str] = Field(default="gzip", description="Compression method")
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO", description="Logging level")
    log_file: Optional[Path] = Field(default=None, description="Log file path")
    
    # API settings (for future web interface)
    api_host: str = Field(default="localhost", description="API host")
    api_port: int = Field(default=8000, ge=1024, le=65535, description="API port")
    api_workers: int = Field(default=1, ge=1, description="Number of API workers")
    
    model_config = ConfigDict(
        env_prefix="GUARACI_",
        env_file=".env",
        case_sensitive=False
    )
    
    @field_validator("data_root", "temp_dir", "default_download_root", mode="before")
    @classmethod
    def ensure_path_exists(cls, v):
        """Ensure directories exist."""
        if v is None:
            return v
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @field_validator("log_file", mode="before")
    @classmethod
    def ensure_log_dir_exists(cls, v):
        """Ensure log directory exists."""
        if v:
            path = Path(v)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return v
    
    def get_datasus_path(self, source: str) -> Path:
        """Get path for specific DATASUS source."""
        legacy_root_env = os.getenv("GUARACI_DEFAULT_OUTPUT_ROOT")
        legacy_root = Path(legacy_root_env) if legacy_root_env else None
        if legacy_root is not None:
            legacy_root.mkdir(parents=True, exist_ok=True)

        base_root = self.default_download_root or legacy_root or (self.data_root / "datasus")
        path = base_root / source
        path.mkdir(parents=True, exist_ok=True)
        return path
    

# Global configuration instance
config = GuaraciConfig()
