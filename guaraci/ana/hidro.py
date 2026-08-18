"""ANA / SNIRH HidroWebService datasource: telemetric station series.

Status: EXPERIMENTAL / live-data-unvalidated (same status tag used by
``guaraci/nasa/gpm.py``). The operator's ANA credential registration
(identifier + password, requested by e-mail per the official manual) was
still pending when this module was written, so nothing here has been
exercised against a live payload. What IS locked, from a live read of the
public OpenAPI document at ``https://www.ana.gov.br/hidrowebservice/api-docs``
on 2026-08-18 (see ``guaraci/ana/client.py`` module docstring for the full
list of confirmed facts):

- endpoint paths, the OAuth header contract, the bearer-token security
  scheme, and the exact (Portuguese, accented) query parameter names of the
  two telemetric series endpoints;
- the 30-day-per-request ceiling on those endpoints (via the ``Range
  Intervalo de busca`` enum, whose largest bucket is ``DIAS_30``).

What is NOT locked, because the OpenAPI document types the response payload
(``Devolucao.items``) as an opaque ``object`` with no published field names,
and no credentials were available to inspect a real response:

- the exact field names inside each telemetric reading (rain/level/flow
  columns, timestamp column name and format).

Consequently this datasource does not hardcode a wide-format column layout.
Each raw record returned by the API is flattened into a row with
snake_cased column names taken as-is from the response, plus request
metadata columns (``station_id``, ``variable``, ``detail``, ``chunk_start``,
``chunk_end``) and a best-effort ``timestamp`` column detected by scanning
the record's keys for date/time-shaped names. One row is produced per raw
API record, which the ANA API itself already scopes to one
(estação, leitura) pair — i.e. this *should* be the tidy 1-row-per
(station, timestamp) shape the integration plan calls for, but the exact
column names must be re-verified against a live payload once the operator's
ANA credentials exist (via ``GUARACI_ANA_SMOKE=1``).

Credential handling mirrors NASA/IBGE: read only from
``GUARACI_ANA_ID``/``GUARACI_ANA_SENHA`` (or injected for tests), never from
job parameters (which are persisted to disk) and never written to the
manifest.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.ana.client import AnaHidroClient, AnaHidroClientError
from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource

_ID_ENV = "GUARACI_ANA_ID"
_SENHA_ENV = "GUARACI_ANA_SENHA"
_MAX_WINDOW_DAYS = 30
_MAX_TOTAL_DAYS = 366 * 5  # safety cap: ~5 years, well beyond a single job
# Kept as a plain constant (not a lookup on the injected client's class) so a
# test double for AnaHidroClient does not need to mirror its class attributes.
_RANGE_MAX_DAYS = "DIAS_30"


class AnaHidroDataSource(DataSource):
    """ANA HidroWebService telemetric series for one or more stations."""

    DEFAULT_DETAIL = "adotada"
    DEFAULT_TIPO_FILTRO_DATA = "DATA_LEITURA"
    DEFAULT_TIMEOUT = 120
    VALID_VARIABLES = ("chuvas", "vazoes", "cotas")
    VALID_DETAILS = AnaHidroClient.VALID_DETAIL
    VALID_TIPO_FILTRO_DATA = AnaHidroClient.VALID_TIPO_FILTRO_DATA

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[AnaHidroClient] = None,
        identificador: Optional[str] = None,
        senha: Optional[str] = None,
    ) -> None:
        super().__init__(name="ana_hidro", output_path=output_path)
        self._client = client
        self._injected_id = identificador
        self._injected_senha = senha
        self._frame: pl.DataFrame = pl.DataFrame()

    def download(
        self,
        *,
        station_ids: Sequence[object],
        start_date: str,
        end_date: str,
        variable: str,
        detail: str = DEFAULT_DETAIL,
        tipo_filtro_data: str = DEFAULT_TIPO_FILTRO_DATA,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download telemetric series for the given stations and window."""

        stations = self._normalize_station_ids(station_ids)
        variable_clean = self._normalize_variable(variable)
        detail_clean = self._normalize_detail(detail)
        tipo_clean = self._normalize_tipo_filtro_data(tipo_filtro_data)
        start = self._parse_iso_date(start_date, field_name="start_date")
        end = self._parse_iso_date(end_date, field_name="end_date")
        if start > end:
            raise ValueError("Parameter 'start_date' cannot be after 'end_date'.")
        total_days = (end - start).days + 1
        if total_days > _MAX_TOTAL_DAYS:
            raise ValueError(
                f"Requested window spans {total_days} days, above the "
                f"{_MAX_TOTAL_DAYS}-day safety cap. Use a shorter window or "
                "split the request."
            )

        windows = self._chunk_windows(start, end, max_days=_MAX_WINDOW_DAYS)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        total_calls = len(stations) * len(windows)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": total_calls,
                }
            )

        records: List[Dict[str, object]] = []
        raw_chunks: List[str] = []
        failed: List[str] = []
        call_index = 0
        for station_id in stations:
            for chunk_start, chunk_end in windows:
                call_index += 1
                try:
                    items = client.serie_telemetrica(
                        station_id=station_id,
                        detail=detail_clean,
                        data_busca=chunk_end.isoformat(),
                        tipo_filtro_data=tipo_clean,
                        range_intervalo=_RANGE_MAX_DAYS,
                    )
                except AnaHidroClientError as exc:
                    failed.append(f"{station_id}:{chunk_start.isoformat()}")
                    raise exc.with_context(
                        f"ANA HidroWebService request failed for station "
                        f"{station_id}, window {chunk_start.isoformat()}.."
                        f"{chunk_end.isoformat()}"
                    ) from exc
                if keep_raw and items:
                    raw_chunks.append(
                        f"# station={station_id} "
                        f"window={chunk_start.isoformat()}..{chunk_end.isoformat()}\n"
                        + json.dumps(items, ensure_ascii=False)
                    )
                for item in items:
                    records.append(
                        self._flatten_record(
                            item,
                            station_id=station_id,
                            variable=variable_clean,
                            detail=detail_clean,
                            chunk_start=chunk_start,
                            chunk_end=chunk_end,
                        )
                    )
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "file_completed",
                            "source": self.name,
                            "documents_total": total_calls,
                            "document_index": call_index,
                            "files_completed": call_index,
                            "file_path": (
                                f"ana_hidro_{station_id}_"
                                f"{chunk_start.isoformat()}_{chunk_end.isoformat()}"
                            ),
                        }
                    )

        self._frame = pl.from_dicts(records) if records else pl.DataFrame()

        artifact_stem = self._build_artifact_stem(
            variable=variable_clean, detail=detail_clean, start=start, end=end
        )
        raw_path: Optional[Path] = None
        if keep_raw and raw_chunks:
            raw_path = self._write_raw_snapshot(stem=artifact_stem, chunks=raw_chunks)

        requested_format = self._normalize_output_format(output_format)
        exported_files: List[str] = []
        warnings: List[str] = []
        if self._frame.height == 0:
            warnings.append(
                "ANA HidroWebService returned no records for the requested "
                "stations/window."
            )
        warnings.append(
            "Response field names are unverified live (no ANA credential "
            "was available during implementation); columns are passed "
            "through as returned by the API, snake_cased."
        )
        if requested_format and self._frame.height > 0:
            try:
                export_path = self.export(
                    self._frame, format=requested_format, name=artifact_stem
                )
                exported_files.append(str(export_path))
            except Exception as exc:  # noqa: BLE001 - reported as a warning
                warnings.append(f"ANA HidroWebService export failed after download. Error: {exc}")
        elif not requested_format and not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and "
                "output_format is empty). Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            stations=stations,
            variable=variable_clean,
            detail=detail_clean,
            tipo_filtro_data=tipo_clean,
            start=start,
            end=end,
            windows=windows,
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
                    "documents_total": total_calls,
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
            "station_ids": stations,
            "variable": variable_clean,
            "detail": detail_clean,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "windows": [
                [chunk_start.isoformat(), chunk_end.isoformat()]
                for chunk_start, chunk_end in windows
            ],
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
        """Return the most recent ANA HidroWebService download as a DataFrame."""
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
                    "ana_hidro_records", connection, if_exists="replace", index=False
                )
            return path
        raise ValueError(
            f"Unsupported ANA HidroWebService export format '{format}'. "
            "Allowed: csv, parquet, sqlite"
        )

    # ------------------------------------------------------------------
    # Windowing
    # ------------------------------------------------------------------
    @staticmethod
    def _chunk_windows(
        start: date, end: date, *, max_days: int
    ) -> List[Tuple[date, date]]:
        chunks: List[Tuple[date, date]] = []
        cursor = start
        step = timedelta(days=max_days - 1)
        while cursor <= end:
            chunk_end = min(cursor + step, end)
            chunks.append((cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        return chunks

    # ------------------------------------------------------------------
    # Record flattening
    # ------------------------------------------------------------------
    _TIMESTAMP_HINTS = ("hora", "leitura", "medicao", "atualizacao", "timestamp")

    @classmethod
    def _flatten_record(
        cls,
        item: Dict[str, object],
        *,
        station_id: str,
        variable: str,
        detail: str,
        chunk_start: date,
        chunk_end: date,
    ) -> Dict[str, object]:
        row: Dict[str, object] = {
            "station_id": station_id,
            "variable": variable,
            "detail": detail,
            "chunk_start": chunk_start.isoformat(),
            "chunk_end": chunk_end.isoformat(),
            "timestamp": cls._detect_timestamp(item),
        }
        for key, value in item.items():
            row[_snake_case(str(key))] = value
        return row

    @classmethod
    def _detect_timestamp(cls, item: Dict[str, object]) -> Optional[object]:
        best: Optional[object] = None
        for key, value in item.items():
            snake = _snake_case(str(key))
            if "data" in snake and any(hint in snake for hint in cls._TIMESTAMP_HINTS):
                return value
            if snake == "data" and best is None:
                best = value
        return best

    # ------------------------------------------------------------------
    # Validation / resolution helpers
    # ------------------------------------------------------------------
    def _resolve_identificador(self) -> str:
        candidate = self._injected_id or os.getenv(_ID_ENV)
        if candidate and candidate.strip():
            return candidate.strip()
        raise ValueError(
            "ANA HidroWebService requires an identifier. Set the "
            f"environment variable {_ID_ENV} (obtained by e-mail "
            "registration with ANA per the HidroWebService manual)."
        )

    def _resolve_senha(self) -> str:
        candidate = self._injected_senha or os.getenv(_SENHA_ENV)
        if candidate and candidate.strip():
            return candidate.strip()
        raise ValueError(
            "ANA HidroWebService requires a password. Set the environment "
            f"variable {_SENHA_ENV} (obtained by e-mail registration with "
            "ANA per the HidroWebService manual)."
        )

    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> AnaHidroClient:
        if self._client is not None:
            return self._client
        identificador = self._resolve_identificador()
        senha = self._resolve_senha()
        timeout_value = max(1, int(timeout))
        base = api_base_url.strip() if api_base_url and api_base_url.strip() else None
        return AnaHidroClient(
            identificador=identificador,
            senha=senha,
            base_url=base,
            timeout_seconds=timeout_value,
        )

    @staticmethod
    def _normalize_station_ids(value: Sequence[object]) -> List[str]:
        if value is None or isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError(
                "Parameter 'station_ids' must be a non-empty list of station codes."
            )
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError(
                "Parameter 'station_ids' must be a non-empty list of station codes."
            )
        return cleaned

    def _normalize_variable(self, variable: str) -> str:
        cleaned = str(variable).strip().lower()
        if cleaned not in self.VALID_VARIABLES:
            raise ValueError(
                f"Unsupported 'variable' value '{variable}'. Allowed: "
                f"{', '.join(self.VALID_VARIABLES)}"
            )
        return cleaned

    def _normalize_detail(self, detail: str) -> str:
        cleaned = str(detail).strip().lower()
        if cleaned not in self.VALID_DETAILS:
            raise ValueError(
                f"Unsupported 'detail' value '{detail}'. Allowed: "
                f"{', '.join(self.VALID_DETAILS)}"
            )
        return cleaned

    def _normalize_tipo_filtro_data(self, value: str) -> str:
        cleaned = str(value).strip().upper()
        if cleaned not in self.VALID_TIPO_FILTRO_DATA:
            raise ValueError(
                f"Unsupported 'tipo_filtro_data' value '{value}'. Allowed: "
                f"{', '.join(self.VALID_TIPO_FILTRO_DATA)}"
            )
        return cleaned

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
        self, *, variable: str, detail: str, start: date, end: date
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return (
            f"ana_hidro_{variable}_{detail}_"
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
        stations: Sequence[str],
        variable: str,
        detail: str,
        tipo_filtro_data: str,
        start: date,
        end: date,
        windows: Sequence[Tuple[date, date]],
        record_count: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: Sequence[str],
        api_base_url: str,
        warnings: Sequence[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        # Credentials are intentionally excluded from the manifest.
        request_filters: Dict[str, object] = {
            "station_ids": list(stations),
            "variable": variable,
            "detail": detail,
            "tipo_filtro_data": tipo_filtro_data,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "windows": [[cs.isoformat(), ce.isoformat()] for cs, ce in windows],
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


def _snake_case(key: str) -> str:
    """Best-effort snake_case for arbitrary (possibly accented) API keys."""
    normalized = unicodedata.normalize("NFKD", key)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    snake = re.sub(r"[^0-9a-zA-Z]+", "_", ascii_only).strip("_").lower()
    return snake or "field"
