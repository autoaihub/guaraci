"""
Guaraci DATASUS SINAN Integration
================================

Enhanced module for downloading, processing, and exporting SINAN data via PySUS.
Includes error handling and performance optimizations.
"""

import os
import sqlite3
import datetime
from typing import Optional, Literal, List, Dict, Any, Callable
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
from guaraci.utils.mapping import UF_DICT
from guaraci.core.config import config


class SinanDataSource(DataSource):
    """Enhanced SINAN data source with error handling."""

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
        if self._sinan_instance is not None:
            return self._sinan_instance

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

    def download(
        self,
        start_year: int,
        end_year: int,
        diseases: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Download SINAN data with enhanced error handling.
        
        Parameters
        ----------
        start_year : int
            Starting year for data collection
        end_year : int
            Ending year for data collection
        diseases : List[str], optional
            List of disease codes. If None, uses NEGLECTED_DISEASES
        progress_callback : Callable[[int, int], None], optional
            Callback invoked with (completed, total) as files finish downloading
            
        Returns
        -------
        Dict[str, Any]
            Summary with total files, successful downloads, and failures
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
        
        logger.info(f"Starting SINAN download: {start_year}-{end_year}")
        logger.info(f"Diseases: {', '.join([f'{d} ({self.DISEASE_NAMES.get(d, d)})' for d in diseases])}")

        try:
            # Get available files
            all_files = self.sinan.get_files(dis_code=diseases, year=years)
            total_files = len(all_files)
            
            if total_files == 0:
                logger.warning("No files found for the specified criteria")
                return {
                    "successful_downloads": 0,
                    "failed_downloads": [],
                    "total_files": 0,
                }
                
            logger.info(f"Found {total_files} files to download")
            if progress_callback and total_files > 0:
                progress_callback(0, total_files)

            # Group files by disease
            grouped_files = defaultdict(list)
            for file_obj in all_files:
                disease_code = str(file_obj).split('BR')[0]
                grouped_files[disease_code].append(file_obj)

            # Download with progress tracking and error handling
            failed_downloads = []
            completed_downloads = 0
            
            # PySUS FTP singleton is not thread-safe; use single worker for reliability.
            worker_count = 1
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for disease, files in grouped_files.items():
                    disease_name = self.DISEASE_NAMES.get(disease, disease)
                    logger.info(f"Downloading {disease} ({disease_name}): {len(files)} files")
                    
                    # Submit download tasks
                    future_to_file = {
                        executor.submit(self._download_file_safe, file_obj): (disease, file_obj) 
                        for file_obj in files
                    }
                    
                    # Process completed downloads
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
                            completed_downloads += 1
                            if progress_callback and total_files > 0:
                                progress_callback(completed_downloads, total_files)

            # Report results
            successful_downloads = sum(len(files) for files in self.data.values())
            logger.info(f"Download completed: {successful_downloads}/{total_files} files successful")

            if failed_downloads:
                logger.warning(f"Failed downloads: {len(failed_downloads)}")
                for disease, file_name in failed_downloads[:5]:
                    logger.warning(f"  {disease}: {file_name}")
                if len(failed_downloads) > 5:
                    logger.warning(f"  ... and {len(failed_downloads) - 5} more")

            # Retorna informações úteis para o CLI
            return {
                "successful_downloads": successful_downloads,
                "failed_downloads": failed_downloads,
                "total_files": total_files
            }

            
        except Exception as e:
            logger.error(f"Download process failed: {e}")
            raise

    def _download_file_safe(self, file_obj) -> Optional[Any]:
        """Safely download a single file with retries."""
        ftpsingleton = None
        if PYSUS_AVAILABLE:
            try:
                from pysus.ftp import FTPSingleton  # type: ignore

                ftpsingleton = FTPSingleton
            except Exception:
                ftpsingleton = None

        for attempt in range(config.retry_attempts):
            try:
                if ftpsingleton:
                    ftpsingleton.close()
                downloaded = file_obj.download()
                if ftpsingleton:
                    ftpsingleton.close()
                return downloaded
            except Exception as e:
                if ftpsingleton:
                    try:
                        ftpsingleton.close()
                    except Exception:
                        pass
                if attempt == config.retry_attempts - 1:
                    logger.error(f"Failed to download {file_obj} after {config.retry_attempts} attempts: {e}")
                    return None
                else:
                    logger.debug(f"Download attempt {attempt + 1} failed for {file_obj}: {e}")
        return None

    def _load_as_polars(self, disease: str) -> pl.DataFrame:
        """
        Load all downloaded files for a disease into a single Polars DataFrame.
        Applies UF code mapping and handles null/unrecognized values safely.
        """
        if disease not in self.data:
            raise ValueError(f"Disease {disease} not found. Run download() first.")

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

    def load_dataframe(self, disease: str) -> pl.DataFrame:
        """Load and return data for a specific disease as a Polars DataFrame."""
        return self._load_as_polars(disease)

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

        conditions: List[pl.Expr] = []

        def resolve_column(options: List[str]) -> Optional[str]:
            for candidate in options:
                if candidate in df.columns:
                    return candidate
            return None

        uf_col = resolve_column(["UF", "SG_UF", "SG_UF_NOT"])
        if uf and uf_col:
            conditions.append(pl.col(uf_col) == uf)

        municipio_col = resolve_column(["ID_MN_RESI", "ID_MUNICIP"])
        if municipio and municipio_col:
            conditions.append(
                pl.col(municipio_col)
                .cast(pl.Utf8)
                .str.contains(municipio, literal=True, strict=False)
            )

        sexo_col = resolve_column(["CS_SEXO"])
        if sexo and sexo_col:
            conditions.append(pl.col(sexo_col) == sexo)

        faixa_col = resolve_column(["NU_IDADE_N"])
        if faixa_etaria and faixa_col:
            conditions.append(pl.col(faixa_col) == faixa_etaria)

        evolucao_col = resolve_column(["CS_EVOLU", "EVOLUCAO"])
        if evolucao and evolucao_col:
            conditions.append(pl.col(evolucao_col) == evolucao)

        classificacao_col = resolve_column(["CLASSI_FIN", "CLASSIFICAC"])
        if classificacao and classificacao_col:
            conditions.append(pl.col(classificacao_col) == classificacao)

        ano_col = resolve_column(["NU_ANO", "ANO", "ANO_NOT"])
        if ano and ano_col:
            conditions.append(pl.col(ano_col) == ano)

        if not conditions:
            return df

        combined = conditions[0]
        for condition in conditions[1:]:
            combined = combined & condition

        return df.filter(combined)

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

    def export(
        self,
        df: pl.DataFrame,
        format: Literal["csv", "sqlite", "parquet"] = "csv",
        name: str = "output",
    ) -> Optional[Path]:
        """Exporta o DataFrame filtrado e retorna o caminho gerado."""
        if df is None or len(df) == 0:
            logger.warning(f"Nenhum dado disponível para exportar: {name}")
            return None

        output_dir = Path(self.output_path)
        final_stem = name

        if "_" in name:
            partes = name.split("_")
            if len(partes) >= 3 and partes[-2].isdigit() and partes[-1].isdigit():
                start_year, end_year = int(partes[-2]), int(partes[-1])
                if "NU_ANO" in df.columns:
                    raw_years = df["NU_ANO"].unique().to_list()
                    present_years = {
                        int(str(value).strip())
                        for value in raw_years
                        if str(value).strip().isdigit()
                    }
                    expected_years = set(range(start_year, end_year + 1))
                    if not expected_years.issubset(present_years):
                        final_stem = f"{name}_partial"
                        logger.warning(
                            f"O intervalo declarado ({start_year}-{end_year}) não corresponde aos dados reais ({sorted(present_years) or raw_years}). "
                            f"O arquivo foi salvo como '{final_stem}.{format}'."
                        )

        final_path = output_dir / f"{final_stem}.{format}"

        if format == "csv":
            df.write_csv(final_path)
        elif format == "parquet":
            df.write_parquet(final_path)
        elif format == "sqlite":
            db_path = output_dir / f"{final_stem}.db"
            con = sqlite3.connect(db_path)
            df.to_pandas().to_sql(name=final_stem, con=con, if_exists="replace", index=False)
            con.close()
        else:
            raise ValueError("Formato inválido. Escolha entre 'csv', 'sqlite' ou 'parquet'.")

        logger.info(f"Exported dataset -> {final_path}")
        return final_path

    def export_per_year(self, disease: str, format: str = "csv"):
        """Exporta arquivos individuais por ano para doenças com múltiplos anos baixados."""
        if disease not in self.data or not self.data[disease]:
            logger.warning(f"Nenhum arquivo disponível para {disease}.")
            return

        # Corrige acesso: extrai caminhos válidos de ParquetSet ou Path
        paths = []
        for p in self.data[disease]:
            if hasattr(p, "path"):  # ParquetSet
                try:
                    path_str = str(p.path)
                    if os.path.exists(path_str):
                        paths.append(path_str)
                except Exception:
                    continue
            elif isinstance(p, (str, Path)) and os.path.exists(p):
                paths.append(str(p))

        if not paths:
            logger.warning(f"Nenhum caminho de arquivo válido encontrado para {disease}.")
            return

        # Extrai anos de cada caminho
        successful_years = sorted({
            Path(p).stem[-4:] for p in paths if Path(p).stem[-4:].isdigit()
        })

        if not successful_years:
            logger.warning(f"Nenhum ano válido encontrado para {disease}.")
            return

        for year in successful_years:
            try:
                df = self.load_dataframe(disease)

                # Filtra apenas o ano específico, se aplicável
                if "NU_ANO" in df.columns:
                    df = df.filter(pl.col("NU_ANO") == int(year))

                output_name = f"{disease}_{year}"
                exported_path = self.export(df, format=format, name=output_name)
                if exported_path:
                    logger.info(f"Exported {disease} {year} -> {exported_path.name} ({len(df)} registros)")
                else:
                    logger.warning(f"Export skipped for {disease} {year}: no data")

            except Exception as e:
                logger.error(f"Failed to export {disease} {year}: {e}")

    # -----------------------------------------------------------
    # METADADOS
    # -----------------------------------------------------------

    def describe_fields(self, disease: str) -> list[str]:
        """Lista todas as colunas disponíveis para uma doença."""
        df = self.load_dataframe(disease)
        return df.columns
