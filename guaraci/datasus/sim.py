"""
Guaraci DATASUS SIM Integration
===============================

Module for downloading, processing and exporting SIM (Mortality Information
System) data via PySUS.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

import polars as pl
from loguru import logger
from pyarrow import parquet  # noqa: F401  - kept for parity with SINAN module

from guaraci.core.config import config
from guaraci.core.datasource import DataSource
from guaraci.utils.mapping import apply_uf_mapping_polars

try:
    # PySUS re-exports SIM from pysus.ftp.databases.sim
    from pysus import SIM  # type: ignore

    PYSUS_AVAILABLE = True
except ImportError:  # pragma: no cover - handled at runtime
    PYSUS_AVAILABLE = False
    SIM = None  # type: ignore


class SimDataSource(DataSource):
    """
    SIM data source backed by PySUS.

    This class focuses on the CID10 mortality database (default), with optional
    access to the legacy CID9 group when requested.
    """

    # Supported SIM groups in PySUS
    DEFAULT_GROUPS: List[str] = ["CID10"]
    ALL_GROUPS: List[str] = ["CID10", "CID9"]

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sim", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)
        self._sim_instance = None

        if not PYSUS_AVAILABLE:
            logger.warning(
                "PySUS is not installed. SIM functionality will be unavailable. "
                "Install with: pip install 'guaraci[datasus]' or pip install pysus"
            )

    # ------------------------------------------------------------------
    # PySUS backend access
    # ------------------------------------------------------------------
    @property
    def sim(self):
        """Lazy loading of SIM instance."""
        if not PYSUS_AVAILABLE:
            raise ImportError(
                "PySUS is required for SIM functionality. "
                "Install with: pip install 'guaraci[datasus]' or pip install pysus"
            )

        if self._sim_instance is None:
            try:
                self._sim_instance = SIM().load()
                logger.debug("SIM instance loaded successfully")
            except Exception as exc:  # pragma: no cover - runtime protection
                logger.error(f"Failed to load SIM instance: {exc}")
                raise
        return self._sim_instance

    # ------------------------------------------------------------------
    # DOWNLOAD
    # ------------------------------------------------------------------
    def download(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Download SIM data with basic error handling.

        Parameters
        ----------
        start_year : int
            Starting year for data collection.
        end_year : int
            Ending year for data collection.
        groups : List[str], optional
            SIM groups to download (e.g., ['CID10', 'CID9']). Defaults to
            CID10 only.
        states : List[str], optional
            Two-letter UF codes. If None, all available states are fetched.
        progress_callback : Callable[[int, int], None], optional
            Callback invoked with (completed, total) as files finish downloading.

        Returns
        -------
        Dict[str, Any]
            Summary with total files, successful downloads and failures.
        """
        # Years validation (avoid requesting future years)
        current_year = datetime.datetime.now().year
        if end_year >= current_year:
            logger.warning(
                f"End year {end_year} adjusted to {current_year - 1} (current year - 1)"
            )
            end_year = current_year - 1

        if start_year > end_year:
            raise ValueError(
                f"Start year ({start_year}) cannot be greater than end year ({end_year})"
            )

        years = list(range(start_year, end_year + 1))

        # Groups validation
        if groups is None or not groups:
            groups = self.DEFAULT_GROUPS.copy()
        else:
            unknown = {g for g in groups if g.upper() not in self.ALL_GROUPS}
            if unknown:
                raise ValueError(f"Unknown SIM group(s): {', '.join(sorted(unknown))}")
            groups = [g.upper() for g in groups]

        logger.info(f"Starting SIM download: {start_year}-{end_year}")
        logger.info(f"Groups: {', '.join(groups)}")
        if states:
            logger.info(f"States: {', '.join(states)}")

        try:
            # Request file list from PySUS
            all_files = self.sim.get_files(group=groups, uf=states, year=years)
            total_files = len(all_files)

            if total_files == 0:
                logger.warning("No SIM files found for the specified criteria")
                return {
                    "successful_downloads": 0,
                    "failed_downloads": [],
                    "total_files": 0,
                }

            logger.info(f"Found {total_files} SIM files to download")
            if progress_callback and total_files > 0:
                progress_callback(0, total_files)

            # Group files by SIM group (CID10/CID9) using PySUS metadata
            grouped_files: Dict[str, List[Any]] = defaultdict(list)
            for file_obj in all_files:
                try:
                    desc = self.sim.describe(file_obj)
                    group_name = desc.get("group", "UNKNOWN")
                except Exception:
                    group_name = "UNKNOWN"
                grouped_files[group_name].append(file_obj)

            failed_downloads: List[tuple[str, str]] = []
            completed_downloads = 0

            # PySUS FTP singleton is not thread-safe; use single worker for reliability.
            worker_count = 1

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for group_name, files in grouped_files.items():
                    logger.info(f"Downloading SIM {group_name}: {len(files)} files")

                    future_to_file = {
                        executor.submit(self._download_file_safe, file_obj): (group_name, file_obj)
                        for file_obj in files
                    }

                    for future in as_completed(future_to_file):
                        group_name, file_obj = future_to_file[future]
                        try:
                            downloaded_path = future.result()
                            if downloaded_path:
                                self.data[group_name].append(downloaded_path)
                            else:
                                failed_downloads.append((group_name, str(file_obj)))
                        except Exception as exc:
                            logger.error(f"Failed to download {file_obj}: {exc}")
                            failed_downloads.append((group_name, str(file_obj)))
                        finally:
                            completed_downloads += 1
                            if progress_callback and total_files > 0:
                                progress_callback(completed_downloads, total_files)

            successful_downloads = sum(len(files) for files in self.data.values())
            logger.info(
                f"SIM download completed: {successful_downloads}/{total_files} files successful"
            )

            if failed_downloads:
                logger.warning(f"Failed SIM downloads: {len(failed_downloads)}")
                for group_name, file_name in failed_downloads[:5]:
                    logger.warning(f"  {group_name}: {file_name}")
                if len(failed_downloads) > 5:
                    logger.warning(f"  ... and {len(failed_downloads) - 5} more")

            return {
                "successful_downloads": successful_downloads,
                "failed_downloads": failed_downloads,
                "total_files": total_files,
            }

        except Exception as exc:
            logger.error(f"SIM download process failed: {exc}")
            raise

    def _download_file_safe(self, file_obj) -> Optional[Any]:
        """Safely download a single SIM file with retries."""
        ftpsingleton = None
        if PYSUS_AVAILABLE:
            try:
                # Resetting the PySUS FTP singleton helps avoid stale connections.
                from pysus.ftp import FTPSingleton  # type: ignore

                ftpsingleton = FTPSingleton
            except Exception:
                ftpsingleton = None

        for attempt in range(config.retry_attempts):
            try:
                if ftpsingleton:
                    ftpsingleton.close()

                # PySUS File.download() returns a Data object that resolves to ParquetSet
                downloaded = file_obj.download()
                if ftpsingleton:
                    ftpsingleton.close()
                return downloaded
            except Exception as exc:
                if ftpsingleton:
                    try:
                        ftpsingleton.close()
                    except Exception:
                        pass
                if attempt == config.retry_attempts - 1:
                    logger.error(
                        f"Failed to download {file_obj} after "
                        f"{config.retry_attempts} attempts: {exc}"
                    )
                    return None
                logger.debug(
                    f"Download attempt {attempt + 1} failed for {file_obj}: {exc}"
                )
        return None

    # ------------------------------------------------------------------
    # LOADING
    # ------------------------------------------------------------------
    def _load_as_polars(self, group: str) -> pl.DataFrame:
        """
        Load all downloaded files for a SIM group (CID10/CID9)
        into a single Polars DataFrame.
        """
        if group not in self.data:
            raise ValueError(f"Group {group} not found. Run download() first.")

        parquet_sets = self.data[group]
        if not parquet_sets:
            logger.warning(f"No data found for SIM group {group}")
            return pl.DataFrame()

        combined_dfs: List[pl.DataFrame] = []
        total_files = len(parquet_sets)

        logger.info(f"Processing {total_files} parquet sets for SIM {group}")

        from tqdm import tqdm

        with tqdm(total=total_files, desc=f"Loading SIM {group}", unit="file") as pbar:
            for parquet_set in parquet_sets:
                try:
                    import pandas as pd

                    df_pandas = parquet_set.to_dataframe()
                    df = pl.from_pandas(df_pandas)

                    # Apply UF standardization on common UF columns, when present
                    uf_columns = [
                        col
                        for col in df.columns
                        if any(pattern in col.upper() for pattern in ["UF", "SG_UF"])
                    ]
                    if uf_columns:
                        df = apply_uf_mapping_polars(df, uf_columns)

                    combined_dfs.append(df)
                except Exception as exc:
                    logger.error(f"Failed to process SIM parquet set {parquet_set}: {exc}")
                finally:
                    pbar.update(1)

        if not combined_dfs:
            logger.warning(f"No valid SIM data found for {group}")
            return pl.DataFrame()

        logger.info(f"Combining {len(combined_dfs)} SIM DataFrames for {group}")
        combined = pl.concat(combined_dfs, how="diagonal")

        logger.info(
            f"✅ SIM {group}: {len(combined)} records loaded, "
            f"{len(combined.columns)} columns"
        )
        return combined

    def load_dataframe(self, group: str = "CID10") -> pl.DataFrame:
        """Load and return SIM data for a specific group as a Polars DataFrame."""
        group_upper = group.upper()
        return self._load_as_polars(group_upper)

    # ------------------------------------------------------------------
    # FILTERING
    # ------------------------------------------------------------------
    def filter(
        self,
        df: Optional[pl.DataFrame] = None,
        uf: Optional[str] = None,
        municipio: Optional[str] = None,
        sexo: Optional[str] = None,
        causa_basica: Optional[str] = None,
        ano_obito: Optional[int] = None,
    ) -> pl.DataFrame:
        """
        Apply common filters to a SIM DataFrame.

        Parameters are best-effort: if the underlying column is not present,
        the corresponding filter is silently ignored.
        """
        if df is None:
            raise ValueError("É necessário fornecer um DataFrame para filtragem.")

        conditions: List[pl.Expr] = []

        def resolve_column(options: List[str]) -> Optional[str]:
            for candidate in options:
                if candidate in df.columns:
                    return candidate
            return None

        # UF filter – try to use UF-like columns
        uf_col = resolve_column(["UF", "UF_RES", "UFRES", "CODUFRES"])
        if uf and uf_col:
            conditions.append(pl.col(uf_col) == uf)

        # Municipality filter (by code or name substring)
        municipio_col = resolve_column(["CODMUNRES", "CODMUN_RESI", "MUN_RES", "MUNRES"])
        if municipio and municipio_col:
            conditions.append(
                pl.col(municipio_col)
                .cast(pl.Utf8)
                .str.contains(municipio, literal=True, strict=False)
            )

        # Sex filter
        sexo_col = resolve_column(["SEXO", "CS_SEXO"])
        if sexo and sexo_col:
            conditions.append(pl.col(sexo_col) == sexo)

        # Basic cause of death (CID code)
        causa_col = resolve_column(["CAUSABAS", "CAUSABASO"])
        if causa_basica and causa_col:
            conditions.append(pl.col(causa_col) == causa_basica)

        # Year of death – either explicit year column or derived from date
        ano_col = resolve_column(["ANOOBITO", "ANO_OBITO"])
        if ano_obito and ano_col:
            conditions.append(pl.col(ano_col) == ano_obito)
        elif ano_obito and "DTOBITO" in df.columns:
            # DTOBITO usually encodes date of death as YYYYMMDD or similar
            try:
                conditions.append(
                    pl.col("DTOBITO")
                    .cast(pl.Utf8)
                    .str.slice(0, 4)
                    .cast(pl.Int64)
                    == ano_obito
                )
            except Exception as exc:
                logger.warning(f"Failed to derive year from DTOBITO: {exc}")

        if not conditions:
            return df

        combined = conditions[0]
        for condition in conditions[1:]:
            combined = combined & condition

        return df.filter(combined)

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    def summary(
        self,
        df: pl.DataFrame,
        by: str = "CAUSABAS",
        metric: Literal["count", "mean", "sum"] = "count",
    ) -> pl.DataFrame:
        """Generate a summary table grouped by a column."""
        if by not in df.columns:
            raise ValueError(f"A coluna '{by}' não existe no DataFrame.")

        if metric == "count":
            return df.groupby(by).count().sort(by)
        if metric == "mean":
            return df.groupby(by).mean().sort(by)
        if metric == "sum":
            return df.groupby(by).sum().sort(by)
        raise ValueError("metric deve ser 'count', 'mean' ou 'sum'.")

    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------
    def export(
        self,
        df: pl.DataFrame,
        format: Literal["csv", "sqlite", "parquet"] = "csv",
        name: str = "sim_output",
    ) -> Optional[Path]:
        """Export a SIM DataFrame and return the generated path."""
        if df is None or len(df) == 0:
            logger.warning(f"Nenhum dado disponível para exportar: {name}")
            return None

        output_dir = Path(self.output_path)
        final_stem = name
        final_path = output_dir / f"{final_stem}.{format}"

        if format == "csv":
            df.write_csv(final_path)
        elif format == "parquet":
            df.write_parquet(final_path)
        elif format == "sqlite":
            import sqlite3

            db_path = output_dir / f"{final_stem}.db"
            con = sqlite3.connect(db_path)
            df.to_pandas().to_sql(name=final_stem, con=con, if_exists="replace", index=False)
            con.close()
        else:
            raise ValueError("Formato inválido. Escolha entre 'csv', 'sqlite' ou 'parquet'.")

        logger.info(f"Exported SIM dataset -> {final_path}")
        return final_path

    # ------------------------------------------------------------------
    # METADATA
    # ------------------------------------------------------------------
    def describe_fields(self, group: str = "CID10") -> List[str]:
        """List all columns available for a given SIM group."""
        df = self.load_dataframe(group)
        return df.columns

