"""IBGE population estimates by locality x year (SIDRA aggregate table 6579).

Table 6579 / variable 9324 is "População residente estimada" — the annual TCU
population estimates IBGE publishes per municipality (and every coarser level).
It is the denominator layer for turning DATASUS case/death counts into rates.

One request per year keeps each response bounded; the tidy output is one row per
(locality, year): ``nivel, localidade_id, localidade_nome, ano, variavel_id,
unidade, valor``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.ibge.client import IbgeClientError, IbgeSidraClient

_EXPORT_FORMATS = {"csv", "parquet", "sqlite"}


class IbgePopulacaoDataSource(DataSource):
    """IBGE population estimates (SIDRA table 6579)."""

    TABLE = "6579"
    VARIABLE = "9324"
    DEFAULT_TIMEOUT = 120
    DEFAULT_LEVEL = "municipio"
    # Friendly aliases + raw SIDRA level codes.
    LEVELS: Dict[str, str] = {
        "municipio": "N6",
        "uf": "N3",
        "estado": "N3",
        "regiao": "N2",
        "brasil": "N1",
        "pais": "N1",
        "n6": "N6",
        "n3": "N3",
        "n2": "N2",
        "n1": "N1",
    }
    _MISSING = {"-", "..", "...", "x", "X", ""}

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_populacao", output_path=output_path)
        self._client = client
        self._records: List[Dict[str, object]] = []

    # -- collection -----------------------------------------------------------
    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download population estimates for a year range at one locality level."""
        y0 = self._parse_year(start_year, "start_year")
        y1 = self._parse_year(end_year, "end_year")
        if y0 > y1:
            raise ValueError("Parameter 'start_year' cannot be after 'end_year'.")
        nivel = self._resolve_level(level)
        localities = f"{nivel}[all]"
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        years = list(range(y0, y1 + 1))
        total = len(years)
        records: List[Dict[str, object]] = []
        raw_by_year: Dict[str, Any] = {}
        warnings: List[str] = []
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": total}
            )

        for index, year in enumerate(years, start=1):
            try:
                payload = client.aggregate(
                    table=self.TABLE,
                    variable=self.VARIABLE,
                    period=str(year),
                    localities=localities,
                )
            except IbgeClientError as exc:
                # A year with no estimate (e.g. a census year) must not abort the
                # whole range — record it and move on.
                warnings.append(f"IBGE year {year} skipped: {exc}")
                payload = None
            if payload:
                rows = self._parse(payload, nivel)
                records.extend(rows)
                if keep_raw:
                    raw_by_year[str(year)] = payload
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "documents_total": total,
                        "document_index": index,
                        "files_completed": index,
                        "file_path": f"ibge_pop_{year}",
                    }
                )

        self._records = records
        stem = self._artifact_stem(nivel, y0, y1)
        raw_path = self._write_raw(stem, raw_by_year) if (keep_raw and raw_by_year) else None

        requested_format = self._normalize_format(output_format)
        exported: List[str] = []
        if not records:
            warnings.append("IBGE returned no rows for the requested years/level.")
        if requested_format and records:
            try:
                exported.append(
                    str(self.export(self._to_df(records), format=requested_format, name=stem))
                )
            except Exception as exc:  # noqa: BLE001 - reported as a warning
                warnings.append(f"IBGE export failed after download. Error: {exc}")
        elif not requested_format and not keep_raw:
            warnings.append(
                "No artifact generated (output_format empty and keep_raw=false). "
                "Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            nivel=nivel,
            start_year=y0,
            end_year=y1,
            record_count=len(records),
            raw_path=raw_path,
            keep_raw=keep_raw,
            output_format=requested_format,
            exported=exported,
            api_base_url=client.base_url,
            warnings=warnings,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": self.name,
                    "documents_total": total,
                    "downloaded_count": len(records),
                    "failed_count": 0,
                    "skipped_count": 0,
                    "output_dir": str(self.output_path),
                }
            )

        payload_out: Dict[str, object] = {
            "documents_found": len(records),
            "downloaded_count": len(records),
            "skipped_count": 0,
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "level": nivel,
            "start_year": y0,
            "end_year": y1,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw,
            "output_format": requested_format,
            "exported_files": exported,
        }
        combined = " ".join(item for item in warnings if item.strip())
        if combined:
            payload_out["export_warning"] = combined
        return payload_out

    def load_dataframe(self) -> pl.DataFrame:
        """Load the most recent download into Polars."""
        return self._to_df(self._records) if self._records else pl.DataFrame()

    def export(self, df: pl.DataFrame, format: str, name: str) -> Path:  # noqa: A003
        """Export a DataFrame to CSV, Parquet or SQLite under the output path."""
        normalized = format.strip().lower()
        if normalized == "csv":
            path = self.output_path / f"{name}.csv"
            df.write_csv(path)
            return path
        if normalized == "parquet":
            path = self.output_path / f"{name}.parquet"
            df.write_parquet(path)
            return path
        if normalized == "sqlite":
            path = self.output_path / f"{name}.sqlite"
            with sqlite3.connect(path) as connection:
                df.to_pandas().to_sql(
                    "ibge_populacao", connection, if_exists="replace", index=False
                )
            return path
        raise ValueError(
            f"Unsupported IBGE export format '{format}'. Allowed: csv, parquet, sqlite"
        )

    # -- parsing --------------------------------------------------------------
    def _parse(self, payload: List[Any], nivel: str) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for variable in payload:
            if not isinstance(variable, dict):
                continue
            variable_id = variable.get("id")
            unidade = variable.get("unidade")
            for resultado in variable.get("resultados") or []:
                for serie in resultado.get("series") or []:
                    localidade = serie.get("localidade") or {}
                    values = serie.get("serie") or {}
                    for year_key, raw_value in values.items():
                        rows.append(
                            {
                                "nivel": nivel,
                                "localidade_id": localidade.get("id"),
                                "localidade_nome": localidade.get("nome"),
                                "ano": self._to_int(year_key),
                                "variavel_id": variable_id,
                                "unidade": unidade,
                                "valor": self._to_value(raw_value),
                            }
                        )
        return rows

    def _to_value(self, value: object) -> Optional[float]:
        if value is None:
            return None
        text = str(value).strip()
        if text in self._MISSING:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None

    @staticmethod
    def _to_int(value: object) -> Optional[int]:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_df(records: List[Dict[str, object]]) -> pl.DataFrame:
        return pl.from_dicts(records, infer_schema_length=None)

    # -- validation / helpers -------------------------------------------------
    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> IbgeSidraClient:
        timeout_value = max(1, int(timeout))
        if api_base_url and str(api_base_url).strip():
            return IbgeSidraClient(base_url=str(api_base_url).strip(), timeout_seconds=timeout_value)
        if self._client is not None:
            return self._client
        return IbgeSidraClient(timeout_seconds=timeout_value)

    def _resolve_level(self, level: str) -> str:
        key = str(level).strip().lower()
        if key not in self.LEVELS:
            allowed = ", ".join(sorted({v for v in self.LEVELS}))
            raise ValueError(f"Unsupported IBGE level '{level}'. Allowed: {allowed}")
        return self.LEVELS[key]

    @staticmethod
    def _parse_year(value: object, field_name: str) -> int:
        try:
            year = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{field_name}' must be a year (integer).") from exc
        if not (1900 <= year <= 2100):
            raise ValueError(f"Parameter '{field_name}' must be a plausible year.")
        return year

    @staticmethod
    def _normalize_format(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip().lower()
        if not cleaned:
            return None
        if cleaned not in _EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported output format '{value}'. Allowed: csv, parquet, sqlite"
            )
        return cleaned

    @staticmethod
    def _artifact_stem(nivel: str, start_year: int, end_year: int) -> str:
        return f"ibge_populacao_{nivel}_{start_year}_{end_year}"

    # -- artifacts ------------------------------------------------------------
    def _write_raw(self, stem: str, raw_by_year: Dict[str, Any]) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{stem}.json"
        path.write_text(json.dumps(raw_by_year, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _write_manifest(
        self,
        *,
        nivel: str,
        start_year: int,
        end_year: int,
        record_count: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported: List[str],
        api_base_url: str,
        warnings: List[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        manifest = DownloadManifest(
            source=self.name,
            results_url=api_base_url,
            filters={
                "table": self.TABLE,
                "variable": self.VARIABLE,
                "level": nivel,
                "start_year": start_year,
                "end_year": end_year,
                "keep_raw": keep_raw,
                "output_format": output_format,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            documents_found=record_count,
            downloaded_files=[],
            materialized_paths=[str(raw_path)] if raw_path else [],
            exported_files=list(exported),
            warnings=list(warnings),
        )
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest_path
