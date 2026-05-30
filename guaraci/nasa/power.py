"""NASA POWER datasource: single-point meteorological and solar series.

NASA POWER serves global gridded climatology (~0.5 deg x 0.625 deg) that fully
covers Brazil, with no authentication. This datasource fetches one point
(latitude/longitude) over a date window at daily or monthly resolution and
materializes a tidy wide table (one row per period, one column per parameter).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.nasa.client import NasaPowerClient, NasaPowerClientError


class NasaPowerDataSource(DataSource):
    """NASA POWER datasource supporting daily and monthly point series."""

    DEFAULT_TEMPORAL = "daily"
    DEFAULT_COMMUNITY = "AG"
    DEFAULT_TIMEOUT = 120
    VALID_TEMPORAL = ("daily", "monthly")
    VALID_COMMUNITIES = ("AG", "RE", "SB")

    # Curated subset of the POWER catalogue most relevant to public-health and
    # environmental cross-analysis. POWER exposes hundreds of variables; this
    # list keeps the schema-driven UI discoverable while staying native to the
    # API. The full catalogue can be reached later via an explicit override.
    SUPPORTED_PARAMETERS: Dict[str, str] = {
        "T2M": "Temperature at 2 meters (C)",
        "T2M_MAX": "Maximum temperature at 2 meters (C)",
        "T2M_MIN": "Minimum temperature at 2 meters (C)",
        "T2MDEW": "Dew/frost point at 2 meters (C)",
        "T2MWET": "Wet bulb temperature at 2 meters (C)",
        "RH2M": "Relative humidity at 2 meters (%)",
        "QV2M": "Specific humidity at 2 meters (g/kg)",
        "PRECTOTCORR": "Precipitation corrected (mm/day)",
        "WS2M": "Wind speed at 2 meters (m/s)",
        "WS10M": "Wind speed at 10 meters (m/s)",
        "PS": "Surface pressure (kPa)",
        "ALLSKY_SFC_SW_DWN": "All-sky surface shortwave downward irradiance "
        "(kWh/m^2/day)",
        "CLRSKY_SFC_SW_DWN": "Clear-sky surface shortwave downward irradiance "
        "(kWh/m^2/day)",
        "ALLSKY_SFC_UV_INDEX": "All-sky surface UV index",
    }
    DEFAULT_PARAMETERS: Tuple[str, ...] = (
        "T2M",
        "T2M_MAX",
        "T2M_MIN",
        "PRECTOTCORR",
        "RH2M",
    )

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[NasaPowerClient] = None,
    ) -> None:
        super().__init__(name="nasa_power", output_path=output_path)
        self._client = client
        self._records: List[Dict[str, object]] = []

    def download(
        self,
        *,
        latitude: object,
        longitude: object,
        start_date: str,
        end_date: str,
        parameters: Optional[Sequence[str]] = None,
        temporal: str = DEFAULT_TEMPORAL,
        community: str = DEFAULT_COMMUNITY,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download one NASA POWER point series and materialize a table."""

        temporal_clean = self._normalize_temporal(temporal)
        community_clean = self._normalize_community(community)
        lat = self._parse_coordinate(latitude, field_name="latitude", limit=90.0)
        lon = self._parse_coordinate(longitude, field_name="longitude", limit=180.0)
        start = self._parse_iso_date(start_date, field_name="start_date")
        end = self._parse_iso_date(end_date, field_name="end_date")
        if start > end:
            raise ValueError("Parameter 'start_date' cannot be after 'end_date'.")
        param_codes = self._normalize_parameters(parameters)
        api_start, api_end = self._build_temporal_window(temporal_clean, start, end)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": 1,
                }
            )

        try:
            payload = client.temporal_point(
                temporal=temporal_clean,
                parameters=param_codes,
                latitude=lat,
                longitude=lon,
                start=api_start,
                end=api_end,
                community=community_clean,
            )
        except NasaPowerClientError as exc:
            raise exc.with_context(
                "NASA POWER request failed for "
                f"{temporal_clean} point ({lat}, {lon}) "
                f"window {api_start}-{api_end}"
            ) from exc

        records, units, response_messages = self._parse_response(
            payload,
            temporal=temporal_clean,
            latitude=lat,
            longitude=lon,
            parameters=param_codes,
        )
        self._records = records

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "file_completed",
                    "source": self.name,
                    "documents_total": 1,
                    "document_index": 1,
                    "files_completed": 1,
                    "file_path": f"power_{temporal_clean}_{api_start}_{api_end}",
                }
            )

        artifact_stem = self._build_artifact_stem(
            temporal=temporal_clean,
            latitude=lat,
            longitude=lon,
            start=api_start,
            end=api_end,
        )
        raw_path: Optional[Path] = None
        if keep_raw:
            raw_path = self._write_raw_snapshot(stem=artifact_stem, payload=payload)

        requested_format = self._normalize_output_format(output_format)
        exported_files: List[str] = []
        warnings: List[str] = list(response_messages)
        if not records:
            warnings.append(
                "NASA POWER returned no data points for the requested window. "
                "Check the date window, coordinates, and parameter availability "
                "for the selected temporal resolution."
            )
        if requested_format:
            if records:
                try:
                    dataframe = self._records_to_dataframe(records)
                    export_path = self.export(
                        dataframe,
                        format=requested_format,
                        name=artifact_stem,
                    )
                    exported_files.append(str(export_path))
                except Exception as exc:  # noqa: BLE001 - reported as a warning
                    warnings.append(
                        self._build_export_failure_warning(
                            exc=exc, keep_raw=keep_raw
                        )
                    )
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            temporal=temporal_clean,
            community=community_clean,
            latitude=lat,
            longitude=lon,
            start=start,
            end=end,
            api_start=api_start,
            api_end=api_end,
            parameters=param_codes,
            units=units,
            record_count=len(records),
            raw_path=raw_path,
            keep_raw=keep_raw,
            output_format=requested_format,
            exported_files=exported_files,
            api_base_url=client.base_url,
            warnings=warnings,
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": self.name,
                    "documents_total": 1,
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
            "temporal": temporal_clean,
            "community": community_clean,
            "latitude": lat,
            "longitude": lon,
            "parameters": list(param_codes),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "query_start": api_start,
            "query_end": api_end,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw,
            "output_format": requested_format,
            "exported_files": exported_files,
            "units": units,
        }
        export_warning = self._combine_warnings(warnings)
        if export_warning:
            payload_out["export_warning"] = export_warning
        return payload_out

    def load_dataframe(self) -> pl.DataFrame:
        """Load the most recent NASA POWER download into Polars."""

        if not self._records:
            return pl.DataFrame()
        return self._records_to_dataframe(self._records)

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
                    "nasa_power_records",
                    connection,
                    if_exists="replace",
                    index=False,
                )
            return path
        raise ValueError(
            f"Unsupported NASA POWER export format '{format}'. "
            "Allowed: csv, parquet, sqlite"
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_response(
        self,
        payload: Mapping[str, object],
        *,
        temporal: str,
        latitude: float,
        longitude: float,
        parameters: Sequence[str],
    ) -> Tuple[List[Dict[str, object]], Dict[str, str], List[str]]:
        properties = payload.get("properties")
        param_block = (
            properties.get("parameter") if isinstance(properties, Mapping) else None
        )
        if not isinstance(param_block, Mapping):
            param_block = {}

        header = payload.get("header")
        fill_value = (
            header.get("fill_value") if isinstance(header, Mapping) else None
        )
        fill_float = self._to_float(fill_value)

        lat, lon, elevation = self._resolve_geometry(payload, latitude, longitude)
        units = self._extract_units(payload)
        messages = self._extract_messages(payload)

        period_keys: set[str] = set()
        for series in param_block.values():
            if isinstance(series, Mapping):
                period_keys.update(str(key) for key in series)

        records: List[Dict[str, object]] = []
        for key in sorted(period_keys):
            date_iso, year, month, day = self._derive_period(key, temporal)
            row: Dict[str, object] = {
                "period": key,
                "date": date_iso,
                "year": year,
                "month": month,
                "day": day,
                "latitude": lat,
                "longitude": lon,
                "elevation": elevation,
            }
            for code in parameters:
                series = param_block.get(code)
                value = (
                    series.get(key) if isinstance(series, Mapping) else None
                )
                row[code] = self._clean_value(value, fill_float)
            records.append(row)
        return records, units, messages

    @staticmethod
    def _derive_period(
        key: str, temporal: str
    ) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
        digits = key.strip()
        if temporal == "daily" and len(digits) == 8 and digits.isdigit():
            year = int(digits[0:4])
            month = int(digits[4:6])
            day = int(digits[6:8])
            try:
                iso = date(year, month, day).isoformat()
            except ValueError:
                iso = None
            return iso, year, month, day
        if temporal == "monthly" and len(digits) == 6 and digits.isdigit():
            year = int(digits[0:4])
            month = int(digits[4:6])
            # POWER encodes the annual aggregate as month 13; keep it lossless
            # (month=13, no date) so downstream filters on month <= 12 isolate
            # true monthly observations.
            if 1 <= month <= 12:
                return date(year, month, 1).isoformat(), year, month, None
            return None, year, month, None
        return None, None, None, None

    @staticmethod
    def _clean_value(value: object, fill_float: Optional[float]) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        if fill_float is not None and float(value) == fill_float:
            return None
        return value

    @staticmethod
    def _resolve_geometry(
        payload: Mapping[str, object], latitude: float, longitude: float
    ) -> Tuple[float, float, Optional[float]]:
        geometry = payload.get("geometry")
        coords = (
            geometry.get("coordinates") if isinstance(geometry, Mapping) else None
        )
        if isinstance(coords, Sequence) and not isinstance(coords, (str, bytes)):
            lon = NasaPowerDataSource._to_float(coords[0]) if len(coords) > 0 else None
            lat = NasaPowerDataSource._to_float(coords[1]) if len(coords) > 1 else None
            elev = NasaPowerDataSource._to_float(coords[2]) if len(coords) > 2 else None
            return (
                lat if lat is not None else latitude,
                lon if lon is not None else longitude,
                elev,
            )
        return latitude, longitude, None

    @staticmethod
    def _extract_units(payload: Mapping[str, object]) -> Dict[str, str]:
        meta = payload.get("parameters")
        units: Dict[str, str] = {}
        if isinstance(meta, Mapping):
            for code, info in meta.items():
                if isinstance(info, Mapping):
                    unit = info.get("units")
                    if unit is not None:
                        units[str(code)] = str(unit)
        return units

    @staticmethod
    def _extract_messages(payload: Mapping[str, object]) -> List[str]:
        messages = payload.get("messages")
        if isinstance(messages, list):
            return [str(item) for item in messages if str(item).strip()]
        return []

    @staticmethod
    def _records_to_dataframe(records: List[Dict[str, object]]) -> pl.DataFrame:
        return pl.from_dicts(records, infer_schema_length=None)

    # ------------------------------------------------------------------
    # Validation / normalization helpers
    # ------------------------------------------------------------------
    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> NasaPowerClient:
        timeout_value = max(1, int(timeout))
        if api_base_url and api_base_url.strip():
            return NasaPowerClient(
                base_url=api_base_url.strip(), timeout_seconds=timeout_value
            )
        if self._client is not None:
            return self._client
        return NasaPowerClient(timeout_seconds=timeout_value)

    def _normalize_temporal(self, temporal: str) -> str:
        cleaned = str(temporal).strip().lower()
        if cleaned not in self.VALID_TEMPORAL:
            raise ValueError(
                f"Parameter 'temporal' must be one of {', '.join(self.VALID_TEMPORAL)}."
            )
        return cleaned

    def _normalize_community(self, community: str) -> str:
        cleaned = str(community).strip().upper()
        if cleaned not in self.VALID_COMMUNITIES:
            raise ValueError(
                "Parameter 'community' must be one of "
                f"{', '.join(self.VALID_COMMUNITIES)}."
            )
        return cleaned

    def _normalize_parameters(
        self, parameters: Optional[Sequence[str]]
    ) -> Tuple[str, ...]:
        if not parameters:
            return self.DEFAULT_PARAMETERS
        cleaned: List[str] = []
        for item in parameters:
            code = str(item).strip().upper()
            if not code:
                continue
            if code not in self.SUPPORTED_PARAMETERS:
                allowed = ", ".join(sorted(self.SUPPORTED_PARAMETERS))
                raise ValueError(
                    f"Unsupported NASA POWER parameter '{item}'. Allowed: {allowed}"
                )
            if code not in cleaned:
                cleaned.append(code)
        if not cleaned:
            return self.DEFAULT_PARAMETERS
        return tuple(cleaned)

    @staticmethod
    def _parse_coordinate(value: object, *, field_name: str, limit: float) -> float:
        if isinstance(value, bool):
            raise ValueError(f"Parameter '{field_name}' must be a number.")
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError(f"Parameter '{field_name}' is required.")
            try:
                number = float(cleaned)
            except ValueError as exc:
                raise ValueError(
                    f"Parameter '{field_name}' must be a decimal number."
                ) from exc
        else:
            raise ValueError(f"Parameter '{field_name}' must be a number.")
        if number < -limit or number > limit:
            raise ValueError(
                f"Parameter '{field_name}' must be between -{limit} and {limit}."
            )
        return number

    @staticmethod
    def _parse_iso_date(value: str, *, field_name: str) -> date:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Parameter '{field_name}' is required (YYYY-MM-DD).")
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"Parameter '{field_name}' must use date format YYYY-MM-DD."
            ) from exc

    @staticmethod
    def _build_temporal_window(
        temporal: str, start: date, end: date
    ) -> Tuple[str, str]:
        if temporal == "monthly":
            return str(start.year), str(end.year)
        return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

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
    def _to_float(value: object) -> Optional[float]:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    def _build_artifact_stem(
        self,
        *,
        temporal: str,
        latitude: float,
        longitude: float,
        start: str,
        end: str,
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lat_token = f"{latitude:.4f}".replace("-", "S").replace(".", "p")
        lon_token = f"{longitude:.4f}".replace("-", "W").replace(".", "p")
        return f"nasa_power_{temporal}_{lat_token}_{lon_token}_{start}_{end}_{timestamp}"

    def _write_raw_snapshot(
        self, *, stem: str, payload: Mapping[str, object]
    ) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        file_path = raw_dir / f"{stem}.json"
        file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_path

    def _write_manifest(
        self,
        *,
        temporal: str,
        community: str,
        latitude: float,
        longitude: float,
        start: date,
        end: date,
        api_start: str,
        api_end: str,
        parameters: Sequence[str],
        units: Mapping[str, str],
        record_count: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: Sequence[str],
        api_base_url: str,
        warnings: Sequence[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        request_filters: Dict[str, object] = {
            "temporal": temporal,
            "community": community,
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "query_start": api_start,
            "query_end": api_end,
            "parameters": list(parameters),
            "units": dict(units),
            "keep_raw": keep_raw,
            "output_format": output_format,
            "api_base_url": api_base_url,
        }
        materialized_paths = [str(raw_path)] if raw_path else []
        manifest = DownloadManifest(
            source=self.name,
            results_url=api_base_url,
            filters=request_filters,
            documents_found=record_count,
            downloaded_files=[],
            materialized_paths=materialized_paths,
            exported_files=list(exported_files),
            warnings=list(warnings),
        )
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    @staticmethod
    def _combine_warnings(warnings: Sequence[str]) -> Optional[str]:
        cleaned = [item.strip() for item in warnings if str(item).strip()]
        if not cleaned:
            return None
        return " ".join(cleaned)

    @staticmethod
    def _build_export_failure_warning(*, exc: Exception, keep_raw: bool) -> str:
        if keep_raw:
            artifact_note = "Raw JSON snapshot and manifest were generated."
        else:
            artifact_note = (
                "Manifest was generated, but no data artifact was preserved. "
                "Re-run with keep_raw=true to retain the raw payload."
            )
        return f"NASA POWER export failed after download. {artifact_note} Error: {exc}"
