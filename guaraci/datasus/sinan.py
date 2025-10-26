"""
Guaraci DATASUS SINAN Integration
================================

Enhanced module for downloading, processing, and exporting SINAN data via PySUS.
Includes caching, error handling, and performance optimizations.
"""

import os
import sqlite3
import datetime
from typing import Optional, Literal, List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import polars as pl
import pandas as pd
import numpy as np
from tqdm import tqdm
from collections import defaultdict
from pyarrow import parquet
from loguru import logger

try:
    from pysus import SINAN
    PYSUS_AVAILABLE = True
except ImportError:
    PYSUS_AVAILABLE = False
    SINAN = None

from guaraci.core.datasource import DataSource
from guaraci.utils.mapping import utility_mapping, UF_DICT
from guaraci.core.config import config


class SinanDataSource(DataSource):
    """Enhanced SINAN data source with caching and error handling."""

    NEGLECTED_DISEASES = ['ANIM', 'CHAG', 'CHIK', 'DENG', 'ESQU', 'HANS', 'LEIV', 'LTAN', 'RAIV']
    
    # Disease name mapping for better user experience
    DISEASE_NAMES = {
        'ANIM': 'Acidentes por Animais Peçonhentos',
        'CHAG': 'Doença de Chagas',
        'CHIK': 'Chikungunya',
        'DENG': 'Dengue',
        'ESQU': 'Esquistossomose',
        'HANS': 'Hanseníase',
        'LEIV': 'Leishmaniose Visceral',
        'LTAN': 'Leishmaniose Tegumentar',
        'RAIV': 'Raiva Humana'
    }

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sinan", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)
        self._sinan_instance = None
        
        if not PYSUS_AVAILABLE:
            logger.warning(
                "PySUS is not installed. SINAN functionality will be limited. "
                "Install with: pip install 'guaraci[datasus]' or pip install pysus"
            )
        
    @property
    def sinan(self):
        """Lazy loading of SINAN instance."""
        if not PYSUS_AVAILABLE:
            raise ImportError(
                "PySUS is required for SINAN functionality. "
                "Install with: pip install 'guaraci[datasus]' or pip install pysus"
            )
            
        if self._sinan_instance is None:
            try:
                self._sinan_instance = SINAN().load()
                logger.debug("SINAN instance loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load SINAN instance: {e}")
                raise
        return self._sinan_instance

    def download(self, start_year: int, end_year: int, diseases: Optional[List[str]] = None, 
                 use_cache: bool = True, force_download: bool = False) -> 'SinanDataSource':
        """
        Download SINAN data with enhanced error handling and caching.
        
        Parameters
        ----------
        start_year : int
            Starting year for data collection
        end_year : int
            Ending year for data collection
        diseases : List[str], optional
            List of disease codes. If None, uses NEGLECTED_DISEASES
        use_cache : bool, default True
            Whether to use cached data if available
        force_download : bool, default False
            Force re-download even if cache exists
            
        Returns
        -------
        SinanDataSource
            Self for method chaining
        """
        if diseases is None:
            diseases = self.NEGLECTED_DISEASES.copy()

        # Validate years
        current_year = datetime.datetime.now().year
        if end_year >= current_year:
            logger.warning(f"End year {end_year} adjusted to {current_year - 1} (current year - 1)")
            end_year = current_year - 1
            
        if start_year > end_year:
            raise ValueError(f"Start year ({start_year}) cannot be greater than end year ({end_year})")

        years = list(range(start_year, end_year + 1))
        
        # Check cache first
        cache_key = self.get_cache_key(
            start_year=start_year, 
            end_year=end_year, 
            diseases=sorted(diseases)
        )
        
        if use_cache and not force_download:
            cached_data = self.load_from_cache(cache_key)
            if cached_data is not None:
                logger.info("Using cached data")
                # Reconstruct self.data from cache metadata if needed
                return self

        logger.info(f"Starting SINAN download: {start_year}-{end_year}")
        logger.info(f"Diseases: {', '.join([f'{d} ({self.DISEASE_NAMES.get(d, d)})' for d in diseases])}")

        try:
            # Get available files
            all_files = self.sinan.get_files(dis_code=diseases, year=years)
            total_files = len(all_files)
            
            if total_files == 0:
                logger.warning("No files found for the specified criteria")
                return self
                
            logger.info(f"Found {total_files} files to download")

            # Group files by disease
            grouped_files = defaultdict(list)
            for file_obj in all_files:
                disease_code = str(file_obj).split('BR')[0]
                grouped_files[disease_code].append(file_obj)

            # Download with progress tracking and error handling
            failed_downloads = []
            
            with ThreadPoolExecutor(max_workers=config.max_concurrent_downloads) as executor:
                for disease, files in grouped_files.items():
                    disease_name = self.DISEASE_NAMES.get(disease, disease)
                    logger.info(f"Downloading {disease} ({disease_name}): {len(files)} files")
                    
                    # Submit download tasks
                    future_to_file = {
                        executor.submit(self._download_file_safe, file_obj): (disease, file_obj) 
                        for file_obj in files
                    }
                    
                    # Process completed downloads
                    with tqdm(total=len(files), desc=f"{disease}", unit="file") as pbar:
                        for future in as_completed(future_to_file):
                            disease_code, file_obj = future_to_file[future]
                            try:
                                downloaded_path = future.result()
                                if downloaded_path:
                                    self.data[disease_code].append(downloaded_path)
                                else:
                                    failed_downloads.append((disease_code, str(file_obj)))
                            except Exception as e:
                                logger.error(f"Failed to download {file_obj}: {e}")
                                failed_downloads.append((disease_code, str(file_obj)))
                            finally:
                                pbar.update(1)

            # Report results
            successful_downloads = sum(len(files) for files in self.data.values())
            logger.info(f"Download completed: {successful_downloads}/{total_files} files successful")
            
            if failed_downloads:
                logger.warning(f"Failed downloads: {len(failed_downloads)}")
                for disease, file_name in failed_downloads[:5]:  # Show first 5 failures
                    logger.warning(f"  {disease}: {file_name}")
                if len(failed_downloads) > 5:
                    logger.warning(f"  ... and {len(failed_downloads) - 5} more")

            return self
            
        except Exception as e:
            logger.error(f"Download process failed: {e}")
            raise

    def _download_file_safe(self, file_obj) -> Optional[Path]:
        """Safely download a single file with retries."""
        for attempt in range(config.retry_attempts):
            try:
                downloaded = file_obj.download()
                return downloaded
            except Exception as e:
                if attempt == config.retry_attempts - 1:
                    logger.error(f"Failed to download {file_obj} after {config.retry_attempts} attempts: {e}")
                    return None
                else:
                    logger.debug(f"Download attempt {attempt + 1} failed for {file_obj}: {e}")
        return None

    def _load_as_polars(self, disease: str, use_cache: bool = True) -> pl.DataFrame:
        """
        Load all downloaded files for a disease into a single Polars DataFrame.
        Applies UF code mapping and handles null/unrecognized values safely.
        """
        if disease not in self.data:
            raise ValueError(f"Disease {disease} not found. Run download() first.")
            
        # Check cache first
        cache_key = f"{disease}_processed"
        if use_cache:
            cached_df = self.load_from_cache(cache_key)
            if cached_df is not None:
                logger.debug(f"Loaded {disease} from cache: {len(cached_df)} records")
                return cached_df

        parquet_sets = self.data[disease]
        if not parquet_sets:
            logger.warning(f"No data found for {disease}")
            return pl.DataFrame()

        combined_dfs = []
        total_files = len(parquet_sets)
        
        logger.info(f"Processing {total_files} parquet sets for {disease}")

        with tqdm(total=total_files, desc=f"Loading {disease}", unit="file") as pbar:
            for parquet_set in parquet_sets:
                try:
                    # PySUS returns ParquetSet objects, we need to read them as pandas first
                    # then convert to polars
                    import pandas as pd
                    
                    # Read the parquet set as pandas DataFrame
                    df_pandas = parquet_set.to_dataframe()
                    
                    # Convert to polars
                    df = pl.from_pandas(df_pandas)
                    
                    # Apply UF mapping safely
                    df = self._apply_uf_mapping(df)
                    
                    combined_dfs.append(df)
                    
                except Exception as e:
                    logger.error(f"Failed to process parquet set {parquet_set}: {e}")
                finally:
                    pbar.update(1)

        if not combined_dfs:
            logger.warning(f"No valid data found for {disease}")
            return pl.DataFrame()

        # Combine all DataFrames
        logger.info(f"Combining {len(combined_dfs)} DataFrames for {disease}")
        combined = pl.concat(combined_dfs, how="diagonal")
        
        # Cache the processed data
        if use_cache:
            self.save_to_cache(combined, cache_key)
        
        logger.info(f"✅ {disease}: {len(combined)} records loaded, {len(combined.columns)} columns")
        return combined

    def _apply_uf_mapping(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply UF code to state abbreviation mapping safely."""
        
        def safe_uf_mapping(value):
            """Safe UF mapping that handles various input types."""
            if value is None or pd.isna(value):
                return None
                
            # Convert to string and clean
            str_val = str(value).strip().upper()
            
            # Handle empty or invalid values
            if not str_val or str_val in ["NAN", "NONE", "NULL", "0", ""]:
                return None
                
            # If already a valid UF code, return as-is
            if str_val in UF_DICT.values():
                return str_val
                
            # Try to convert numeric code to UF
            try:
                numeric_code = int(float(str_val))
                return UF_DICT.get(numeric_code)
            except (ValueError, TypeError):
                return None

        # Find UF-related columns
        uf_columns = [
            col for col in df.columns 
            if any(pattern in col.upper() for pattern in ["UF", "_UF", "SG_UF"])
        ]
        
        # Apply mapping to UF columns
        for col in uf_columns:
            try:
                df = df.with_columns([
                    pl.col(col)
                    .map_elements(safe_uf_mapping, return_dtype=pl.Utf8)
                    .alias(col)
                ])
            except Exception as e:
                logger.warning(f"Failed to apply UF mapping to column {col}: {e}")
        
        return df

    def load_dataframe(self, disease: str, use_cache: bool = True) -> pl.DataFrame:
        """Load and return data for a specific disease as a Polars DataFrame."""
        return self._load_as_polars(disease, use_cache=use_cache)

    # -----------------------------------------------------------
    # FILTRAGEM
    # -----------------------------------------------------------

    def filter(
        self,
        df: Optional[pl.DataFrame] = None,
        uf: Optional[str] = None,
        municipio: Optional[str] = None,
        sexo: Optional[str] = None,
        faixa_etaria: Optional[str] = None,
        evolucao: Optional[str] = None,
        classificacao: Optional[str] = None,
        ano: Optional[int] = None,
    ) -> pl.DataFrame:
        """Aplica filtros dinâmicos ao DataFrame do SINAN."""
        if df is None:
            raise ValueError("É necessário fornecer um DataFrame para filtragem.")

        conds = []
        if uf: conds.append(pl.col("UF") == uf)
        if municipio: conds.append(pl.col("ID_MN_RESI").str.contains(municipio))
        if sexo: conds.append(pl.col("CS_SEXO") == sexo)
        if faixa_etaria: conds.append(pl.col("NU_IDADE_N") == faixa_etaria)
        if evolucao: conds.append(pl.col("CS_EVOLU") == evolucao)
        if classificacao: conds.append(pl.col("CLASSI_FIN") == classificacao)
        if ano: conds.append(pl.col("NU_ANO") == ano)

        return df.filter(pl.all(conds)) if conds else df

    # -----------------------------------------------------------
    # SUMARIZAÇÃO
    # -----------------------------------------------------------

    def summary(self, df: pl.DataFrame, by: str = "UF", metric: Literal["count", "mean", "sum"] = "count") -> pl.DataFrame:
        """Gera uma tabela resumida por agrupamento."""
        if by not in df.columns:
            raise ValueError(f"A coluna '{by}' não existe no DataFrame.")
        if metric == "count":
            return df.groupby(by).count().sort(by)
        elif metric == "mean":
            return df.groupby(by).mean().sort(by)
        elif metric == "sum":
            return df.groupby(by).sum().sort(by)
        else:
            raise ValueError("metric deve ser 'count', 'mean' ou 'sum'.")

    # EXPORTAÇÃO

    def export(self, df: pl.DataFrame, format: Literal["csv", "sqlite", "parquet"] = "csv", name: str = "output"):
        """Exporta o DataFrame filtrado para CSV, SQLite ou Parquet."""
        path = os.path.join(self.output_path, f"{name}.{format}")
        if format == "csv":
            df.write_csv(path)
        elif format == "parquet":
            df.write_parquet(path)
        elif format == "sqlite":
            con = sqlite3.connect(os.path.join(self.output_path, f"{name}.db"))
            df_pandas = df.to_pandas()
            df_pandas.to_sql(name=name, con=con, if_exists="replace", index=False)
            con.close()
        else:
            raise ValueError("Formato inválido. Escolha entre 'csv', 'sqlite' ou 'parquet'.")
        print(f"Arquivo exportado: {path}")

    # -----------------------------------------------------------
    # METADADOS
    # -----------------------------------------------------------

    def describe_fields(self, disease: str) -> list[str]:
        """Lista todas as colunas disponíveis para uma doença."""
        df = self.load_dataframe(disease)
        return df.columns
