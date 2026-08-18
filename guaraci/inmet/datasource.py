"""INMET historical automatic-station datasource.

Downloads INMET's per-year ZIP archives of ALL automatic weather stations
(``https://portal.inmet.gov.br/uploads/dadoshistoricos/<AAAA>.zip``),
extracts the station CSVs (optionally filtered by UF), parses each into tidy
hourly rows (see :mod:`guaraci.inmet.parser` for the verified file shape),
and materializes a wide tidy table.

Caching / idempotency: the yearly ZIP is cached under
``<output_dir>/raw/<year>.zip``. Frozen years (before the current year) are
never re-downloaded once cached. The current year's archive grows over the
year (INMET republishes it with more months), so it is reconciled by
``Content-Length``: a HEAD probe compares the remote size against the cached
file and only re-downloads when they differ.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl
from loguru import logger

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.inmet.client import InmetClient, InmetClientError
from guaraci.inmet.parser import (
    BASE_COLUMNS,
    StationFileInfo,
    parse_station_csv,
    parse_station_filename,
)

ProgressCallback = Callable[[Dict[str, object]], None]


class InmetEstacoesDataSource(DataSource):
    """INMET automatic weather stations, historical hourly series."""

    MIN_YEAR = 2000
    DEFAULT_TIMEOUT = 180

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[InmetClient] = None,
    ) -> None:
        super().__init__(name="inmet_estacoes", output_path=output_path)
        self._client = client
        self._dataframe: pl.DataFrame = pl.DataFrame()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def download(
        self,
        *,
        start_year: object,
        end_year: Optional[object] = None,
        ufs: Optional[Sequence[str]] = None,
        variables: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        """Download and materialize INMET station data for a year range."""

        start = self._parse_year(start_year, field_name="start_year")
        end = self._parse_year(end_year, field_name="end_year") if end_year is not None else start
        if end < start:
            raise ValueError("Parameter 'end_year' cannot be before 'start_year'.")
        uf_filter = self._normalize_ufs(ufs)
        variable_filter = self._normalize_variables(variables)

        base_dir = Path(output_dir) if output_dir else self.output_path
        raw_dir = base_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)
        current_year = datetime.now().year
        years = list(range(start, end + 1))

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": len(years),
                }
            )

        downloaded_files: List[str] = []
        skipped_files: List[str] = []
        failed: List[str] = []
        warnings: List[str] = []
        records: List[Dict[str, object]] = []
        stations_seen: set[str] = set()

        for index, year in enumerate(years, start=1):
            zip_path = raw_dir / f"{year}.zip"
            try:
                fetched = self._ensure_zip_cached(
                    client,
                    year=year,
                    zip_path=zip_path,
                    current_year=current_year,
                    warnings=warnings,
                )
            except InmetClientError as exc:
                failed.append(f"{year}: {exc}")
                self._emit_file_event(
                    progress_callback, "file_failed", index, len(years), zip_path, error=str(exc)
                )
                continue

            if fetched:
                downloaded_files.append(str(zip_path))
            else:
                skipped_files.append(str(zip_path))
            self._emit_file_event(progress_callback, "file_completed", index, len(years), zip_path)

            try:
                year_records, station_codes, year_warnings = self._parse_year_zip(
                    zip_path,
                    year=year,
                    uf_filter=uf_filter,
                    keep_raw=keep_raw,
                    extract_dir=base_dir / "extracted" / str(year),
                )
            except (zipfile.BadZipFile, OSError) as exc:
                failed.append(f"{year}: could not read cached ZIP ({exc}).")
                continue
            records.extend(year_records)
            stations_seen.update(station_codes)
            warnings.extend(year_warnings)

        dataframe = self._records_to_dataframe(records)
        dataframe, missing_variables = self._apply_variable_filter(dataframe, variable_filter)
        if missing_variables:
            warnings.append(
                "Requested variables not found in any parsed file: "
                + ", ".join(sorted(missing_variables))
            )
        self._dataframe = dataframe

        if dataframe.is_empty():
            warnings.append(
                "No records parsed for the requested start_year/end_year/ufs. "
                "Check the year range (2000+) and UF codes."
            )

        requested_format = self._normalize_output_format(output_format)
        exported_files: List[str] = []
        artifact_stem = f"inmet_estacoes_{start}_{end}"
        if requested_format and not dataframe.is_empty():
            try:
                export_path = self.export(dataframe, format=requested_format, name=artifact_stem)
                exported_files.append(str(export_path))
            except Exception as exc:  # noqa: BLE001 - reported as a warning
                warnings.append(
                    f"INMET export failed after download. ZIP cache and any extracted "
                    f"CSVs were kept. Error: {exc}"
                )
        elif requested_format and dataframe.is_empty():
            warnings.append("No data artifact generated: parsed dataframe is empty.")
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            base_dir=base_dir,
            start_year=start,
            end_year=end,
            ufs=uf_filter,
            variables=variable_filter,
            keep_raw=keep_raw,
            output_format=requested_format,
            api_base_url=client.base_url,
            record_count=len(records),
            station_count=len(stations_seen),
            downloaded_files=downloaded_files,
            skipped_files=skipped_files,
            failed_urls=failed,
            exported_files=exported_files,
            warnings=warnings,
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": self.name,
                    "documents_total": len(years),
                    "downloaded_count": len(downloaded_files),
                    "skipped_count": len(skipped_files),
                    "failed_count": len(failed),
                    "output_dir": str(base_dir),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": len(years),
            "downloaded_count": len(downloaded_files),
            "skipped_count": len(skipped_files),
            "failed_count": len(failed),
            "manifest_path": str(manifest_path),
            "output_dir": str(base_dir),
            "start_year": start,
            "end_year": end,
            "ufs": list(uf_filter) if uf_filter else None,
            "variables": list(variable_filter) if variable_filter else None,
            "record_count": len(records),
            "station_count": len(stations_seen),
            "output_format": requested_format,
            "exported_files": exported_files,
            "keep_raw": keep_raw,
        }
        combined_warning = self._combine_warnings(warnings)
        if combined_warning:
            payload["export_warning"] = combined_warning
        return payload

    def load_dataframe(self) -> pl.DataFrame:
        """Return the tidy table materialized by the most recent download."""
        return self._dataframe

    def export(self, df: pl.DataFrame, format: str, name: str) -> Path:  # noqa: A003
        """Export a Polars DataFrame to CSV, Parquet or SQLite."""
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
                    "inmet_estacoes_records", connection, if_exists="replace", index=False
                )
            return path
        raise ValueError(
            f"Unsupported INMET export format '{format}'. Allowed: csv, parquet, sqlite"
        )

    # ------------------------------------------------------------------
    # Zip caching / parsing
    # ------------------------------------------------------------------
    def _ensure_zip_cached(
        self,
        client: InmetClient,
        *,
        year: int,
        zip_path: Path,
        current_year: int,
        warnings: List[str],
    ) -> bool:
        """Download the year's ZIP if missing/stale. Returns True if fetched."""
        if zip_path.exists():
            if year < current_year:
                return False
            try:
                remote_size = client.head_content_length(year)
            except InmetClientError as exc:
                warnings.append(
                    f"Could not verify remote size for {year} (kept cached copy): {exc}"
                )
                return False
            local_size = zip_path.stat().st_size
            if remote_size is None or remote_size == local_size:
                return False
        client.download_zip(year, zip_path)
        return True

    def _parse_year_zip(
        self,
        zip_path: Path,
        *,
        year: int,
        uf_filter: Optional[Sequence[str]],
        keep_raw: bool,
        extract_dir: Path,
    ) -> Tuple[List[Dict[str, object]], List[str], List[str]]:
        records: List[Dict[str, object]] = []
        station_codes: List[str] = []
        warnings: List[str] = []
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                basename = Path(member.filename).name
                if not basename.lower().endswith(".csv"):
                    continue
                file_info = parse_station_filename(basename)
                if file_info is None:
                    warnings.append(f"{year}: could not parse station filename '{basename}'.")
                    continue
                if uf_filter and file_info.uf not in uf_filter:
                    continue
                raw_bytes = zf.read(member)
                try:
                    _metadata, station_records, station_warnings = parse_station_csv(
                        raw_bytes, year=year, file_info=file_info
                    )
                except ValueError as exc:
                    warnings.append(f"{year}/{basename}: {exc}")
                    continue
                records.extend(station_records)
                station_codes.append(f"{file_info.uf}:{file_info.code}")
                warnings.extend(station_warnings)
                if keep_raw:
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    (extract_dir / basename).write_bytes(raw_bytes)
        return records, station_codes, warnings

    # ------------------------------------------------------------------
    # Validation / normalization helpers
    # ------------------------------------------------------------------
    def _resolve_client(self, *, api_base_url: Optional[str], timeout: int) -> InmetClient:
        timeout_value = max(1, int(timeout))
        if api_base_url and str(api_base_url).strip():
            return InmetClient(base_url=str(api_base_url).strip(), timeout_seconds=timeout_value)
        if self._client is not None:
            return self._client
        return InmetClient(timeout_seconds=timeout_value)

    @classmethod
    def _parse_year(cls, value: object, *, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"Parameter '{field_name}' must be a year (integer).")
        if isinstance(value, int):
            year = value
        elif isinstance(value, str) and value.strip():
            try:
                year = int(value.strip())
            except ValueError as exc:
                raise ValueError(f"Parameter '{field_name}' must be a year (integer).") from exc
        else:
            raise ValueError(f"Parameter '{field_name}' is required.")
        current_year = datetime.now().year
        if year < cls.MIN_YEAR or year > current_year:
            raise ValueError(
                f"Parameter '{field_name}' must be between {cls.MIN_YEAR} and {current_year}."
            )
        return year

    @staticmethod
    def _normalize_ufs(ufs: Optional[Sequence[str]]) -> Optional[Tuple[str, ...]]:
        if not ufs:
            return None
        cleaned: List[str] = []
        for item in ufs:
            code = str(item).strip().upper()
            if code and code not in cleaned:
                cleaned.append(code)
        return tuple(cleaned) if cleaned else None

    @staticmethod
    def _normalize_variables(variables: Optional[Sequence[str]]) -> Optional[Tuple[str, ...]]:
        if not variables:
            return None
        cleaned: List[str] = []
        for item in variables:
            slug = str(item).strip().lower()
            if slug and slug not in cleaned:
                cleaned.append(slug)
        return tuple(cleaned) if cleaned else None

    @staticmethod
    def _normalize_output_format(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        if cleaned not in {"csv", "parquet", "sqlite"}:
            raise ValueError(
                f"Unsupported output format '{value}'. Allowed: csv, parquet, sqlite"
            )
        return cleaned

    @staticmethod
    def _records_to_dataframe(records: List[Dict[str, object]]) -> pl.DataFrame:
        if not records:
            return pl.DataFrame()
        return pl.from_dicts(records, infer_schema_length=None)

    @staticmethod
    def _apply_variable_filter(
        dataframe: pl.DataFrame, variable_filter: Optional[Sequence[str]]
    ) -> Tuple[pl.DataFrame, List[str]]:
        if not variable_filter or dataframe.is_empty():
            return dataframe, []
        present = [name for name in variable_filter if name in dataframe.columns]
        missing = [name for name in variable_filter if name not in dataframe.columns]
        keep = [col for col in BASE_COLUMNS if col in dataframe.columns] + present
        return dataframe.select(keep), missing

    @staticmethod
    def _emit_file_event(
        progress_callback: Optional[ProgressCallback],
        event: str,
        index: int,
        total: int,
        zip_path: Path,
        *,
        error: Optional[str] = None,
    ) -> None:
        if progress_callback is None:
            return
        payload: Dict[str, object] = {
            "event": event,
            "source": "inmet_estacoes",
            "document_index": index,
            "documents_total": total,
            "file_path": str(zip_path),
        }
        if error is not None:
            payload["error"] = error
        progress_callback(payload)

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    def _write_manifest(
        self,
        *,
        base_dir: Path,
        start_year: int,
        end_year: int,
        ufs: Optional[Sequence[str]],
        variables: Optional[Sequence[str]],
        keep_raw: bool,
        output_format: Optional[str],
        api_base_url: str,
        record_count: int,
        station_count: int,
        downloaded_files: Sequence[str],
        skipped_files: Sequence[str],
        failed_urls: Sequence[str],
        exported_files: Sequence[str],
        warnings: Sequence[str],
    ) -> Path:
        manifest = DownloadManifest(
            source=self.name,
            results_url=api_base_url,
            filters={
                "start_year": start_year,
                "end_year": end_year,
                "ufs": list(ufs) if ufs else None,
                "variables": list(variables) if variables else None,
                "keep_raw": keep_raw,
                "output_format": output_format,
                "api_base_url": api_base_url,
            },
            documents_found=record_count,
            downloaded_files=list(downloaded_files),
            skipped_files=list(skipped_files),
            failed_urls=list(failed_urls),
            materialized_paths=list(downloaded_files) + list(skipped_files),
            exported_files=list(exported_files),
            warnings=list(warnings),
        )
        manifest_path = base_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("{} manifest saved to {}", self.name.upper(), manifest_path)
        return manifest_path

    @staticmethod
    def _combine_warnings(warnings: Sequence[str]) -> Optional[str]:
        cleaned = [item.strip() for item in warnings if str(item).strip()]
        if not cleaned:
            return None
        return " ".join(cleaned)
