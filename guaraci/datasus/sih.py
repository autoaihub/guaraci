"""
Guaraci DATASUS SIH Integration
===============================

Module for downloading, processing and exporting SIH (Hospital Information
System) data over the direct anonymous FTP connection to ftp.datasus.gov.br.
"""

from __future__ import annotations

import datetime
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

import polars as pl
from loguru import logger

from guaraci.core.datasource import DataSource
from guaraci.datasus import filtering, frames
from guaraci.utils.mapping import apply_uf_mapping_polars


class SihDataSource(DataSource):
    """
    SIH data source backed by the direct DATASUS FTP layer.
    """

    ALL_GROUPS: List[str] = ["RD", "RJ", "ER", "SP", "CH", "CM"]
    #: O SIH codifica o sexo como 1 (masculino) e 3 (feminino), herança do
    #: layout antigo da AIH; a interface expõe M/F. Sem a tradução, --sexo M
    #: não casava nada.
    SEXO_CODES: Dict[str, str] = {"M": "1", "F": "3", "I": "0"}

    DEFAULT_GROUPS: List[str] = ALL_GROUPS.copy()

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sih", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)

    def download(
        self,
        start_year: int,
        end_year: int,
        groups: Optional[List[str]] = None,
        states: Optional[List[str]] = None,
        months: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
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

        logger.info(f"Starting SIH download: {start_year}-{end_year}")

        return self._download_via_ftp(
            years=years,
            groups=normalized_groups,
            states=states,
            months=month_values,
            progress_callback=progress_callback,
        )

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

        return self._discover_via_ftp(
            start_year=start_year,
            end_year=end_year,
            years=years,
            groups=selected_groups,
            states=states,
            months=selected_months,
        )

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

    def scan_dataframe(self, group: str = "RD") -> pl.LazyFrame:
        """Plano lazy sobre os parquets baixados do grupo.

        Nada é lido aqui: quem consome decide entre materializar
        (:meth:`load_dataframe`) ou escrever em streaming (:meth:`export`).
        """
        group = group.upper()
        if group not in self.data:
            raise ValueError(f"Group {group} not found. Run download() first.")
        return frames.scan_parquet_group(self.data[group], label=f"SIH {group}")

    def _load_as_polars(self, group: str) -> pl.DataFrame:
        return self.scan_dataframe(group).collect()

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

        # UF_ZI é o código do gestor (120000 para o Acre), não a sigla: sem a
        # leitura por prefixo de `uf_expr`, --uf SP não casava com nada.
        pedidos = [
            (uf, ["UF_ZI", "UF", "CODUF", "MUNIC_RES"], filtering.uf_expr),
            (
                municipio,
                ["MUNIC_RES", "MUNIC_RESID", "MUNIC_MOV"],
                filtering.contains_expr,
            ),
            (
                sexo,
                ["SEXO", "CS_SEXO"],
                lambda frame, col, val: filtering.coded_equality_expr(
                    frame, col, val, self.SEXO_CODES
                ),
            ),
            (ano, ["ANO_CMPT", "ANO"], filtering.equality_expr),
            (mes, ["MES_CMPT", "MES"], filtering.equality_expr),
            (
                cid,
                ["DIAG_PRINC"],
                lambda frame, col, val: pl.col(col)
                .cast(pl.Utf8, strict=False)
                .str.strip_chars()
                .str.to_uppercase()
                .str.starts_with(str(val).strip().upper()),
            ),
        ]
        for valor, candidatos, build_expr in pedidos:
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                continue
            coluna = filtering.resolve_filter_column(df, candidatos)
            if coluna is None:
                continue
            conditions.append(build_expr(df, coluna, valor))

        combined = filtering.combine(conditions)
        if combined is None:
            return df
        return df.filter(combined)

    def summary(self, df: pl.DataFrame, by: str = "UF_ZI", metric: Literal["count", "mean", "sum"] = "count") -> pl.DataFrame:
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
        name: str = "sih_output",
    ) -> Optional[Path]:
        """Escreve o conjunto, em streaming quando recebe um plano lazy."""
        if df is None or frames.is_empty(df):
            return None
        return frames.write_frame(
            df, output_dir=Path(self.output_path), stem=name, format=format
        )

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
