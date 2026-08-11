"""
Guaraci DATASUS SIH Integration
===============================

Module for downloading, processing and exporting SIH (Hospital Information
System) data via PySUS 2.x.
"""

from __future__ import annotations

import asyncio
import datetime
import os
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
    from pysus.api.ftp.client import FTP as PySUSFtpClient
    from pysus.api.ftp.databases import SIH as PySUSFtpSIH
    from pysus.api.ftp.models import File as PySUSFtpFile
    PYSUS_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - handled at runtime
    import logging
    logging.getLogger(__name__).warning(f"PySUS não está disponível ou falhou ao importar: {exc}")
    PYSUS_AVAILABLE = False
    PySUS = None  # type: ignore[assignment]
    PySUSFtpClient = None  # type: ignore[assignment]
    PySUSFtpSIH = None  # type: ignore[assignment]
    PySUSFtpFile = None  # type: ignore[assignment]


# --- Backend selection -------------------------------------------------------
#
# Phase 2 of docs/PLANO_DATASUS_FTP_DIRETO.md: SihDataSource picks between
# the legacy PySUS path and the new direct-FTP layer based on the env var
# ``GUARACI_DATASUS_BACKEND``. The shared selector lives in
# ``guaraci.datasus.backend`` (phase 3 generalised it to SIM/SINAN too).

from guaraci.datasus.backend import (  # noqa: E402
    BACKEND_FTP as _BACKEND_FTP,
    BACKEND_PYSUS as _BACKEND_PYSUS,
    get_datasus_backend as _get_datasus_backend,
)


