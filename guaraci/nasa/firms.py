"""NASA FIRMS datasource: active-fire / thermal-anomaly detections.

FIRMS (Fire Information for Resource Management System) serves near-real-time
and standard-processing active-fire detections from MODIS and VIIRS. The CSV
endpoints require a free ``MAP_KEY``.

Security note: the MAP_KEY is a credential. It is read only from the
``GUARACI_FIRMS_MAP_KEY`` environment variable (or injected for tests), never
from job parameters (which are persisted to disk), and never written to the
manifest.

Naming note: the user-facing parameter is ``product`` (the FIRMS "source"
identifier such as ``VIIRS_SNPP_NRT``). It is deliberately not called
``source`` because ``DownloadService.run(source, **params)`` already reserves
that argument name.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.nasa.client import NasaFirmsClient, NasaFirmsClientError

_MAP_KEY_ENV = "GUARACI_FIRMS_MAP_KEY"
_MAX_DAY_RANGE = 10


class NasaFirmsDataSource(DataSource):
    """NASA FIRMS datasource for active-fire detections over a date window."""

    DEFAULT_PRODUCT = "VIIRS_SNPP_NRT"
    DEFAULT_COUNTRY = "BRA"
    DEFAULT_TIMEOUT = 120
    VALID_PRODUCTS = (
        "VIIRS_SNPP_NRT",
        "VIIRS_NOAA20_NRT",
        "VIIRS_NOAA21_NRT",
        "MODIS_NRT",
        "VIIRS_SNPP_SP",
        "MODIS_SP",
    )

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[NasaFirmsClient] = None,
        map_key: Optional[str] = None,
    ) -> None:
        super().__init__(name="nasa_firms", output_path=output_path)
        self._client = client
        self._injected_map_key = map_key
        self._frame: pl.DataFrame = pl.DataFrame()

    def download(
        self,
        *,
        start_date: str,
        end_date: str,
        product: str = DEFAULT_PRODUCT,
        country: str = DEFAULT_COUNTRY,
        area: Optional[str] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download FIRMS detections, chunked into <=10-day requests."""

        product_clean = self._normalize_product(product)
        start = self._parse_iso_date(start_date, field_name="start_date")
        end = self._parse_iso_date(end_date, field_name="end_date")
        if start > end:
            raise ValueError("Parameter 'start_date' cannot be after 'end_date'.")
        area_clean = self._normalize_area(area)
        country_clean = None if area_clean else self._normalize_country(country)
        region_label = (
            f"area:{area_clean}" if area_clean else f"country:{country_clean}"
        )
        map_key = self._resolve_map_key()
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)
        segments = self._build_segments(start, end)

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": len(segments),
                }
            )

        frames: List[pl.DataFrame] = []
        raw_chunks: List[str] = []
        for index, (seg_date, seg_len) in enumerate(segments):
            iso = seg_date.isoformat()
            try:
                if area_clean:
                    text = client.fetch_area_csv(
                        map_key=map_key,
                        source=product_clean,
                        area=area_clean,
                        day_range=seg_len,
                        date=iso,
                    )
                else:
                    text = client.fetch_country_csv(
                        map_key=map_key,
                        source=product_clean,
                        country=str(country_clean),
                        day_range=seg_len,
                        date=iso,
                    )
            except NasaFirmsClientError as exc:
                raise exc.with_context(
                    f"NASA FIRMS request failed for {product_clean} "
                    f"{region_label} window {iso} (+{seg_len}d)"
                ) from exc

            self._raise_if_error_payload(text, map_key=map_key)
            if keep_raw:
                raw_chunks.append(text)
            chunk = self._parse_csv_chunk(text, product=product_clean)
            if chunk is not None and chunk.height > 0:
                frames.append(chunk)

            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "documents_total": len(segments),
                        "document_index": index + 1,
                        "files_completed": index + 1,
                        "file_path": f"{product_clean}_{iso}_{seg_len}d",
                    }
                )

        self._frame = self._combine_frames(frames)

        artifact_stem = self._build_artifact_stem(
            product=product_clean,
            region_label=region_label,
            start=start,
            end=end,
        )
        raw_path: Optional[Path] = None
        if keep_raw and raw_chunks:
            raw_path = self._write_raw_snapshot(stem=artifact_stem, chunks=raw_chunks)

        requested_format = self._normalize_output_format(output_format)
        exported_files: List[str] = []
        warnings: List[str] = []
        if self._frame.height == 0:
            warnings.append(
                "NASA FIRMS returned no detections for the requested window and "
                "region. This is expected when there were no fires, or check the "
                "product, date window, and area/country."
            )
        if requested_format:
            if self._frame.height > 0:
                try:
                    export_path = self.export(
                        self._frame, format=requested_format, name=artifact_stem
                    )
                    exported_files.append(str(export_path))
                except Exception as exc:  # noqa: BLE001 - reported as a warning
                    warnings.append(
                        f"NASA FIRMS export failed after download. Error: {exc}"
                    )
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            product=product_clean,
            region_label=region_label,
            start=start,
            end=end,
            segments=len(segments),
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
                    "documents_total": len(segments),
                    "downloaded_count": self._frame.height,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": self._frame.height,
            "downloaded_count": self._frame.height,
            "skipped_count": 0,
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "firms_product": product_clean,
            "region": region_label,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "segments": len(segments),
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
        """Return the most recent FIRMS download as a Polars DataFrame."""
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
                    "nasa_firms_records",
                    connection,
                    if_exists="replace",
                    index=False,
                )
            return path
        raise ValueError(
            f"Unsupported NASA FIRMS export format '{format}'. "
            "Allowed: csv, parquet, sqlite"
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _raise_if_error_payload(text: str, *, map_key: str) -> None:
        head = text.lstrip()[:400].lower()
        if "latitude" in head and "longitude" in head:
            return
        redacted = text.replace(map_key, "***") if map_key else text
        snippet = redacted.strip().replace("\n", " ")[:220]
        raise NasaFirmsClientError(
            f"NASA FIRMS returned a non-CSV response: '{snippet}'.",
            category="configuration",
            hint=(
                "Verify the MAP_KEY (GUARACI_FIRMS_MAP_KEY), the product, and the "
                "area/country selection."
            ),
        )

    def _parse_csv_chunk(self, text: str, *, product: str) -> Optional[pl.DataFrame]:
        try:
            frame = pl.read_csv(io.StringIO(text))
        except Exception:
            return None
        if frame.height == 0:
            return frame
        return frame.with_columns(pl.lit(product).alias("firms_product"))

    @staticmethod
    def _combine_frames(frames: Sequence[pl.DataFrame]) -> pl.DataFrame:
        non_empty = [frame for frame in frames if frame.width > 0]
        if not non_empty:
            return pl.DataFrame()
        if len(non_empty) == 1:
            return non_empty[0]
        return pl.concat(non_empty, how="vertical_relaxed")

    @staticmethod
    def _build_segments(start: date, end: date) -> List[Tuple[date, int]]:
        segments: List[Tuple[date, int]] = []
        cursor = start
        while cursor <= end:
            remaining = (end - cursor).days + 1
            seg_len = min(_MAX_DAY_RANGE, remaining)
            segments.append((cursor, seg_len))
            cursor = cursor + timedelta(days=seg_len)
        return segments

    # ------------------------------------------------------------------
    # Validation / resolution helpers
    # ------------------------------------------------------------------
    def _resolve_map_key(self) -> str:
        candidate = self._injected_map_key or os.getenv(_MAP_KEY_ENV)
        if candidate and candidate.strip():
            return candidate.strip()
        raise ValueError(
            "NASA FIRMS requires a MAP_KEY. Set the environment variable "
            f"{_MAP_KEY_ENV} (free key from "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/)."
        )

    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> NasaFirmsClient:
        timeout_value = max(1, int(timeout))
        if api_base_url and api_base_url.strip():
            return NasaFirmsClient(
                base_url=api_base_url.strip(), timeout_seconds=timeout_value
            )
        if self._client is not None:
            return self._client
        return NasaFirmsClient(timeout_seconds=timeout_value)

    def _normalize_product(self, product: str) -> str:
        cleaned = str(product).strip().upper()
        if cleaned not in self.VALID_PRODUCTS:
            allowed = ", ".join(self.VALID_PRODUCTS)
            raise ValueError(
                f"Unsupported FIRMS product '{product}'. Allowed: {allowed}"
            )
        return cleaned

    @staticmethod
    def _normalize_country(country: str) -> str:
        cleaned = str(country).strip().upper()
        if len(cleaned) != 3 or not cleaned.isalpha():
            raise ValueError(
                "Parameter 'country' must be a 3-letter ISO code (for example BRA)."
            )
        return cleaned

    @staticmethod
    def _normalize_area(area: Optional[str]) -> Optional[str]:
        if area is None:
            return None
        cleaned = str(area).strip()
        if not cleaned:
            return None
        if cleaned.lower() == "world":
            return "world"
        parts = [piece.strip() for piece in cleaned.split(",")]
        if len(parts) != 4:
            raise ValueError(
                "Parameter 'area' must be 'world' or a bounding box "
                "'west,south,east,north'."
            )
        try:
            west, south, east, north = (float(piece) for piece in parts)
        except ValueError as exc:
            raise ValueError(
                "Parameter 'area' bounding box must contain four decimal numbers."
            ) from exc
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise ValueError("Parameter 'area' longitudes must be between -180 and 180.")
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            raise ValueError("Parameter 'area' latitudes must be between -90 and 90.")
        if west >= east or south >= north:
            raise ValueError(
                "Parameter 'area' must satisfy west < east and south < north."
            )
        return f"{west},{south},{east},{north}"

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
        self, *, product: str, region_label: str, start: date, end: date
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        region_token = region_label.replace(":", "_").replace(",", "_")
        return (
            f"nasa_firms_{product}_{region_token}_"
            f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{timestamp}"
        )

    def _write_raw_snapshot(self, *, stem: str, chunks: Sequence[str]) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        file_path = raw_dir / f"{stem}.csv"
        file_path.write_text("\n".join(chunks), encoding="utf-8")
        return file_path

    def _write_manifest(
        self,
        *,
        product: str,
        region_label: str,
        start: date,
        end: date,
        segments: int,
        record_count: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: Sequence[str],
        api_base_url: str,
        warnings: Sequence[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        # The MAP_KEY is intentionally excluded from persisted manifest filters.
        request_filters: Dict[str, object] = {
            "firms_product": product,
            "region": region_label,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "segments": segments,
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
