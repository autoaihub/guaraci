"""
Guaraci DATASUS SIM Integration
===============================

Module for downloading, processing and exporting SIM (Mortality Information
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
from guaraci.datasus import filtering, frames
from guaraci.datasus.backend import (
    BACKEND_FTP as _BACKEND_FTP,
    get_datasus_backend as _get_datasus_backend,
)
from guaraci.utils.mapping import apply_uf_mapping_polars

try:
    import pysus
    from pysus.api.client import PySUS
    PYSUS_AVAILABLE = True
except ImportError as exc:
    import logging
    logging.getLogger(__name__).warning(f"PySUS não está disponível ou falhou ao importar: {exc}")
    PYSUS_AVAILABLE = False


class SimDataSource(DataSource):
    """
    SIM data source backed by PySUS 2.x.
    """

    #: O SIM guarda o sexo como código (1 masculino, 2 feminino, 0 ignorado),
    #: enquanto a interface expõe M/F. Sem a tradução, --sexo M não casava nada.
    SEXO_CODES: Dict[str, str] = {"M": "1", "F": "2", "I": "0"}

    DEFAULT_GROUPS: List[str] = ["CID10"]
    ALL_GROUPS: List[str] = ["CID10", "CID9"]

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sim", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)

        if not PYSUS_AVAILABLE:
            logger.warning(
                "PySUS is not installed. SIM functionality will be unavailable. "
                "Install with: pip install 'guaraci[datasus]'"
            )

    @property
    def sim(self):
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for SIM functionality.")
        return True

    def download(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        backend = _get_datasus_backend()

        current_year = datetime.datetime.now().year
        if end_year > current_year:
            logger.warning(f"End year {end_year} is in the future; adjusted to {current_year}")
            end_year = current_year
        elif end_year == current_year:
            logger.info(
                f"Collecting current year ({current_year}); SIM data may be partial "
                f"due to DATASUS publication lag"
            )

        if start_year > end_year:
            raise ValueError(f"Start year ({start_year}) cannot be greater than end year ({end_year})")

        years = list(range(start_year, end_year + 1))

        if groups is None or not groups:
            normalized_groups = self.DEFAULT_GROUPS.copy()
        else:
            unknown = {g for g in groups if g.upper() not in self.ALL_GROUPS}
            if unknown:
                raise ValueError(f"Unknown SIM group(s): {', '.join(sorted(unknown))}")
            normalized_groups = [g.upper() for g in groups]

        logger.info(f"Starting SIM download: {start_year}-{end_year} (backend={backend})")

        if backend == _BACKEND_FTP:
            return self._download_via_ftp(
                years=years,
                groups=normalized_groups,
                states=states,
                progress_callback=progress_callback,
            )

        return self._download_via_pysus(
            years=years,
            groups=normalized_groups,
            states=states,
            progress_callback=progress_callback,
        )

    def _download_via_pysus(
        self,
        *,
        years: List[int],
        groups: List[str],
        states: Optional[List[str]],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for the 'pysus' backend.")

        async def _fetch():
            successful = 0
            failed_downloads = []

            async with PySUS() as client:
                files_to_download = []
                for g in groups:
                    _states = states if states else [None]
                    for y in years:
                        for s in _states:
                            try:
                                res = await client.query(dataset="sim", group=g, state=s, year=y)
                                if res:
                                    files_to_download.extend(res)
                            except Exception as exc:
                                logger.error(f"Failed to query SIM {g} {s} {y}: {exc}")
                
                total_files = len(files_to_download)
                if total_files == 0:
                    logger.warning("No SIM files found for the specified criteria")
                    return {"successful_downloads": 0, "failed_downloads": [], "total_files": 0}

                logger.info(f"Found {total_files} SIM files to download")
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
            logger.error(f"SIM download process failed: {exc}")
            raise

    def _download_via_ftp(
        self,
        *,
        years: List[int],
        groups: List[str],
        states: Optional[List[str]],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        """Direct FTP backend (phase 3 of PLANO_DATASUS_FTP_DIRETO)."""
        from guaraci.datasus.ftp import sim_backend as ftp_sim

        cache_dir = self._ftp_cache_dir()
        try:
            result = ftp_sim.download_sim(
                years=years,
                groups=groups,
                states=states,
                cache_dir=cache_dir,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.error(f"SIM FTP download process failed: {exc}")
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

    def scan_dataframe(self, group: str = "CID10") -> pl.LazyFrame:
        """Plano lazy sobre os parquets baixados do grupo.

        Nada é lido aqui: quem consome decide entre materializar
        (:meth:`load_dataframe`) ou escrever em streaming (:meth:`export`).
        """
        group = group.upper()
        if group not in self.data:
            raise ValueError(f"Group {group} not found. Run download() first.")
        return frames.scan_parquet_group(self.data[group], label=f"SIM {group}")

    def _load_as_polars(self, group: str) -> pl.DataFrame:
        return self.scan_dataframe(group).collect()

    def load_dataframe(self, group: str = "CID10") -> pl.DataFrame:
        return self._load_as_polars(group.upper())

    def filter(
        self,
        df: Optional[pl.DataFrame] = None,
        uf: Optional[str] = None,
        municipio: Optional[str] = None,
        sexo: Optional[str] = None,
        causa_basica: Optional[str] = None,
        ano_obito: Optional[int] = None,
    ) -> pl.DataFrame:
        if df is None:
            raise ValueError("É necessário fornecer um DataFrame para filtragem.")

        conditions: List[pl.Expr] = []
        colunas = filtering.columns_of(df)

        # A UF não tem coluna própria nos arquivos do SIM: ela vive nos dois
        # primeiros dígitos do código de município, que `uf_expr` sabe ler.
        # Antes, nenhum dos candidatos existia e o filtro era descartado em
        # silêncio, devolvendo o país inteiro para quem pediu um estado.
        pedidos = [
            (uf, ["UF", "UF_RES", "UFRES", "CODUFRES", "CODMUNRES"], filtering.uf_expr),
            (
                municipio,
                ["CODMUNRES", "CODMUN_RESI", "MUN_RES", "MUNRES"],
                filtering.contains_expr,
            ),
            (
                sexo,
                ["SEXO", "CS_SEXO"],
                lambda frame, col, val: filtering.coded_equality_expr(
                    frame, col, val, self.SEXO_CODES
                ),
            ),
            (causa_basica, ["CAUSABAS", "CAUSABASO"], filtering.equality_expr),
        ]
        for valor, candidatos, build_expr in pedidos:
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                continue
            coluna = filtering.resolve_filter_column(df, candidatos)
            if coluna is None:
                continue
            conditions.append(build_expr(df, coluna, valor))

        if ano_obito:
            ano_col = filtering.resolve_filter_column(df, ["ANOOBITO", "ANO_OBITO"])
            if ano_col is not None:
                conditions.append(filtering.equality_expr(df, ano_col, ano_obito))
            elif "DTOBITO" in colunas:
                # DTOBITO é DDMMAAAA: o ano são os quatro últimos dígitos. O
                # recorte antigo pegava os quatro primeiros ("2205" para
                # 22/05/2020), de modo que o filtro por ano nunca casava.
                conditions.append(
                    pl.col("DTOBITO")
                    .cast(pl.Utf8, strict=False)
                    .str.strip_chars()
                    .str.zfill(8)
                    .str.slice(4, 4)
                    .cast(pl.Int64, strict=False)
                    == int(ano_obito)
                )

        combined = filtering.combine(conditions)
        if combined is None:
            return df
        return df.filter(combined)

    def summary(self, df: pl.DataFrame, by: str = "CAUSABAS", metric: Literal["count", "mean", "sum"] = "count") -> pl.DataFrame:
        if by not in df.columns:
            raise ValueError(f"A coluna '{by}' não existe no DataFrame.")
        if metric == "count": return df.group_by(by).len().sort(by)
        if metric == "mean": return df.group_by(by).mean().sort(by)
        if metric == "sum": return df.group_by(by).sum().sort(by)
        raise ValueError("metric deve ser 'count', 'mean' ou 'sum'.")

    def export(
        self,
        df: pl.DataFrame | pl.LazyFrame,
        format: Literal["csv", "sqlite", "parquet"] = "csv",
        name: str = "sim_output",
    ) -> Optional[Path]:
        """Escreve o conjunto, em streaming quando recebe um plano lazy."""
        if df is None or frames.is_empty(df):
            return None
        return frames.write_frame(
            df, output_dir=Path(self.output_path), stem=name, format=format
        )

    def describe_fields(self, group: str = "CID10") -> List[str]:
        return self.load_dataframe(group).columns
