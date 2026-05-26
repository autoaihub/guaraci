"""
Guaraci DATASUS SIH Integration
===============================

Module for downloading, processing and exporting SIH (Hospital Information
System) data via PySUS 2.x.
"""

from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

import polars as pl
from loguru import logger

from guaraci.core.datasource import DataSource
from guaraci.utils.mapping import apply_uf_mapping_polars

try:
    import pysus
    from pysus.api.client import PySUS
    PYSUS_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - handled at runtime
    import logging
    logging.getLogger(__name__).warning(f"PySUS não está disponível ou falhou ao importar: {exc}")
    PYSUS_AVAILABLE = False


class SihDataSource(DataSource):
    """
    SIH data source backed by PySUS 2.x.
    """

    DEFAULT_GROUPS: List[str] = ["RD"]
    ALL_GROUPS: List[str] = ["RD", "RJ", "ER", "SP", "CH", "CM"]

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sih", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)

        if not PYSUS_AVAILABLE:
            logger.warning(
                "PySUS is not installed. SIH functionality will be unavailable. "
                "Install with: pip install 'guaraci[datasus]'"
            )

    @property
    def sih(self):
        # Kept for compatibility, though unused in the new async logic
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for SIH functionality.")
        return True

    def download(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        months: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for SIH functionality.")

        current_year = datetime.datetime.now().year
        if end_year >= current_year:
            logger.warning(f"End year {end_year} adjusted to {current_year - 1}")
            end_year = current_year - 1

        if start_year > end_year:
            raise ValueError(f"Start year ({start_year}) cannot be greater than end year ({end_year})")

        years = list(range(start_year, end_year + 1))

        if groups is None or not groups:
            groups = self.DEFAULT_GROUPS.copy()
        else:
            unknown = {g for g in groups if g.upper() not in self.ALL_GROUPS}
            if unknown:
                raise ValueError(f"Unknown SIH group(s): {', '.join(sorted(unknown))}")
            groups = [g.upper() for g in groups]

        month_values: Optional[List[int]] = None
        if months:
            invalid = [m for m in months if m < 1 or m > 12]
            if invalid:
                raise ValueError(f"Invalid month values: {invalid}. Expected 1–12.")
            month_values = months

        logger.info(f"Starting SIH download: {start_year}-{end_year}")

        async def _fetch():
            successful = 0
            failed_downloads = []
            
            async with PySUS() as client:
                files_to_download = []
                for g in groups:
                    _states = states if states else [None]
                    _months = month_values if month_values else [None]
                    for y in years:
                        for m in _months:
                            for s in _states:
                                try:
                                    res = await client.query(dataset="sih", group=g, state=s, year=y, month=m)
                                    if res:
                                        files_to_download.extend(res)
                                except Exception as exc:
                                    logger.error(f"Failed to query SIH {g} {s} {y} {m}: {exc}")
                
                total_files = len(files_to_download)
                if total_files == 0:
                    logger.warning("No SIH files found for the specified criteria")
                    return {"successful_downloads": 0, "failed_downloads": [], "total_files": 0}

                logger.info(f"Found {total_files} SIH files to download")
                if progress_callback:
                    progress_callback(0, total_files)

                completed_downloads = 0
                for file_record in files_to_download:
                    try:
                        g_name = file_record.group.name if hasattr(file_record, "group") and file_record.group else "UNKNOWN"
                    except Exception:
                        g_name = "UNKNOWN"

                    try:
                        downloaded = await client.download(file_record)
                        self.data[g_name].append(str(downloaded.path))
                        successful += 1
                    except Exception as exc:
                        logger.error(f"Failed to download {file_record}: {exc}")
                        failed_downloads.append((g_name, str(file_record)))
                    finally:
                        completed_downloads += 1
                        if progress_callback:
                            progress_callback(completed_downloads, total_files)

                return {
                    "successful_downloads": successful,
                    "failed_downloads": failed_downloads,
                    "total_files": total_files,
                }

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
                
            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(_fetch())
            else:
                return asyncio.run(_fetch())
        except Exception as exc:
            logger.error(f"SIH download process failed: {exc}")
            raise

    def _load_as_polars(self, group: str) -> pl.DataFrame:
        if group not in self.data:
            raise ValueError(f"Group {group} not found. Run download() first.")

        parquet_sets = self.data[group]
        if not parquet_sets:
            logger.warning(f"No data found for SIH group {group}")
            return pl.DataFrame()

        combined_dfs: List[pl.DataFrame] = []
        total_files = len(parquet_sets)

        logger.info(f"Processing {total_files} parquet files for SIH {group}")
        from tqdm import tqdm

        with tqdm(total=total_files, desc=f"Loading SIH {group}", unit="file") as pbar:
            for filepath in parquet_sets:
                try:
                    df = pl.read_parquet(filepath)
                    uf_columns = [c for c in df.columns if any(p in c.upper() for p in ["UF", "CODUF"])]
                    if uf_columns:
                        df = apply_uf_mapping_polars(df, uf_columns)
                    combined_dfs.append(df)
                except Exception as exc:
                    logger.error(f"Failed to process SIH parquet file {filepath}: {exc}")
                finally:
                    pbar.update(1)

        if not combined_dfs:
            logger.warning(f"No valid SIH data found for {group}")
            return pl.DataFrame()

        combined = pl.concat(combined_dfs, how="diagonal")
        return combined

    def load_dataframe(self, group: str = "RD") -> pl.DataFrame:
        return self._load_as_polars(group.upper())

    def filter(
        self,
        df: Optional[pl.DataFrame] = None,
        uf: Optional[str] = None,
        municipio: Optional[str] = None,
        sexo: Optional[str] = None,
        ano: Optional[int] = None,
        mes: Optional[int] = None,
        cid: Optional[str] = None,
    ) -> pl.DataFrame:
        if df is None:
            raise ValueError("É necessário fornecer um DataFrame para filtragem.")

        conditions: List[pl.Expr] = []
        def resolve_column(options: List[str]) -> Optional[str]:
            for candidate in options:
                if candidate in df.columns:
                    return candidate
            return None

        uf_col = resolve_column(["UF_ZI", "UF", "CODUF"])
        if uf and uf_col:
            conditions.append(pl.col(uf_col) == uf)

        municipio_col = resolve_column(["MUNIC_RES", "MUNIC_RESID", "MUNIC_MOV"])
        if municipio and municipio_col:
            conditions.append(pl.col(municipio_col).cast(pl.Utf8).str.contains(municipio, literal=True, strict=False))

        sexo_col = resolve_column(["SEXO", "CS_SEXO"])
        if sexo and sexo_col:
            conditions.append(pl.col(sexo_col) == sexo)

        ano_col = resolve_column(["ANO_CMPT", "ANO"])
        if ano and ano_col:
            conditions.append(pl.col(ano_col) == ano)

        mes_col = resolve_column(["MES_CMPT", "MES"])
        if mes and mes_col:
            conditions.append(pl.col(mes_col) == mes)

        cid_col = resolve_column(["DIAG_PRINC"])
        if cid and cid_col:
            conditions.append(pl.col(cid_col).cast(pl.Utf8).str.starts_with(cid))

        if not conditions:
            return df

        combined = conditions[0]
        for condition in conditions[1:]:
            combined = combined & condition

        return df.filter(combined)

    def summary(self, df: pl.DataFrame, by: str = "UF_ZI", metric: Literal["count", "mean", "sum"] = "count") -> pl.DataFrame:
        if by not in df.columns:
            raise ValueError(f"A coluna '{by}' não existe no DataFrame.")
        if metric == "count": return df.groupby(by).count().sort(by)
        if metric == "mean": return df.groupby(by).mean().sort(by)
        if metric == "sum": return df.groupby(by).sum().sort(by)
        raise ValueError("metric deve ser 'count', 'mean' ou 'sum'.")

    def export(self, df: pl.DataFrame, format: Literal["csv", "sqlite", "parquet"] = "csv", name: str = "sih_output") -> Optional[Path]:
        if df is None or len(df) == 0:
            return None
        output_dir = Path(self.output_path)
        final_path = output_dir / f"{name}.{format}"
        if format == "csv": df.write_csv(final_path)
        elif format == "parquet": df.write_parquet(final_path)
        elif format == "sqlite":
            import sqlite3
            con = sqlite3.connect(output_dir / f"{name}.db")
            df.to_pandas().to_sql(name=name, con=con, if_exists="replace", index=False)
            con.close()
        return final_path

    def describe_fields(self, group: str = "RD") -> List[str]:
        return self.load_dataframe(group).columns
