"""
Guaraci SNIS Legacy BigQuery Integration
=======================================

Legacy integration for SNIS "Serie Historica" dataset via Base dos Dados (BigQuery).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd
import polars as pl
from loguru import logger

from guaraci.core.config import config
from guaraci.core.datasource import DataSource


class SnisLegacyBigQueryDataSource(DataSource):
    """Legacy SNIS data source backed by Base dos Dados (BigQuery)."""

    DEFAULT_TABLE = "basedosdados.br_mdr_snis.municipio_agua_esgoto"

    OUTPUT_COLUMNS: List[str] = [
        "id_municipio",
        "ano",
        "AG001",
        "AG001A",
        "AG006",
        "AG010",
        "AG018",
        "AG019",
        "AG024",
        "CO108",
        "CO109",
        "CO140",
        "CO164",
        "CS001",
        "CS026",
        "CS048",
        "ES001",
        "ES005",
        "ES006",
        "ES013",
        "ES014",
        "ES015",
        "ES026",
        "ESO26",
        "G06A",
        "G12A",
        "PMGIRS",
        "PO007",
        "PO028",
        "PO048",
        "POP_TOT",
        "POP_URB",
    ]

    INDICATOR_ALIASES: Dict[str, Sequence[str]] = {
        "AG001": ("AG001", "populacao_atendida_agua"),
        "AG001A": ("AG001A",),
        "AG006": ("AG006", "volume_agua_produzido"),
        "AG010": ("AG010", "volume_agua_consumido"),
        "AG018": ("AG018", "volume_agua_tratada_importado"),
        "AG019": ("AG019", "volume_agua_tratada_exportado"),
        "AG024": ("AG024", "volume_servico_agua"),
        "CO108": ("CO108",),
        "CO109": ("CO109",),
        "CO140": ("CO140",),
        "CO164": ("CO164",),
        "CS001": ("CS001",),
        "CS026": ("CS026",),
        "CS048": ("CS048",),
        "ES001": ("ES001", "populacao_atendida_esgoto", "populacao_atentida_esgoto"),
        "ES005": ("ES005", "volume_esgoto_coletado"),
        "ES006": ("ES006", "volume_esgoto_tratado"),
        "ES013": ("ES013", "volume_esgoto_bruto_importado"),
        "ES014": ("ES014",),
        "ES015": ("ES015",),
        "ES026": ("ES026", "populacao_urbana_atendida_esgoto"),
        "ESO26": ("ESO26",),
        "G06A": ("G06A", "populacao_urbana_residente_agua"),
        "G12A": ("G12A", "populacao_urbana_atendida_agua_ibge"),
        "PMGIRS": ("PMGIRS",),
        "PO007": ("PO007",),
        "PO028": ("PO028",),
        "PO048": ("PO048",),
        "POP_TOT": ("POP_TOT", "populacao_total"),
        "POP_URB": ("POP_URB", "populacao_urbana"),
    }

    MUNICIPIO_CANDIDATES = (
        "id_municipio",
        "id_municipio_ibge",
        "id_municipio_6",
        "id_municipio_7",
        "codigo_municipio",
        "cod_municipio",
        "municipio_id",
        "cod_ibge",
        "ibge",
    )
    ANO_CANDIDATES = (
        "ano",
        "ano_referencia",
        "ano_base",
        "ano_referencia_snis",
        "year",
    )
    UF_CANDIDATES = ("sigla_uf", "uf", "sigla_uf_municipio", "uf_municipio")

    def __init__(self, output_path: Optional[str] = None):
        base_output = output_path or str(config.data_root / "snis")
        super().__init__(name="snis", output_path=base_output)

    def download(
        self,
        ano: int,
        output_csv: str,
        ufs: Optional[Sequence[str]] = None,
        municipios: Optional[Sequence[str]] = None,
        table_id: Optional[str] = None,
        billing_project_id: Optional[str] = None,
        ano_col_override: Optional[str] = None,
        municipio_col_override: Optional[str] = None,
        uf_col_override: Optional[str] = None,
        all_columns: bool = False,
    ) -> Path:
        """Download SNIS data for a given year and save to CSV."""
        table_id = table_id or self.DEFAULT_TABLE
        project, dataset, table = self._parse_table_id(table_id)
        billing_project_id = self._resolve_billing_project(billing_project_id)

        fields = self._get_fields(project, dataset, table, billing_project_id)
        ano_col = ano_col_override or self._pick_field(fields, self.ANO_CANDIDATES)
        municipio_col = municipio_col_override or self._pick_field(
            fields, self.MUNICIPIO_CANDIDATES
        )
        uf_col = uf_col_override or self._pick_field(fields, self.UF_CANDIDATES)

        if not ano_col or not municipio_col:
            logger.error("Available fields: {}", ", ".join(sorted(fields)))
            raise RuntimeError(
                "Required columns not found in SNIS schema. "
                f"Found ano={ano_col}, municipio={municipio_col}."
            )

        resolved_columns = self._resolve_indicator_columns(fields)
        missing = [name for name, col in resolved_columns.items() if col is None]
        if missing:
            logger.warning(
                "Missing indicator columns in SNIS dataset: {}",
                ", ".join(missing),
            )

        extra_fields: List[str] = []
        if all_columns:
            extra_fields = [field for field in fields if field not in self.OUTPUT_COLUMNS]

        sql = self._build_sql(
            table_ref=f"{project}.{dataset}.{table}",
            ano=ano,
            ano_col=ano_col,
            municipio_col=municipio_col,
            uf_col=uf_col,
            resolved_columns=resolved_columns,
            ufs=ufs,
            municipios=municipios,
            extra_fields=extra_fields,
        )

        df = self._read_sql(sql, billing_project_id)
        if df.empty:
            logger.warning("No records returned for the requested parameters.")

        output_columns = self.OUTPUT_COLUMNS + extra_fields
        df = df.reindex(columns=output_columns)

        output_path = Path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info(f"Saved SNIS data to {output_path}")
        return output_path

    def export_schema(
        self,
        output_csv: str,
        table_id: Optional[str] = None,
        billing_project_id: Optional[str] = None,
    ) -> Path:
        """Export BigQuery schema info to CSV for the SNIS table."""
        table_id = table_id or self.DEFAULT_TABLE
        project, dataset, table = self._parse_table_id(table_id)
        billing_project_id = self._resolve_billing_project(billing_project_id)

        sql = (
            f"SELECT * FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS` "
            f"WHERE table_name = '{table}'"
        )
        df = self._read_sql(sql, billing_project_id)

        output_path = Path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info(f"Saved SNIS schema to {output_path}")
        return output_path

    def load_dataframe(self, csv_path: str) -> pl.DataFrame:
        """Load a CSV file produced by this data source into Polars."""
        return pl.read_csv(csv_path)

    @staticmethod
    def _normalize_field(name: str) -> str:
        normalized: List[str] = []
        last_was_sep = False
        for ch in name.lower().strip():
            if ch.isalnum():
                normalized.append(ch)
                last_was_sep = False
            else:
                if not last_was_sep:
                    normalized.append("_")
                    last_was_sep = True
        return "".join(normalized).strip("_")

    def _pick_field(self, fields: Iterable[str], candidates: Sequence[str]) -> Optional[str]:
        normalized = {self._normalize_field(field): field for field in fields}
        for candidate in candidates:
            key = self._normalize_field(candidate)
            if key in normalized:
                return normalized[key]
        return None

    def _resolve_indicator_columns(self, fields: Iterable[str]) -> Dict[str, Optional[str]]:
        normalized = {self._normalize_field(field): field for field in fields}
        resolved: Dict[str, Optional[str]] = {}
        for indicator, aliases in self.INDICATOR_ALIASES.items():
            found = None
            for alias in aliases:
                key = self._normalize_field(alias)
                if key in normalized:
                    found = normalized[key]
                    break
            resolved[indicator] = found
        return resolved

    def _build_sql(
        self,
        table_ref: str,
        ano: int,
        ano_col: str,
        municipio_col: str,
        uf_col: Optional[str],
        resolved_columns: Dict[str, Optional[str]],
        ufs: Optional[Sequence[str]],
        municipios: Optional[Sequence[str]],
        extra_fields: Optional[Sequence[str]] = None,
    ) -> str:
        select_parts: List[str] = []
        select_parts.append(self._select_alias(ano_col, "ano"))
        select_parts.append(self._select_alias(municipio_col, "id_municipio"))

        for indicator in self.OUTPUT_COLUMNS:
            if indicator in ("ano", "id_municipio"):
                continue
            resolved = resolved_columns.get(indicator)
            if resolved:
                select_parts.append(self._select_alias(resolved, indicator))
            else:
                select_parts.append(f"NULL AS {self._quote_identifier(indicator)}")

        if extra_fields:
            for field in extra_fields:
                select_parts.append(self._quote_identifier(field))

        where_parts = [f"{self._quote_identifier(ano_col)} = {int(ano)}"]

        if ufs:
            if not uf_col:
                logger.warning("UF filter requested but UF column not found in schema.")
            else:
                cleaned_ufs = self._clean_ufs(ufs)
                uf_list = ", ".join(f"'{uf}'" for uf in cleaned_ufs)
                where_parts.append(
                    f"{self._quote_identifier(uf_col)} IN ({uf_list})"
                )

        if municipios:
            cleaned_municipios = self._clean_municipios(municipios)
            municipios_list = ", ".join(f"'{m}'" for m in cleaned_municipios)
            where_parts.append(
                f"{self._quote_identifier(municipio_col)} IN ({municipios_list})"
            )

        select_clause = ", ".join(select_parts)
        where_clause = " AND ".join(where_parts)
        return f"SELECT {select_clause} FROM `{table_ref}` WHERE {where_clause}"

    def _select_alias(self, column: str, alias: str) -> str:
        column_ref = self._quote_identifier(column)
        if column == alias:
            return column_ref
        return f"{column_ref} AS {self._quote_identifier(alias)}"

    @staticmethod
    def _quote_identifier(name: str) -> str:
        return f"`{name}`"

    @staticmethod
    def _clean_ufs(ufs: Sequence[str]) -> List[str]:
        cleaned: List[str] = []
        for uf in ufs:
            upper = uf.strip().upper()
            if len(upper) != 2 or not upper.isalpha():
                raise ValueError(f"Invalid UF value: {uf}")
            cleaned.append(upper)
        return cleaned

    @staticmethod
    def _clean_municipios(municipios: Sequence[str]) -> List[str]:
        cleaned: List[str] = []
        for municipio in municipios:
            value = municipio.strip()
            if not value.isdigit():
                raise ValueError(f"Invalid municipio code: {municipio}")
            cleaned.append(value)
        return cleaned

    @staticmethod
    def _parse_table_id(table_id: str) -> tuple[str, str, str]:
        parts = table_id.split(".")
        if len(parts) != 3:
            raise ValueError(
                "table_id must be in the format <project>.<dataset>.<table>."
            )
        return parts[0], parts[1], parts[2]

    @staticmethod
    def _resolve_billing_project(billing_project_id: Optional[str]) -> str:
        if billing_project_id:
            return billing_project_id
        env_value = os.getenv("BASEDOSDADOS_BILLING_PROJECT") or os.getenv(
            "GOOGLE_CLOUD_PROJECT"
        )
        if not env_value:
            raise RuntimeError(
                "Missing billing project id. Provide --billing-project or set "
                "BASEDOSDADOS_BILLING_PROJECT / GOOGLE_CLOUD_PROJECT."
            )
        return env_value

    def _get_fields(
        self, project: str, dataset: str, table: str, billing_project_id: str
    ) -> List[str]:
        sql = (
            "SELECT column_name FROM "
            f"`{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS` "
            f"WHERE table_name = '{table}' "
            "ORDER BY ordinal_position"
        )
        df = self._read_sql(sql, billing_project_id)
        return df["column_name"].astype(str).tolist()

    @staticmethod
    def _read_sql(sql: str, billing_project_id: str) -> pd.DataFrame:
        try:
            from google.cloud import bigquery  # type: ignore
            from google.oauth2 import service_account  # type: ignore
            from google.auth.exceptions import DefaultCredentialsError  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "google-cloud-bigquery is required for SNIS BigQuery integration. "
                "Install with: pip install google-cloud-bigquery"
            ) from exc

        credentials = None
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path:
            cred_file = Path(cred_path)
            if not cred_file.exists():
                raise RuntimeError(
                    f"GOOGLE_APPLICATION_CREDENTIALS not found: {cred_file}"
                )
            credentials = service_account.Credentials.from_service_account_file(
                str(cred_file)
            )

        try:
            client = bigquery.Client(
                project=billing_project_id,
                credentials=credentials,
            )
        except DefaultCredentialsError as exc:
            raise RuntimeError(
                "BigQuery credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
                "to a service account JSON file."
            ) from exc

        query_job = client.query(sql)
        return query_job.to_dataframe()


# Backward-compatible alias for legacy imports.
SnisDataSource = SnisLegacyBigQueryDataSource
