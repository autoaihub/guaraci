"""Generic spec-driven DATASUS data source (phase 5).

SIH/SIM/SINAN keep their bespoke classes (they carry the legacy PySUS
path). The eleven systems added in phase 5 are FTP-only — there is no
legacy to preserve — so a single :class:`FtpDataSource`, parametrised by a
:class:`~guaraci.datasus.ftp.specs.SystemSpec`, covers all of them. Each
source is then just ``FtpDataSource(specs.SINASC)`` etc.

Contract matches the other datasources closely enough that the
``PysusDownloadSource`` service adapter drives it unchanged: ``download``
returns ``{successful_downloads, failed_downloads, total_files}`` and
populates ``self.data`` (group -> list of parquet paths) for raw
materialisation and export.
"""

from __future__ import annotations

import datetime
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import polars as pl
from loguru import logger

from guaraci.core.datasource import DataSource
from guaraci.datasus.ftp import generic_backend
from guaraci.datasus.ftp.specs import SystemSpec
from guaraci.utils.mapping import apply_uf_mapping_polars

_UF_CANDIDATES = ["UF", "SG_UF", "SG_UF_NOT", "UF_RES", "UFRES", "CODUFRES", "UF_ZI"]
_MUN_CANDIDATES = ["CODMUNRES", "CODMUN_RESI", "MUN_RES", "MUNRES", "MUNIC_RES", "CODMUNNASC"]
_SEXO_CANDIDATES = ["SEXO", "CS_SEXO", "SEXOBITO"]


