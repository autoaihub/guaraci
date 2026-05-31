"""NASA GPM IMERG datasource: single-point precipitation series.

GPM IMERG (Integrated Multi-satellitE Retrievals for GPM) is NASA's ~0.1 deg
(~10 km) precipitation product. This datasource extracts a single grid cell per
day from the GES DISC OPeNDAP server using an ``.ascii`` constraint, so it never
downloads or parses HDF5/NetCDF granules and adds no heavy dependency (stdlib
only) — mirroring the point-series shape of ``NasaPowerDataSource``.

Security note: GES DISC requires an Earthdata Login bearer token. It is read
only from the ``GUARACI_EARTHDATA_TOKEN`` environment variable (or injected for
tests), never from job parameters (which are persisted to disk) and never
written to the manifest.

Status: EXPERIMENTAL / live-data-unvalidated. The OPeNDAP contract (endpoint,
granule naming, grid layout, index formula, ASCII grammar) was validated with a
real Earthdata token, but a successful data response additionally requires the
account to have authorized the "NASA GESDISC DATA ARCHIVE" application at
https://urs.earthdata.nasa.gov (Applications -> Authorized Apps). Until then
data requests return HTTP 401; the parser is covered by tests against the
documented OPeNDAP ASCII format.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.nasa.client import NasaGesDiscClient, NasaGesDiscClientError

_TOKEN_ENV = "GUARACI_EARTHDATA_TOKEN"
_MAX_DAYS = 372  # safety cap: one OPeNDAP request per day


class NasaGpmDataSource(DataSource):
    """NASA GPM IMERG daily precipitation for a single point via OPeNDAP."""

    DEFAULT_PRODUCT = "daily"
    DEFAULT_VARIABLE = "precipitation"
    DEFAULT_TIMEOUT = 120
    VALID_PRODUCTS = ("daily",)
    VALID_VARIABLES = (
        "precipitation",
        "MWprecipitation",
        "randomError",
        "precipitation_cnt",
    )
    # IMERG 0.1-degree grid (cell centers): lon -179.95..179.95 (3600),
    # lat -89.95..89.95 (1800); array order is precipitation[time][lon][lat].
    _LON0 = -179.95
    _LAT0 = -89.95
    _RES = 0.1
    _NLON = 3600
    _NLAT = 1800
    _FILL_THRESHOLD = -9000.0  # IMERG fill is ~ -9999.9; generic fill is -1e34

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[NasaGesDiscClient] = None,
        token: Optional[str] = None,
    ) -> None:
        super().__init__(name="nasa_gpm", output_path=output_path)
        self._client = client
        self._injected_token = token
        self._frame: pl.DataFrame = pl.DataFrame()

    def download(
        self,
        *,
        latitude: object,
        longitude: object,
        start_date: str,
        end_date: str,
        product: str = DEFAULT_PRODUCT,
        variable: str = DEFAULT_VARIABLE,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download a daily IMERG point precipitation series."""

        product_clean = self._normalize_product(product)
        variable_clean = self._normalize_variable(variable)
        lat = self._parse_coordinate(latitude, field_name="latitude", limit=90.0)
        lon = self._parse_coordinate(longitude, field_name="longitude", limit=180.0)
        start = self._parse_iso_date(start_date, field_name="start_date")
        end = self._parse_iso_date(end_date, field_name="end_date")
        if start > end:
            raise ValueError("Parameter 'start_date' cannot be after 'end_date'.")
        days = (end - start).days + 1
        if days > _MAX_DAYS:
            raise ValueError(
                f"Requested window spans {days} days; the daily IMERG point "
                f"extraction issues one request per day and is capped at "
                f"{_MAX_DAYS}. Use a shorter window."
            )

        lon_idx = self._clamp(round((lon - self._LON0) / self._RES), self._NLON)
        lat_idx = self._clamp(round((lat - self._LAT0) / self._RES), self._NLAT)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        dates = [start + timedelta(days=offset) for offset in range(days)]
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": len(dates),
                }
            )

        records: List[Dict[str, object]] = []
        raw_chunks: List[str] = []
        failed: List[str] = []
        for index, day in enumerate(dates):
            dataset_path = self._daily_dataset_path(day)
            constraint = f"{variable_clean}[0][{lon_idx}][{lat_idx}]"
            try:
                text = client.fetch_ascii(dataset_path, constraint)
            except NasaGesDiscClientError as exc:
                raise exc.with_context(
                    f"NASA GPM IMERG request failed for {day.isoformat()} "
                    f"at grid [{lon_idx}][{lat_idx}]"
                ) from exc
            if keep_raw:
                raw_chunks.append(f"# {day.isoformat()}\n{text}")
            value, grid_lat, grid_lon = self._parse_ascii(text, variable_clean)
            records.append(
                {
                    "date": day.isoformat(),
                    "year": day.year,
                    "month": day.month,
                    "day": day.day,
                    "latitude": grid_lat if grid_lat is not None else lat,
                    "longitude": grid_lon if grid_lon is not None else lon,
                    variable_clean: value,
                }
            )
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "documents_total": len(dates),
                        "document_index": index + 1,
                        "files_completed": index + 1,
                        "file_path": f"IMERGDF_{day.isoformat()}",
                    }
                )

        self._frame = pl.from_dicts(records) if records else pl.DataFrame()

        artifact_stem = self._build_artifact_stem(
            variable=variable_clean, latitude=lat, longitude=lon, start=start, end=end
        )
        raw_path: Optional[Path] = None
        if keep_raw and raw_chunks:
            raw_path = self._write_raw_snapshot(stem=artifact_stem, chunks=raw_chunks)

        requested_format = self._normalize_output_format(output_format)
        exported_files: List[str] = []
        warnings: List[str] = []
        if self._frame.height == 0:
            warnings.append("NASA GPM IMERG returned no data points for the window.")
        if requested_format and self._frame.height > 0:
            try:
                export_path = self.export(
                    self._frame, format=requested_format, name=artifact_stem
                )
                exported_files.append(str(export_path))
            except Exception as exc:  # noqa: BLE001 - reported as a warning
                warnings.append(f"NASA GPM export failed after download. Error: {exc}")
        elif not requested_format and not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            product=product_clean,
            variable=variable_clean,
            latitude=lat,
            longitude=lon,
            start=start,
            end=end,
            grid_index=(lon_idx, lat_idx),
            record_count=self._frame.height,
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
                    "documents_total": len(dates),
                    "downloaded_count": self._frame.height,
                    "failed_count": len(failed),
                    "skipped_count": 0,
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": self._frame.height,
            "downloaded_count": self._frame.height,
            "skipped_count": 0,
            "failed_count": len(failed),
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "product": product_clean,
            "variable": variable_clean,
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "grid_index": [lon_idx, lat_idx],
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw,
            "output_format": requested_format,
            "exported_files": exported_files,
        }
        export_warning = self._combine_warnings(warnings)
        if export_warning:
            payload["export_warning"] = export_warning
        return payload

    def load_dataframe(self) -> pl.DataFrame:
        """Return the most recent GPM download as a Polars DataFrame."""
        return self._frame

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
                    "nasa_gpm_records", connection, if_exists="replace", index=False
                )
            return path
        raise ValueError(
            f"Unsupported NASA GPM export format '{format}'. "
            "Allowed: csv, parquet, sqlite"
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_ascii(
        self, text: str, variable: str
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Parse an OPeNDAP ``.ascii`` Grid response for one point.

        The data array line is ``<var>.<var>[...], <value>``; the map vectors
        appear as ``<var>.lat``/``<var>.lon`` lines.
        """
        value: Optional[float] = None
        grid_lat: Optional[float] = None
        grid_lon: Optional[float] = None
        data_prefix = f"{variable}.{variable}"
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.lower().startswith("dataset:"):
                continue
            if line.startswith(data_prefix):
                value = self._clean_value(self._last_float(line))
            elif line.startswith(f"{variable}.lat"):
                grid_lat = self._last_float(line)
            elif line.startswith(f"{variable}.lon"):
                grid_lon = self._last_float(line)
        return value, grid_lat, grid_lon

    @staticmethod
    def _last_float(line: str) -> Optional[float]:
        parts = line.split(",")
        if len(parts) < 2:
            return None
        try:
            return float(parts[-1].strip())
        except ValueError:
            return None

    def _clean_value(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if value <= self._FILL_THRESHOLD:
            return None
        return value

    # ------------------------------------------------------------------
    # Granule path
    # ------------------------------------------------------------------
    @staticmethod
    def _daily_dataset_path(day: date) -> str:
        stamp = day.strftime("%Y%m%d")
        granule = (
            f"3B-DAY.MS.MRG.3IMERG.{stamp}-S000000-E235959.V07B.nc4"
        )
        return (
            f"/opendap/GPM_L3/GPM_3IMERGDF.07/{day.year:04d}/"
            f"{day.month:02d}/{granule}"
        )

    @staticmethod
    def _clamp(index: int, size: int) -> int:
        return max(0, min(int(index), size - 1))

    # ------------------------------------------------------------------
    # Validation / resolution helpers
    # ------------------------------------------------------------------
    def _resolve_token(self) -> str:
        candidate = self._injected_token or os.getenv(_TOKEN_ENV)
        if candidate and candidate.strip():
            return candidate.strip()
        raise ValueError(
            "NASA GPM (GES DISC) requires an Earthdata Login token. Set the "
            f"environment variable {_TOKEN_ENV} (generate at "
            "https://urs.earthdata.nasa.gov, and authorize the 'NASA GESDISC "
            "DATA ARCHIVE' application)."
        )

    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> NasaGesDiscClient:
        if self._client is not None:
            return self._client
        token = self._resolve_token()
        timeout_value = max(1, int(timeout))
        base = api_base_url.strip() if api_base_url and api_base_url.strip() else None
        return NasaGesDiscClient(
            token=token, base_url=base, timeout_seconds=timeout_value
        )

    def _normalize_product(self, product: str) -> str:
        cleaned = str(product).strip().lower()
        if cleaned not in self.VALID_PRODUCTS:
            raise ValueError(
                f"Parameter 'product' must be one of {', '.join(self.VALID_PRODUCTS)}."
            )
        return cleaned

    def _normalize_variable(self, variable: str) -> str:
        cleaned = str(variable).strip()
        if cleaned not in self.VALID_VARIABLES:
            allowed = ", ".join(self.VALID_VARIABLES)
            raise ValueError(
                f"Unsupported GPM variable '{variable}'. Allowed: {allowed}"
            )
        return cleaned

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

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    def _build_artifact_stem(
        self, *, variable: str, latitude: float, longitude: float, start: date, end: date
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lat_token = f"{latitude:.4f}".replace("-", "S").replace(".", "p")
        lon_token = f"{longitude:.4f}".replace("-", "W").replace(".", "p")
        return (
            f"nasa_gpm_{variable}_{lat_token}_{lon_token}_"
            f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{timestamp}"
        )

    def _write_raw_snapshot(self, *, stem: str, chunks: Sequence[str]) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        file_path = raw_dir / f"{stem}.txt"
        file_path.write_text("\n".join(chunks), encoding="utf-8")
        return file_path

    def _write_manifest(
        self,
        *,
        product: str,
        variable: str,
        latitude: float,
        longitude: float,
        start: date,
        end: date,
        grid_index: Tuple[int, int],
        record_count: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: Sequence[str],
        api_base_url: str,
        warnings: Sequence[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        # The Earthdata token is intentionally excluded from the manifest.
        request_filters: Dict[str, object] = {
            "product": product,
            "variable": variable,
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "grid_index": list(grid_index),
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