class SihDataSource(DataSource):
    """
    SIH data source backed by PySUS 2.x.
    """

    ALL_GROUPS: List[str] = ["RD", "RJ", "ER", "SP", "CH", "CM"]
    DEFAULT_GROUPS: List[str] = ALL_GROUPS.copy()

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
        backend = _get_datasus_backend()

        current_year = datetime.datetime.now().year
        if end_year > current_year:
            logger.warning(f"End year {end_year} is in the future; adjusted to {current_year}")
            end_year = current_year
        elif end_year == current_year:
            logger.info(
                f"Collecting current year ({current_year}); SIH data may be partial "
                f"due to DATASUS publication lag"
            )

        if start_year > end_year:
            raise ValueError(f"Start year ({start_year}) cannot be greater than end year ({end_year})")

        years = list(range(start_year, end_year + 1))

        if groups is None or not groups:
            normalized_groups = self.ALL_GROUPS.copy()
        else:
            unknown = {g for g in groups if g.upper() not in self.ALL_GROUPS}
            if unknown:
                raise ValueError(f"Unknown SIH group(s): {', '.join(sorted(unknown))}")
            normalized_groups = [g.upper() for g in groups]

        month_values: Optional[List[int]] = None
        if months:
            invalid = [m for m in months if m < 1 or m > 12]
            if invalid:
                raise ValueError(f"Invalid month values: {invalid}. Expected 1–12.")
            month_values = months

        logger.info(f"Starting SIH download: {start_year}-{end_year} (backend={backend})")

        if backend == _BACKEND_FTP:
            return self._download_via_ftp(
                years=years,
                groups=normalized_groups,
                states=states,
                months=month_values,
                progress_callback=progress_callback,
            )

        return self._download_via_pysus(
            years=years,
            groups=normalized_groups,
            states=states,
            month_values=month_values,
            progress_callback=progress_callback,
        )

    def _download_via_pysus(
        self,
        *,
        years: List[int],
        groups: List[str],
        states: Optional[List[str]],
        month_values: Optional[List[int]],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for the 'pysus' backend.")

        async def _discover_files() -> List[Any]:
            if PySUSFtpClient is None or PySUSFtpSIH is None or PySUSFtpFile is None:
                raise ImportError("PySUS FTP support is required for SIH downloads.")

            ftp_client = PySUSFtpClient()
            await ftp_client.connect()
            try:
                dataset = PySUSFtpSIH(client=ftp_client)
                discovered = await dataset._fetch_content()
            finally:
                await ftp_client.close()

            selected_groups = set(groups)
            selected_states = {s.upper() for s in states} if states else None
            selected_months = set(month_values) if month_values else None

            files_to_download = []
            for file_record in discovered:
                if not isinstance(file_record, PySUSFtpFile):
                    continue
                group_obj = getattr(file_record, "group", None)
                group_name = str(getattr(group_obj, "name", "") or "").upper()
                state_name = str(getattr(file_record, "state", "") or "").upper()
                year_value = getattr(file_record, "year", None)
                month_value = getattr(file_record, "month", None)

                if group_name not in selected_groups:
                    continue
                if selected_states is not None and state_name not in selected_states:
                    continue
                if year_value not in years:
                    continue
                if selected_months is not None and month_value not in selected_months:
                    continue
                files_to_download.append(file_record)

            files_to_download.sort(
                key=lambda item: (
                    str(getattr(getattr(item, "group", None), "name", "") or ""),
                    str(getattr(item, "state", "") or ""),
                    int(getattr(item, "year", 0) or 0),
                    int(getattr(item, "month", 0) or 0),
                    str(getattr(item, "basename", item)),
                )
            )
            return files_to_download

        async def _fetch():
            successful = 0
            failed_downloads = []
            
            files_to_download = await _discover_files()

            async with PySUS() as client:
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
                        downloaded = await client.download_to_parquet(file_record)
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

    def _download_via_ftp(
        self,
        *,
        years: List[int],
        groups: List[str],
        states: Optional[List[str]],
        months: Optional[List[int]],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        """Direct FTP backend (phase 2 of PLANO_DATASUS_FTP_DIRETO)."""
        from guaraci.datasus.ftp import sih_backend as ftp_sih

        cache_dir = self._ftp_cache_dir()
        try:
            result = ftp_sih.download_sih(
                years=years,
                groups=groups,
                states=states,
                months=months,
                cache_dir=cache_dir,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.error(f"SIH FTP download process failed: {exc}")
            raise

        paths_by_group: Dict[str, List[str]] = result.pop("paths_by_group", {})
        for group, paths in paths_by_group.items():
            self.data[group].extend(paths)
        return result

    def _ftp_cache_dir(self) -> Path:
        """Where the FTP backend stores .dbc downloads and the .parquet output.

        Honours ``GUARACI_FTP_CACHE_DIR`` when set so tests and users can
        point the cache at a tmp directory without touching the user-facing
        export folder.
        """
        explicit = os.environ.get("GUARACI_FTP_CACHE_DIR")
        path = Path(explicit) if explicit else Path(self.output_path) / ".cache_ftp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def discover(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        months: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        backend = _get_datasus_backend()

        current_year = datetime.datetime.now().year
        if end_year > current_year:
            end_year = current_year
        if start_year > end_year:
            raise ValueError(f"Start year ({start_year}) cannot be greater than end year ({end_year})")

        selected_groups = groups or self.ALL_GROUPS.copy()
        selected_groups = [g.upper() for g in selected_groups]
        unknown = {g for g in selected_groups if g not in self.ALL_GROUPS}
        if unknown:
            raise ValueError(f"Unknown SIH group(s): {', '.join(sorted(unknown))}")

        selected_months: Optional[List[int]] = None
        if months:
            invalid = [m for m in months if m < 1 or m > 12]
            if invalid:
                raise ValueError(f"Invalid month values: {invalid}. Expected 1–12.")
            selected_months = months

        years = list(range(start_year, end_year + 1))

        if backend == _BACKEND_FTP:
            return self._discover_via_ftp(
                start_year=start_year,
                end_year=end_year,
                years=years,
                groups=selected_groups,
                states=states,
                months=selected_months,
            )

        return self._discover_via_pysus(
            start_year=start_year,
            end_year=end_year,
            years=years,
            selected_groups=selected_groups,
            states=states,
            selected_months=selected_months,
        )

    def _discover_via_pysus(
        self,
        *,
        start_year: int,
        end_year: int,
        years: List[int],
        selected_groups: List[str],
        states: Optional[List[str]],
        selected_months: Optional[List[int]],
    ) -> Dict[str, Any]:
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for the 'pysus' backend.")

        async def _discover() -> List[Any]:
            if PySUSFtpClient is None or PySUSFtpSIH is None or PySUSFtpFile is None:
                raise ImportError("PySUS FTP support is required for SIH discovery.")
            ftp_client = PySUSFtpClient()
            await ftp_client.connect()
            try:
                dataset = PySUSFtpSIH(client=ftp_client)
                discovered = await dataset._fetch_content()
            finally:
                await ftp_client.close()

            state_filter = {s.upper() for s in states} if states else None
            month_filter = set(selected_months) if selected_months else None
            group_filter = set(selected_groups)
            selected: List[Any] = []
            for file_record in discovered:
                if not isinstance(file_record, PySUSFtpFile):
                    continue
                group_name = str(getattr(getattr(file_record, "group", None), "name", "") or "").upper()
                state_name = str(getattr(file_record, "state", "") or "").upper()
                if group_name not in group_filter:
                    continue
                if state_filter is not None and state_name not in state_filter:
                    continue
                if getattr(file_record, "year", None) not in years:
                    continue
                if month_filter is not None and getattr(file_record, "month", None) not in month_filter:
                    continue
                selected.append(file_record)
            selected.sort(
                key=lambda item: (
                    str(getattr(getattr(item, "group", None), "name", "") or ""),
                    str(getattr(item, "state", "") or ""),
                    int(getattr(item, "year", 0) or 0),
                    int(getattr(item, "month", 0) or 0),
                    str(getattr(item, "basename", item)),
                )
            )
            return selected

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                files = loop.run_until_complete(_discover())
            else:
                files = asyncio.run(_discover())
        except Exception as exc:
            logger.error(f"SIH discovery failed: {exc}")
            raise

        by_group: Dict[str, int] = defaultdict(int)
        by_state: Dict[str, int] = defaultdict(int)
        total_size = 0
        sample: List[Dict[str, Any]] = []
        for file_record in files:
            group_name = str(getattr(getattr(file_record, "group", None), "name", "") or "")
            state_name = str(getattr(file_record, "state", "") or "")
            by_group[group_name] += 1
            by_state[state_name] += 1
            total_size += int(getattr(file_record, "size", 0) or 0)
            if len(sample) < 10:
                sample.append(
                    {
                        "name": str(getattr(file_record, "basename", file_record)),
                        "group": group_name,
                        "state": state_name,
                        "year": getattr(file_record, "year", None),
                        "month": getattr(file_record, "month", None),
                        "size_bytes": int(getattr(file_record, "size", 0) or 0),
                    }
                )

        return {
            "source": "sih",
            "documents_found": len(files),
            "total_size_bytes": total_size,
            "by_group": dict(sorted(by_group.items())),
            "by_state": dict(sorted(by_state.items())),
            "sample": sample,
            "filters": {
                "start_year": start_year,
                "end_year": end_year,
                "groups": selected_groups,
                "states": states,
                "months": selected_months,
            },
        }

    def _discover_via_ftp(
        self,
        *,
        start_year: int,
        end_year: int,
        years: List[int],
        groups: List[str],
        states: Optional[List[str]],
        months: Optional[List[int]],
    ) -> Dict[str, Any]:
        """Direct FTP backend preflight (phase 2 of PLANO_DATASUS_FTP_DIRETO)."""
        from guaraci.datasus.ftp import sih_backend as ftp_sih

        try:
            payload = ftp_sih.discover_sih_summary(
                years=years,
                groups=groups,
                states=states,
                months=months,
            )
        except Exception as exc:
            logger.error(f"SIH FTP discovery failed: {exc}")
            raise

        # Anchor the start/end_year to the request, not just the matches.
        payload["filters"] = {
            "start_year": start_year,
            "end_year": end_year,
            "groups": groups,
            "states": states,
            "months": months,
        }
        return payload

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
        if metric == "count": return df.group_by(by).len().sort(by)
        if metric == "mean": return df.group_by(by).mean().sort(by)
        if metric == "sum": return df.group_by(by).sum().sort(by)
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

    def apply_column_map(
        self,
        df: pl.DataFrame,
        column_map: Optional[Dict[str, str]] = None,
    ) -> pl.DataFrame:
        """Instance method shortcut for apply_sih_column_map."""
        return apply_sih_column_map(df, column_map)

    def describe_fields(self, group: str = "RD") -> List[str]:
        return self.load_dataframe(group).columns


DEFAULT_SIH_RD_COLUMN_MAP: Dict[str, str] = {
    "N_AIH": "numero_aih",
    "DT_INTER": "data_internacao",
    "DT_SAIDA": "data_saida",
    "MUNIC_RES": "municipio_residencia",
    "MUNIC_MOV": "municipio_movimentacao",
    "DIAG_PRINC": "diagnostico_principal",
    "DIAG_SECUN": "diagnostico_secundario",
    "COBRANCA": "motivo_cobranca",
    "SEXO": "sexo",
    "IDADE": "idade",
    "UTI_MES_TO": "dias_uti_mes",
    "MORTE": "obito",
    "VAL_TOT": "valor_total",
    "UF_ZI": "uf_gestao",
}


def apply_sih_column_map(
    df: pl.DataFrame,
    column_map: Optional[Dict[str, str]] = None,
) -> pl.DataFrame:
    """Apply a standardized column mapping to a SIH Polars DataFrame.

    Defaults to DEFAULT_SIH_RD_COLUMN_MAP. Only renames columns that exist
    in `df`; unmapped or missing columns are left untouched.
    """
    mapping = column_map if column_map is not None else DEFAULT_SIH_RD_COLUMN_MAP
    rename_dict = {col: target for col, target in mapping.items() if col in df.columns}
    return df.rename(rename_dict) if rename_dict else df
