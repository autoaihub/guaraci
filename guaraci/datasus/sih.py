"""
Guaraci DATASUS SIH Integration
===============================

Module for downloading, processing and exporting SIH (Hospital Information
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
from pyarrow import parquet  # noqa: F401  - kept for parity with other DATASUS modules

from guaraci.core.config import config
from guaraci.core.datasource import DataSource
from guaraci.utils.mapping import apply_uf_mapping_polars

try:
    # PySUS re-exports SIH from pysus.ftp.databases.sih
    from pysus import SIH  # type: ignore

    PYSUS_AVAILABLE = True
except ImportError:  # pragma: no cover - handled at runtime
    PYSUS_AVAILABLE = False
    SIH = None  # type: ignore


class SihDataSource(DataSource):
    """
    SIH data source backed by PySUS.

    Uses the AIH groups exposed by PySUS (RD, RJ, ER, SP, CH, CM) with
    filtering by UF, year and month.
    """

    # Common groups exposed by PySUS
    DEFAULT_GROUPS: List[str] = ["RD"]  # AIH reduzida
    ALL_GROUPS: List[str] = ["RD", "RJ", "ER", "SP", "CH", "CM"]

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sih", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)
        self._sih_instance = None

        if not PYSUS_AVAILABLE:
            logger.warning(
                "PySUS is not installed. SIH functionality will be unavailable. "
                "Install with: pip install 'guaraci[datasus]' or pip install pysus"
            )

    # ------------------------------------------------------------------
    # PySUS backend access
    # ------------------------------------------------------------------
    @property
    def sih(self):
        """Lazy loading of SIH instance."""
        if not PYSUS_AVAILABLE:
            raise ImportError(
                "PySUS is required for SIH functionality. "
                "Install with: pip install 'guaraci[datasus]' or pip install pysus"
            )

        if self._sih_instance is None:
            try:
                self._sih_instance = SIH().load()
                logger.debug("SIH instance loaded successfully")
            except Exception as exc:  # pragma: no cover - runtime protection
                logger.error(f"Failed to load SIH instance: {exc}")
                raise
        return self._sih_instance

    # ------------------------------------------------------------------
    # DOWNLOAD
    # ------------------------------------------------------------------
    def download(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        months: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Download SIH data with basic error handling.

        Parameters
        ----------
        start_year : int
            Starting year for data collection.
        end_year : int
            Ending year for data collection.
        groups : List[str], optional
            SIH groups (e.g., ['RD', 'RJ']). Defaults to reduced AIH (RD).
        states : List[str], optional
            Two-letter UF codes. If None, all available states are fetched.
        months : List[int], optional
            List of months (1–12). If None, all months are considered.
        progress_callback : Callable[[int, int], None], optional
            Callback invoked with (completed, total) as files finish downloading.

        Returns
        -------
        Dict[str, Any]
            Summary with total files, successful downloads and failures.
        """
        # Years validation
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
                raise ValueError(f"Unknown SIH group(s): {', '.join(sorted(unknown))}")
            groups = [g.upper() for g in groups]

        # Months validation (if provided)
        month_values: Optional[List[int]] = None
        if months:
            invalid = [m for m in months if m < 1 or m > 12]
            if invalid:
                raise ValueError(f"Invalid month values: {invalid}. Expected 1–12.")
            month_values = months

        logger.info(f"Starting SIH download: {start_year}-{end_year}")
        logger.info(f"Groups: {', '.join(groups)}")
        if states:
            logger.info(f"States: {', '.join(states)}")
        if month_values:
            logger.info(f"Months: {', '.join(str(m) for m in month_values)}")

        try:
            all_files = self.sih.get_files(
                group=groups,
                uf=states,
                year=years,
                month=month_values,
            )
            total_files = len(all_files)

            if total_files == 0:
                logger.warning("No SIH files found for the specified criteria")
                return {
                    "successful_downloads": 0,
                    "failed_downloads": [],
                    "total_files": 0,
                }

            logger.info(f"Found {total_files} SIH files to download")
            if progress_callback and total_files > 0:
                progress_callback(0, total_files)

            # Group files by raw group code (RD/RJ/...)
            grouped_files: Dict[str, List[Any]] = defaultdict(list)
            for file_obj in all_files:
                try:
                    group_code, _uf, _year, _month = self.sih.format(file_obj)
                    group_name = group_code
                except Exception:
                    group_name = "UNKNOWN"
                grouped_files[group_name].append(file_obj)

            failed_downloads: List[tuple[str, str]] = []
            completed_downloads = 0

            with ThreadPoolExecutor(max_workers=config.max_concurrent_downloads) as executor:
                for group_name, files in grouped_files.items():
                    logger.info(f"Downloading SIH {group_name}: {len(files)} files")

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
                f"SIH download completed: {successful_downloads}/{total_files} files successful"
            )

            if failed_downloads:
                logger.warning(f"Failed SIH downloads: {len(failed_downloads)}")
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
            logger.error(f"SIH download process failed: {exc}")
            raise

    def _download_file_safe(self, file_obj) -> Optional[Any]:
        """Safely download a single SIH file with retries."""
        for attempt in range(config.retry_attempts):
            try:
                downloaded = file_obj.download()
                return downloaded
            except Exception as exc:
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
        Load all downloaded files for a SIH group into a single Polars DataFrame.
        """
        if group not in self.data:
            raise ValueError(f"Group {group} not found. Run download() first.")

        parquet_sets = self.data[group]
        if not parquet_sets:
            logger.warning(f"No data found for SIH group {group}")
            return pl.DataFrame()

        combined_dfs: List[pl.DataFrame] = []
        total_files = len(parquet_sets)

        logger.info(f"Processing {total_files} parquet sets for SIH {group}")

        from tqdm import tqdm

        with tqdm(total=total_files, desc=f"Loading SIH {group}", unit="file") as pbar:
            for parquet_set in parquet_sets:
                try:
                    import pandas as pd

                    df_pandas = parquet_set.to_dataframe()
                    df = pl.from_pandas(df_pandas)

                    # UF standardization on UF-related columns, when present
                    uf_columns = [
                        col
                        for col in df.columns
                        if any(pattern in col.upper() for pattern in ["UF", "CODUF"])
                    ]
                    if uf_columns:
                        df = apply_uf_mapping_polars(df, uf_columns)

                    combined_dfs.append(df)
                except Exception as exc:
                    logger.error(f"Failed to process SIH parquet set {parquet_set}: {exc}")
                finally:
                    pbar.update(1)

        if not combined_dfs:
            logger.warning(f"No valid SIH data found for {group}")
            return pl.DataFrame()

        logger.info(f"Combining {len(combined_dfs)} SIH DataFrames for {group}")
        combined = pl.concat(combined_dfs, how="diagonal")

        logger.info(
            f"✅ SIH {group}: {len(combined)} records loaded, "
            f"{len(combined.columns)} columns"
        )
        return combined

    def load_dataframe(self, group: str = "RD") -> pl.DataFrame:
        """Load and return SIH data for a specific group as a Polars DataFrame."""
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
        ano: Optional[int] = None,
        mes: Optional[int] = None,
    ) -> pl.DataFrame:
        """
        Apply common filters to a SIH DataFrame.

        All filters are best-effort and skipped silently if the underlying
        column does not exist.
        """
        if df is None:
            raise ValueError("É necessário fornecer um DataFrame para filtragem.")

        conditions: List[pl.Expr] = []

        def resolve_column(options: List[str]) -> Optional[str]:
            for candidate in options:
                if candidate in df.columns:
                    return candidate
            return None

        # UF filter
        uf_col = resolve_column(["UF_ZI", "UF", "CODUF"])
        if uf and uf_col:
            conditions.append(pl.col(uf_col) == uf)

        # Municipality filter (residence or establishment)
        municipio_col = resolve_column(["MUNIC_RES", "MUNIC_RESID", "MUNIC_RES", "MUNIC_MOV"])
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

        # Year filter – commonly encoded in column "ANO_CMPT" or "ANO"
        ano_col = resolve_column(["ANO_CMPT", "ANO"])
        if ano and ano_col:
            conditions.append(pl.col(ano_col) == ano)

        # Month filter – commonly encoded in column "MES_CMPT" or "MES"
        mes_col = resolve_column(["MES_CMPT", "MES"])
        if mes and mes_col:
            conditions.append(pl.col(mes_col) == mes)

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
        by: str = "UF_ZI",
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
        name: str = "sih_output",
    ) -> Optional[Path]:
        """Export a SIH DataFrame and return the generated path."""
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

        logger.info(f"Exported SIH dataset -> {final_path}")
        return final_path

    # ------------------------------------------------------------------
    # METADATA
    # ------------------------------------------------------------------
    def describe_fields(self, group: str = "RD") -> List[str]:
        """List all columns available for a given SIH group."""
        df = self.load_dataframe(group)
        return df.columns