class FtpDataSource(DataSource):
    """A DATASUS source backed entirely by the direct-FTP engine."""

    def __init__(self, spec: SystemSpec, output_path: Optional[str] = None) -> None:
        super().__init__(name=spec.name, output_path=output_path)
        self.spec = spec
        self.data: Dict[str, List[Any]] = defaultdict(list)

    # -- collection -----------------------------------------------------------

    def download(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        years = self._resolve_years(start_year, end_year)
        norm_groups = self._normalize_groups(groups)
        norm_states = list(states) if (states and self.spec.has_state) else None

        logger.info(
            f"Starting {self.spec.name} FTP download: {years[0]}-{years[-1]} "
            f"(groups={norm_groups}, states={norm_states})"
        )

        result = generic_backend.download(
            self.spec,
            years=years,
            groups=norm_groups,
            states=norm_states,
            cache_dir=self._ftp_cache_dir(),
            progress_callback=progress_callback,
        )

        paths_by_group: Dict[str, List[str]] = result.pop("paths_by_group", {})
        for group, paths in paths_by_group.items():
            self.data[group].extend(paths)
        return result

    def discover(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        years = self._resolve_years(start_year, end_year)
        norm_groups = self._normalize_groups(groups)
        norm_states = list(states) if (states and self.spec.has_state) else None

        summary = generic_backend.discover_summary(
            self.spec,
            years=years,
            groups=norm_groups,
            states=norm_states,
        )
        # Anchor the echoed filters to the request's own range.
        filters: Dict[str, Any] = {
            "start_year": years[0],
            "end_year": years[-1],
            "groups": norm_groups,
        }
        if self.spec.has_state:
            filters["states"] = norm_states
        summary["filters"] = filters
        return summary

    # -- helpers --------------------------------------------------------------

    def _resolve_years(self, start_year: int, end_year: int) -> List[int]:
        current_year = datetime.datetime.now().year
        if end_year >= current_year:
            logger.warning(f"End year {end_year} adjusted to {current_year - 1}")
            end_year = current_year - 1
        if start_year < self.spec.min_year:
            logger.warning(
                f"Start year {start_year} is before {self.spec.name} data begins "
                f"({self.spec.min_year}); clamping."
            )
            start_year = self.spec.min_year
        if start_year > end_year:
            raise ValueError(
                f"Start year ({start_year}) cannot be greater than end year ({end_year})"
            )
        return list(range(start_year, end_year + 1))

    def _normalize_groups(self, groups: Optional[List[str]]) -> Optional[List[str]]:
        spec = self.spec
        if not spec.groups:
            return None  # single implicit group -> backend lists the flat roots
        if not groups:
            return list(spec.default_groups) or list(spec.groups)
        unknown = {g for g in groups if g.upper() not in spec.groups}
        if unknown:
            raise ValueError(
                f"Unknown {spec.name} group(s): {', '.join(sorted(unknown))}. "
                f"Valid: {', '.join(spec.groups)}"
            )
        return [g.upper() for g in groups]

    def _ftp_cache_dir(self) -> Path:
        explicit = os.environ.get("GUARACI_FTP_CACHE_DIR")
        path = Path(explicit) if explicit else Path(self.output_path) / ".cache_ftp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- loading / export -----------------------------------------------------

    def load_dataframe(self, group: Optional[str] = None) -> pl.DataFrame:
        if group is not None:
            paths = list(self.data.get(group.upper(), []))
        else:
            paths = [p for items in self.data.values() for p in items]
        if not paths:
            logger.warning(f"No data found for {self.spec.name} (group={group})")
            return pl.DataFrame()

        frames: List[pl.DataFrame] = []
        for filepath in paths:
            try:
                df = pl.read_parquet(filepath)
                uf_columns = [c for c in df.columns if any(p in c.upper() for p in ["UF", "SG_UF"])]
                if uf_columns:
                    df = apply_uf_mapping_polars(df, uf_columns)
                frames.append(df)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to read parquet {filepath}: {exc}")
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal")

    def filter(
        self,
        df: Optional[pl.DataFrame] = None,
        uf: Optional[str] = None,
        municipio: Optional[str] = None,
        sexo: Optional[str] = None,
        **_ignored: Any,
    ) -> pl.DataFrame:
        """Best-effort generic filter across heterogeneous DATASUS schemas.

        Resolves UF / municipality / sex columns from a candidate list;
        filters the source does not have columns for are silently skipped.
        Source-specific refinements are intentionally out of scope here.
        """
        if df is None:
            raise ValueError("A DataFrame is required for filtering.")

        def resolve(options: List[str]) -> Optional[str]:
            for candidate in options:
                if candidate in df.columns:
                    return candidate
            return None

        conditions: List[pl.Expr] = []
        uf_col = resolve(_UF_CANDIDATES)
        if uf and uf_col:
            conditions.append(pl.col(uf_col).cast(pl.Utf8) == str(uf))
        mun_col = resolve(_MUN_CANDIDATES)
        if municipio and mun_col:
            conditions.append(
                pl.col(mun_col).cast(pl.Utf8).str.contains(str(municipio), literal=True, strict=False)
            )
        sexo_col = resolve(_SEXO_CANDIDATES)
        if sexo and sexo_col:
            conditions.append(pl.col(sexo_col).cast(pl.Utf8) == str(sexo))

        if not conditions:
            return df
        combined = conditions[0]
        for condition in conditions[1:]:
            combined = combined & condition
        return df.filter(combined)

    def export(
        self,
        df: pl.DataFrame,
        format: str = "csv",
        name: Optional[str] = None,
    ) -> Optional[Path]:
        if df is None or len(df) == 0:
            return None
        output_dir = Path(self.output_path)
        name = name or f"{self.spec.name}_output"
        final_path = output_dir / f"{name}.{format}"
        if format == "csv":
            df.write_csv(final_path)
        elif format == "parquet":
            df.write_parquet(final_path)
        elif format == "sqlite":
            import sqlite3

            con = sqlite3.connect(output_dir / f"{name}.db")
            df.to_pandas().to_sql(name=name, con=con, if_exists="replace", index=False)
            con.close()
            return output_dir / f"{name}.db"
        else:
            raise ValueError(f"Unsupported export format: {format}")
        return final_path

    def describe_fields(self, group: Optional[str] = None) -> List[str]:
        return self.load_dataframe(group).columns

    def __repr__(self) -> str:
        return f"FtpDataSource(spec={self.spec.name!r})"
