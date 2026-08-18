"""INPE Queimadas (BDQueimadas) datasource: fire-spot detections for Brazil.

Serves the "focos de queimada" reference product published by INPE's fire
monitoring program at ``dataserver-coids.inpe.br``. Two file families are
exposed:

- **Annual** (``anual/Brasil_sat_ref`` or ``anual/Brasil_todos_sats``): one
  ZIP per year, Brazil-wide, years 2003+ confirmed live. ``Brasil_sat_ref``
  is the reference-satellite product (one detection series per year, stable
  methodology); ``Brasil_todos_sats`` merges detections from every satellite
  INPE ingests (more rows, mixed sensor characteristics).
- **Monthly** (``mensal/Brasil``): one file per calendar month, only
  available from 2023 onward, with a DIFFERENT schema (it is INPE's blended
  near-real-time product, not the annual reference series) - includes
  ``risco_fogo``, ``frp``, ``precipitacao`` and ``numero_dias_sem_chuva``
  that the annual files do not have. Requesting ``months`` intentionally
  switches to this product; ``dataset`` is ignored in that mode (documented
  in the ``months`` parameter description on the source schema).

Both schemas share ``estado``/``municipio`` columns (full Portuguese names,
not UF codes), which is what the ``states`` filter matches against.

Complements (does not replace) ``nasa_firms``: FIRMS is NASA's near-real-time
MODIS/VIIRS feed with global coverage; INPE Queimadas is Brazil's own
national program, using its own satellite-reference methodology and
including ``bioma``/``municipio`` classification INPE derives locally.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.inpe.client import InpeQueimadasClient, InpeQueimadasClientError

# UF (2-letter) -> full state name as used in the "estado" column of both
# the annual and monthly INPE Queimadas products.
UF_TO_STATE: Dict[str, str] = {
    "AC": "ACRE",
    "AL": "ALAGOAS",
    "AP": "AMAPÁ",
    "AM": "AMAZONAS",
    "BA": "BAHIA",
    "CE": "CEARÁ",
    "DF": "DISTRITO FEDERAL",
    "ES": "ESPÍRITO SANTO",
    "GO": "GOIÁS",
    "MA": "MARANHÃO",
    "MT": "MATO GROSSO",
    "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS",
    "PA": "PARÁ",
    "PB": "PARAÍBA",
    "PR": "PARANÁ",
    "PE": "PERNAMBUCO",
    "PI": "PIAUÍ",
    "RJ": "RIO DE JANEIRO",
    "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL",
    "RO": "RONDÔNIA",
    "RR": "RORAIMA",
    "SC": "SANTA CATARINA",
    "SP": "SÃO PAULO",
    "SE": "SERGIPE",
    "TO": "TOCANTINS",
}
_VALID_STATE_NAMES = frozenset(UF_TO_STATE.values())

_NUMERIC_FLOAT_COLUMNS = {"lat", "lon", "frp", "precipitacao"}
_NUMERIC_INT_COLUMNS = {
    "id_bdq",
    "municipio_id",
    "estado_id",
    "pais_id",
    "numero_dias_sem_chuva",
    "risco_fogo",
}

_MONTHLY_FILE_RE = re.compile(r"^focos_mensal_br_(\d{4})(\d{2})\.(zip|csv)$")
_ANNUAL_YEAR_RE = re.compile(r"(\d{4})\.zip$")


class InpeQueimadasDataSource(DataSource):
    """INPE Queimadas datasource for annual/monthly fire-spot extracts."""

    DEFAULT_TIMEOUT = 180
    MIN_YEAR = 2003
    DEFAULT_DATASET = "referencia_anual"
    VALID_DATASETS = ("referencia_anual", "todos_satelites")

    # dataset key -> (index directory, filename pattern with {year})
    _ANNUAL_DIRS: Dict[str, Tuple[str, str]] = {
        "referencia_anual": ("anual/Brasil_sat_ref", "focos_br_ref_{year}.zip"),
        "todos_satelites": (
            "anual/Brasil_todos_sats",
            "focos_br_todos-sats_{year}.zip",
        ),
    }
    _MONTHLY_DIR = "mensal/Brasil"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[InpeQueimadasClient] = None,
    ) -> None:
        super().__init__(name="inpe_queimadas", output_path=output_path)
        self._client = client
        self._frame: pl.DataFrame = pl.DataFrame()

    def download(
        self,
        *,
        start_year: object,
        end_year: Optional[object] = None,
        months: Optional[Sequence[object]] = None,
        dataset: str = DEFAULT_DATASET,
        states: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download fire-spot detections for a year range (optionally by month)."""

        dataset_clean = self._normalize_dataset(dataset)
        y0 = self._parse_year(start_year, field_name="start_year")
        y1 = self._parse_year(end_year, field_name="end_year") if end_year is not None else y0
        if y0 > y1:
            raise ValueError("Parameter 'start_year' cannot be after 'end_year'.")
        if y0 < self.MIN_YEAR:
            raise ValueError(
                f"Parameter 'start_year' must be >= {self.MIN_YEAR} "
                "(no INPE Queimadas reference data published before that year)."
            )
        months_clean = self._normalize_months(months)
        states_clean = self._normalize_states(states)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)
        years = list(range(y0, y1 + 1))

        if months_clean:
            targets, warnings = self._resolve_monthly_targets(client, years, months_clean)
            product_label = "mensal"
        else:
            targets, warnings = self._resolve_annual_targets(client, years, dataset_clean)
            product_label = dataset_clean

        total = len(targets)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": total}
            )

        frames: List[pl.DataFrame] = []
        raw_snapshots: Dict[str, bytes] = {}
        files_used: List[str] = []
        for index, (remote_path, label, is_monthly) in enumerate(targets, start=1):
            try:
                raw_bytes = client.fetch_bytes(remote_path)
            except InpeQueimadasClientError as exc:
                raise exc.with_context(
                    f"INPE Queimadas request failed for {label}"
                ) from exc
            if keep_raw:
                raw_snapshots[label] = raw_bytes
            files_used.append(remote_path.rsplit("/", 1)[-1])
            chunk = self._parse_payload(raw_bytes, filename=remote_path, is_monthly=is_monthly)
            if chunk is not None and chunk.height > 0:
                frames.append(
                    chunk.with_columns(
                        pl.lit("mensal" if is_monthly else dataset_clean).alias(
                            "queimadas_produto"
                        )
                    )
                )
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "documents_total": total,
                        "document_index": index,
                        "files_completed": index,
                        "file_path": label,
                    }
                )

        combined = self._combine_frames(frames)
        if states_clean:
            combined = self._filter_states(combined, states_clean)
        self._frame = combined

        artifact_stem = self._build_artifact_stem(
            product=product_label, start_year=y0, end_year=y1
        )
        raw_path: Optional[Path] = None
        if keep_raw and raw_snapshots:
            raw_path = self._write_raw_snapshot(stem=artifact_stem, snapshots=raw_snapshots)

        requested_format = self._normalize_output_format(output_format)
        exported_files: List[str] = []
        if self._frame.height == 0:
            warnings.append(
                "INPE Queimadas returned no detections for the requested "
                "years/months/states."
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
                        f"INPE Queimadas export failed after download. Error: {exc}"
                    )
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            dataset=dataset_clean,
            months=months_clean,
            states=states_clean,
            start_year=y0,
            end_year=y1,
            record_count=self._frame.height,
            files_used=files_used,
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
                    "documents_total": total,
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
            "dataset": dataset_clean,
            "months": months_clean,
            "start_year": y0,
            "end_year": y1,
            "files_used": files_used,
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
        """Return the most recent INPE Queimadas download as a Polars DataFrame."""
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
                    "inpe_queimadas_records",
                    connection,
                    if_exists="replace",
                    index=False,
                )
            return path
        raise ValueError(
            f"Unsupported INPE Queimadas export format '{format}'. "
            "Allowed: csv, parquet, sqlite"
        )

    # ------------------------------------------------------------------
    # Discovery helpers (parse the index, never hardcode year lists)
    # ------------------------------------------------------------------
    def _resolve_annual_targets(
        self, client: InpeQueimadasClient, years: Sequence[int], dataset: str
    ) -> Tuple[List[Tuple[str, str, bool]], List[str]]:
        dir_path, pattern = self._ANNUAL_DIRS[dataset]
        try:
            listing = client.list_directory(dir_path)
        except InpeQueimadasClientError as exc:
            raise exc.with_context(
                f"INPE Queimadas directory listing failed for '{dir_path}'"
            ) from exc
        available_years = set()
        for name in listing:
            match = _ANNUAL_YEAR_RE.search(name)
            if match:
                available_years.add(int(match.group(1)))

        targets: List[Tuple[str, str, bool]] = []
        warnings: List[str] = []
        for year in years:
            if year not in available_years:
                warnings.append(
                    f"INPE Queimadas: year {year} not published under "
                    f"'{dir_path}', skipped."
                )
                continue
            filename = pattern.format(year=year)
            targets.append((f"{dir_path}/{filename}", f"{dataset}_{year}", False))
        return targets, warnings

    def _resolve_monthly_targets(
        self, client: InpeQueimadasClient, years: Sequence[int], months: Sequence[int]
    ) -> Tuple[List[Tuple[str, str, bool]], List[str]]:
        try:
            listing = client.list_directory(self._MONTHLY_DIR)
        except InpeQueimadasClientError as exc:
            raise exc.with_context(
                f"INPE Queimadas directory listing failed for '{self._MONTHLY_DIR}'"
            ) from exc
        available: Dict[Tuple[int, int], str] = {}
        for name in listing:
            match = _MONTHLY_FILE_RE.match(name)
            if match:
                year, month = int(match.group(1)), int(match.group(2))
                # prefer .zip if both extensions somehow exist
                key = (year, month)
                if key not in available or name.endswith(".zip"):
                    available[key] = name

        targets: List[Tuple[str, str, bool]] = []
        warnings: List[str] = []
        for year in years:
            for month in months:
                key = (year, month)
                filename = available.get(key)
                if filename is None:
                    warnings.append(
                        f"INPE Queimadas: monthly file for {year}-{month:02d} not "
                        f"available under '{self._MONTHLY_DIR}' (monthly product "
                        "starts in 2023), skipped."
                    )
                    continue
                targets.append(
                    (f"{self._MONTHLY_DIR}/{filename}", f"mensal_{year}{month:02d}", True)
                )
        return targets, warnings

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _parse_payload(
        self, raw_bytes: bytes, *, filename: str, is_monthly: bool
    ) -> Optional[pl.DataFrame]:
        csv_bytes = self._extract_csv_bytes(raw_bytes, filename=filename)
        try:
            frame = pl.read_csv(io.BytesIO(csv_bytes), infer_schema_length=0)
        except Exception:
            return None
        if frame.height == 0:
            return frame
        return self._coerce_numeric(frame)

    @staticmethod
    def _extract_csv_bytes(raw_bytes: bytes, *, filename: str) -> bytes:
        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
                names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
                target = names[0] if names else archive.namelist()[0]
                with archive.open(target) as member:
                    return member.read()
        return raw_bytes

    @staticmethod
    def _coerce_numeric(frame: pl.DataFrame) -> pl.DataFrame:
        string_cols = [
            name
            for name, dtype in frame.schema.items()
            if dtype == pl.Utf8
        ]
        if string_cols:
            frame = frame.with_columns(
                [pl.col(name).str.strip_chars() for name in string_cols]
            )
        casts = []
        for name in frame.columns:
            if name in _NUMERIC_FLOAT_COLUMNS:
                casts.append(pl.col(name).cast(pl.Float64, strict=False))
            elif name in _NUMERIC_INT_COLUMNS:
                casts.append(pl.col(name).cast(pl.Int64, strict=False))
        if casts:
            frame = frame.with_columns(casts)
        return frame

    @staticmethod
    def _combine_frames(frames: Sequence[pl.DataFrame]) -> pl.DataFrame:
        non_empty = [frame for frame in frames if frame.width > 0]
        if not non_empty:
            return pl.DataFrame()
        if len(non_empty) == 1:
            return non_empty[0]
        return pl.concat(non_empty, how="diagonal_relaxed")

    @staticmethod
    def _filter_states(frame: pl.DataFrame, states: frozenset) -> pl.DataFrame:
        if frame.height == 0 or "estado" not in frame.columns:
            return frame
        return frame.filter(pl.col("estado").str.to_uppercase().is_in(list(states)))

    # ------------------------------------------------------------------
    # Validation / resolution helpers
    # ------------------------------------------------------------------
    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> InpeQueimadasClient:
        timeout_value = max(1, int(timeout))
        if api_base_url and api_base_url.strip():
            return InpeQueimadasClient(
                base_url=api_base_url.strip(), timeout_seconds=timeout_value
            )
        if self._client is not None:
            return self._client
        return InpeQueimadasClient(timeout_seconds=timeout_value)

    def _normalize_dataset(self, dataset: str) -> str:
        cleaned = str(dataset).strip().lower()
        if cleaned not in self.VALID_DATASETS:
            allowed = ", ".join(self.VALID_DATASETS)
            raise ValueError(f"Unsupported dataset '{dataset}'. Allowed: {allowed}")
        return cleaned

    @staticmethod
    def _parse_year(value: object, *, field_name: str) -> int:
        try:
            year = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{field_name}' must be an integer year.") from exc
        if year < 1900 or year > 2100:
            raise ValueError(f"Parameter '{field_name}' must be a plausible year.")
        return year

    @staticmethod
    def _normalize_months(value: Optional[Sequence[object]]) -> Optional[List[int]]:
        if not value:
            return None
        months: List[int] = []
        for item in value:
            try:
                month = int(str(item).strip())
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Parameter 'months' entries must be integers 1-12 (got {item!r})."
                ) from exc
            if month < 1 or month > 12:
                raise ValueError(
                    f"Parameter 'months' entries must be between 1 and 12 (got {month})."
                )
            if month not in months:
                months.append(month)
        return sorted(months) or None

    @staticmethod
    def _normalize_states(value: Optional[Sequence[str]]) -> Optional[frozenset]:
        if not value:
            return None
        resolved: List[str] = []
        for item in value:
            cleaned = str(item).strip().upper()
            if not cleaned:
                continue
            if cleaned in UF_TO_STATE:
                resolved.append(UF_TO_STATE[cleaned])
            elif cleaned in _VALID_STATE_NAMES:
                resolved.append(cleaned)
            else:
                allowed = ", ".join(sorted(UF_TO_STATE))
                raise ValueError(
                    f"Unsupported state '{item}'. Use a UF code ({allowed}) or "
                    "the full state name."
                )
        return frozenset(resolved) or None

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
    def _build_artifact_stem(self, *, product: str, start_year: int, end_year: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"inpe_queimadas_{product}_{start_year}_{end_year}_{timestamp}"

    def _write_raw_snapshot(self, *, stem: str, snapshots: Dict[str, bytes]) -> Path:
        raw_dir = self.output_path / "raw" / stem
        raw_dir.mkdir(parents=True, exist_ok=True)
        for label, raw_bytes in snapshots.items():
            safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
            (raw_dir / f"{safe_label}.bin").write_bytes(raw_bytes)
        return raw_dir

    def _write_manifest(
        self,
        *,
        dataset: str,
        months: Optional[List[int]],
        states: Optional[frozenset],
        start_year: int,
        end_year: int,
        record_count: int,
        files_used: Sequence[str],
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: Sequence[str],
        api_base_url: str,
        warnings: Sequence[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        request_filters: Dict[str, object] = {
            "dataset": dataset,
            "months": months,
            "states": sorted(states) if states else None,
            "start_year": start_year,
            "end_year": end_year,
            "files_used": list(files_used),
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
