"""OpenDataSUS datasource for MVP dataset ingestion and export."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.opendatasus.client import OpenDataSUSClient, OpenDataSUSClientError
from guaraci.opendatasus.utils.swagger_catalog import (
    DemasPniEndpoint,
    load_local_get_params_catalog,
    load_local_pni_catalog,
)


@dataclass(frozen=True)
class OpenDataSUSDatasetSpec:
    """Dataset-level metadata used for query generation."""

    package_id: str
    preferred_resource_terms: tuple[str, ...]
    date_column: str
    uf_column: str
    demas_strategy: str = "pni_yearly"
    demas_static_path: Optional[str] = None
    ckan_supported: bool = True


@dataclass(frozen=True)
class DemasEndpointPlan:
    """Resolved DEMAS endpoint details for one download run."""

    path: str
    label: str
    uf_params: tuple[str, ...]
    query_params: Dict[str, object] = field(default_factory=dict)


class OpenDataSUSDataSource(DataSource):
    """OpenDataSUS datasource supporting CKAN and DEMAS vaccination APIs."""

    DEFAULT_DATASET = "doses_aplicadas_pni"
    DEFAULT_MAX_PAGES = 250
    LOCAL_SWAGGER_PATH = Path(__file__).resolve().parent / "utils" / "swagger.json"
    DATASET_SPECS: Dict[str, OpenDataSUSDatasetSpec] = {
        "doses_aplicadas_pni": OpenDataSUSDatasetSpec(
            package_id="covid-19-vacinacao",
            preferred_resource_terms=("vacinacao", "vacina", "covid"),
            date_column="data_vacina",
            uf_column="uf_estabelecimento",
        ),
        "zikavirus": OpenDataSUSDatasetSpec(
            package_id="arboviroses-zikavirus",
            preferred_resource_terms=("zikavirus", "zika", "arboviroses"),
            date_column="dt_notific",
            uf_column="sg_uf_not",
            demas_strategy="static",
            demas_static_path="/arboviroses/zikavirus",
            ckan_supported=False,
        ),
    }

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[OpenDataSUSClient] = None,
    ) -> None:
        super().__init__(name="opendatasus", output_path=output_path)
        self._client = client
        self._data_by_dataset: Dict[str, List[Dict[str, object]]] = {}
        self._latest_dataset: Optional[str] = None
        self._demas_catalog = load_local_pni_catalog(self.LOCAL_SWAGGER_PATH)
        self._demas_get_params_by_path = load_local_get_params_catalog(self.LOCAL_SWAGGER_PATH)

    def download(
        self,
        dataset: str,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        uf: Optional[str] = None,
        batch_size: int = 1000,
        output_format: Optional[str] = None,
        resource_id: Optional[str] = None,
        api_base_url: Optional[str] = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        keep_raw: bool = False,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        """Download records from one configured OpenDataSUS dataset."""

        dataset_key = dataset.strip().lower()
        spec = self.DATASET_SPECS.get(dataset_key)
        if spec is None:
            supported = ", ".join(sorted(self.DATASET_SPECS))
            raise ValueError(
                f"Unsupported OpenDataSUS dataset '{dataset}'. Supported: {supported}"
            )

        start_year_value, end_year_value = self._normalize_year_window(
            start_year=start_year,
            end_year=end_year,
        )
        range_start = date(start_year_value, 1, 1)
        range_end = date(end_year_value, 12, 31)
        start = self._parse_optional_iso_date(start_date, field_name="start_date")
        end = self._parse_optional_iso_date(end_date, field_name="end_date")
        if start is not None and end is not None and start > end:
            raise ValueError("Parameter 'start_date' cannot be after 'end_date'.")
        if start is not None and (start < range_start or start > range_end):
            raise ValueError(
                "Parameter 'start_date' must be within the selected start_year/end_year range."
            )
        if end is not None and (end < range_start or end > range_end):
            raise ValueError(
                "Parameter 'end_date' must be within the selected start_year/end_year range."
            )

        uf_clean = self._normalize_uf(uf)
        fetch_batch_size = max(1, int(batch_size))
        max_pages_value = max(1, int(max_pages))
        requested_format = self._normalize_output_format(output_format)
        keep_raw_value = bool(keep_raw)
        effective_start = start or range_start
        effective_end = end or range_end
        client = self._resolve_client(api_base_url=api_base_url)

        if client.mode == "demas":
            return self._download_from_demas(
                spec=spec,
                dataset=dataset_key,
                start_year=start_year_value,
                end_year=end_year_value,
                effective_start=effective_start,
                effective_end=effective_end,
                start=start,
                end=end,
                uf=uf_clean,
                batch_size=fetch_batch_size,
                max_pages=max_pages_value,
                requested_format=requested_format,
                resource_id=resource_id,
                keep_raw=keep_raw_value,
                client=client,
                progress_callback=progress_callback,
            )

        if not spec.ckan_supported:
            raise OpenDataSUSClientError(
                "This dataset is currently available only through DEMAS API mode. "
                "Use api_base_url='https://apidadosabertos.saude.gov.br'."
            )

        selected_resource_id = self._resolve_resource_id(
            client=client,
            spec=spec,
            resource_id=resource_id,
        )

        where_clauses = self._build_where_clauses(
            spec=spec,
            start=effective_start,
            end=effective_end,
            uf=uf_clean,
        )

        total_records = self._count_records(
            client=client,
            resource_id=selected_resource_id,
            where_clauses=where_clauses,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": dataset_key,
                    "documents_total": total_records,
                }
            )

        records: List[Dict[str, object]] = []
        if total_records > 0:
            for offset in range(0, total_records, fetch_batch_size):
                chunk = self._fetch_records(
                    client=client,
                    resource_id=selected_resource_id,
                    date_column=spec.date_column,
                    where_clauses=where_clauses,
                    limit=fetch_batch_size,
                    offset=offset,
                )
                records.extend(chunk)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "file_progress",
                            "source": dataset_key,
                            "documents_total": total_records,
                            "document_index": min(len(records), total_records),
                            "files_completed": min(len(records), total_records),
                        }
                    )

        self._data_by_dataset[dataset_key] = records
        self._latest_dataset = dataset_key

        artifact_stem = self._build_artifact_stem(
            dataset=dataset_key,
            start=effective_start,
            end=effective_end,
            uf=uf_clean,
        )
        raw_path: Optional[Path] = None
        if keep_raw_value:
            raw_path = self._write_raw_snapshot(
                stem=artifact_stem,
                records=records,
            )
        exported_files: List[str] = []
        warnings: List[str] = []
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
                except Exception as exc:
                    warnings.append(
                        self._build_export_failure_warning(
                            exc=exc,
                            keep_raw=keep_raw_value,
                        )
                    )
            else:
                warnings.append(
                    "No records returned by OpenDataSUS query; export file was not generated. "
                    "Consider widening the date window or removing optional refinements such as UF."
                )
        elif not keep_raw_value:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is empty). "
                "Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            dataset=dataset_key,
            resource_id=selected_resource_id,
            start_year=start_year_value,
            end_year=end_year_value,
            start=start,
            end=end,
            effective_start=effective_start,
            effective_end=effective_end,
            uf=uf_clean,
            total_records=total_records,
            records_downloaded=len(records),
            raw_path=raw_path,
            keep_raw=keep_raw_value,
            output_format=requested_format,
            exported_files=exported_files,
            api_base_url=client.base_url,
            warnings=warnings,
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": dataset_key,
                    "documents_total": total_records,
                    "downloaded_count": len(records),
                    "failed_count": 0,
                    "skipped_count": max(total_records - len(records), 0),
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": total_records,
            "downloaded_count": len(records),
            "skipped_count": max(total_records - len(records), 0),
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "dataset": dataset_key,
            "resource_id": selected_resource_id,
            "start_year": start_year_value,
            "end_year": end_year_value,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "query_start_date": effective_start.isoformat(),
            "query_end_date": effective_end.isoformat(),
            "uf": uf_clean,
            "api_base_url": client.base_url,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw_value,
            "output_format": requested_format,
            "exported_files": exported_files,
        }
        export_warning = self._combine_warnings(warnings)
        if export_warning:
            payload["export_warning"] = export_warning
        return payload

    def load_dataframe(self, dataset: Optional[str] = None) -> pl.DataFrame:
        """Load downloaded OpenDataSUS records into Polars."""

        selected = (dataset or self._latest_dataset or "").strip().lower()
        if not selected:
            raise ValueError("No OpenDataSUS dataset loaded yet. Run download() first.")
        records = self._data_by_dataset.get(selected)
        if records is None:
            raise ValueError(
                f"Dataset '{selected}' not available in memory. Run download() for this dataset first."
            )
        if not records:
            return pl.DataFrame()
        return pl.DataFrame(records)

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
            table_name = "opendatasus_records"
            with sqlite3.connect(path) as connection:
                df.to_pandas().to_sql(table_name, connection, if_exists="replace", index=False)
            return path

        raise ValueError(
            f"Unsupported OpenDataSUS export format '{format}'. Allowed: csv, parquet, sqlite"
        )

    def _resolve_client(self, api_base_url: Optional[str]) -> OpenDataSUSClient:
        if api_base_url and api_base_url.strip():
            return OpenDataSUSClient(base_url=api_base_url)
        if self._client is not None:
            return self._client
        return OpenDataSUSClient()

    def _resolve_resource_id(
        self,
        *,
        client: OpenDataSUSClient,
        spec: OpenDataSUSDatasetSpec,
        resource_id: Optional[str],
    ) -> str:
        if resource_id and resource_id.strip():
            return resource_id.strip()

        try:
            package_payload = client.package_show(spec.package_id)
        except OpenDataSUSClientError as exc:
            raise self._annotate_client_error(
                exc,
                context=(
                    "OpenDataSUS CKAN metadata lookup failed while resolving "
                    f"package '{spec.package_id}'"
                ),
            ) from exc
        resources = package_payload.get("resources")
        if not isinstance(resources, list):
            raise OpenDataSUSClientError(
                "OpenDataSUS package metadata did not return a resources list."
            )

        preferred = [item.lower() for item in spec.preferred_resource_terms]
        fallback_id: Optional[str] = None

        for resource in resources:
            if not isinstance(resource, Mapping):
                continue
            candidate_id = str(resource.get("id") or "").strip()
            if not candidate_id:
                continue
            if fallback_id is None:
                fallback_id = candidate_id

            if not bool(resource.get("datastore_active")):
                continue

            searchable = " ".join(
                [
                    str(resource.get("name") or ""),
                    str(resource.get("description") or ""),
                    str(resource.get("url") or ""),
                ]
            ).lower()
            if any(term in searchable for term in preferred):
                return candidate_id

        if fallback_id is not None:
            return fallback_id

        raise OpenDataSUSClientError(
            f"No resource identifier could be resolved for package '{spec.package_id}'."
        )

    def _download_from_demas(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        dataset: str,
        start_year: int,
        end_year: int,
        effective_start: date,
        effective_end: date,
        start: Optional[date],
        end: Optional[date],
        uf: Optional[str],
        batch_size: int,
        max_pages: int,
        requested_format: Optional[str],
        resource_id: Optional[str],
        keep_raw: bool,
        client: OpenDataSUSClient,
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
    ) -> Dict[str, object]:
        endpoints = self._resolve_demas_endpoints(
            spec=spec,
            dataset=dataset,
            start_year=start_year,
            end_year=end_year,
        )
        years = list(range(start_year, end_year + 1))
        page_size = min(max(1, int(batch_size)), 1000)
        max_pages_per_year = min(max(1, int(max_pages)), 200000)
        estimated_pages_total = max(1, len(endpoints) * max_pages_per_year)

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": dataset,
                    "documents_total": estimated_pages_total,
                }
            )

        records: List[Dict[str, object]] = []
        pages_scanned = 0
        truncated = False

        for endpoint_spec in endpoints:
            endpoint = endpoint_spec.path
            uf_param_name = self._select_uf_param(endpoint_spec.uf_params)
            for page in range(max_pages_per_year):
                params: Dict[str, object] = dict(endpoint_spec.query_params)
                params.update(
                    {
                        "limit": page_size,
                        "offset": page,
                    }
                )
                if uf and uf_param_name:
                    params[uf_param_name] = uf

                try:
                    payload = client.demas_get(endpoint, params=params)
                except OpenDataSUSClientError as exc:
                    raise self._annotate_client_error(
                        exc,
                        context=(
                            "OpenDataSUS DEMAS request failed for "
                            f"dataset '{dataset}' at endpoint '{endpoint}' page {page + 1}"
                        ),
                    ) from exc
                fetched = self._extract_demas_rows(payload)
                if not fetched:
                    break

                filtered_rows = self._filter_demas_rows(
                    rows=fetched,
                    start=start,
                    end=end,
                    uf=uf,
                )
                records.extend(filtered_rows)
                pages_scanned += 1

                if progress_callback is not None:
                    page_label = f"{endpoint_spec.label}_page_{page + 1}"
                    progress_callback(
                        {
                            "event": "file_completed",
                            "source": dataset,
                            "documents_total": estimated_pages_total,
                            "document_index": pages_scanned,
                            "file_path": page_label,
                        }
                    )

                if len(fetched) < page_size:
                    break
            else:
                truncated = True

        self._data_by_dataset[dataset] = records
        self._latest_dataset = dataset

        artifact_stem = self._build_artifact_stem(
            dataset=dataset,
            start=effective_start,
            end=effective_end,
            uf=uf,
        )
        raw_path: Optional[Path] = None
        if keep_raw:
            raw_path = self._write_raw_snapshot(
                stem=artifact_stem,
                records=records,
            )

        exported_files: List[str] = []
        warnings: List[str] = []
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
                except Exception as exc:
                    warnings.append(
                        self._build_export_failure_warning(
                            exc=exc,
                            keep_raw=keep_raw,
                        )
                    )
            else:
                warnings.append(
                    "No records returned by OpenDataSUS query; export file was not generated. "
                    "Consider widening the date window or removing optional refinements such as UF."
                )
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is empty). "
                "Set output_format or enable keep_raw."
            )

        if truncated:
            warnings.append(
                "OpenDataSUS query reached max_pages limit before exhausting remote pages. "
                f"Increase max_pages (current={max_pages_per_year}) or narrow the selected date window."
            )

        endpoint_slug = ",".join([item.path.lstrip("/") for item in endpoints]) or dataset
        resolved_resource = (
            resource_id.strip()
            if resource_id and resource_id.strip()
            else f"demas:{endpoint_slug}"
        )
        manifest_path = self._write_manifest(
            dataset=dataset,
            resource_id=resolved_resource,
            start_year=start_year,
            end_year=end_year,
            start=start,
            end=end,
            effective_start=effective_start,
            effective_end=effective_end,
            uf=uf,
            total_records=len(records),
            records_downloaded=len(records),
            raw_path=raw_path,
            keep_raw=keep_raw,
            output_format=requested_format,
            exported_files=exported_files,
            api_base_url=client.base_url,
            warnings=warnings,
            extra_metadata={
                "api_mode": "demas",
                "years": years,
                "endpoints": [item.path for item in endpoints],
                "pages_scanned": pages_scanned,
                "max_pages": max_pages_per_year,
                "batch_size": page_size,
                "truncated": truncated,
            },
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": dataset,
                    "documents_total": estimated_pages_total,
                    "downloaded_count": len(records),
                    "pages_scanned": pages_scanned,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": len(records),
            "downloaded_count": len(records),
            "skipped_count": 0,
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "dataset": dataset,
            "resource_id": resolved_resource,
            "start_year": start_year,
            "end_year": end_year,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "query_start_date": effective_start.isoformat(),
            "query_end_date": effective_end.isoformat(),
            "uf": uf,
            "api_base_url": client.base_url,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw,
            "output_format": requested_format,
            "exported_files": exported_files,
        }
        export_warning = self._combine_warnings(warnings)
        if export_warning:
            payload["export_warning"] = export_warning
        return payload

    def _resolve_demas_endpoints(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        dataset: str,
        start_year: int,
        end_year: int,
    ) -> List[DemasEndpointPlan]:
        if spec.demas_strategy == "pni_yearly":
            by_year = {item.year: item for item in self._demas_catalog}
            selected: List[DemasEndpointPlan] = []
            for year in range(start_year, end_year + 1):
                from_catalog = by_year.get(year)
                if from_catalog is not None:
                    selected.append(
                        DemasEndpointPlan(
                            path=from_catalog.path,
                            label=f"{dataset}_year_{year}",
                            uf_params=from_catalog.uf_params,
                            query_params={},
                        )
                    )
                    continue
                selected.append(
                    DemasEndpointPlan(
                        path=f"/vacinacao/doses-aplicadas-pni-{year}",
                        label=f"{dataset}_year_{year}",
                        uf_params=self._fallback_uf_params_for_year(year),
                        query_params={},
                    )
                )
            return selected

        path = str(spec.demas_static_path or "").strip()
        if not path.startswith("/"):
            path = f"/{path}"
        params = self._demas_get_params_by_path.get(path, ())
        uf_params = tuple(
            item for item in params if item in self._candidate_uf_param_names()
        )
        if "nu_ano" in params:
            return [
                DemasEndpointPlan(
                    path=path,
                    label=f"{dataset}_year_{year}",
                    uf_params=uf_params,
                    query_params={"nu_ano": year},
                )
                for year in range(start_year, end_year + 1)
            ]

        return [DemasEndpointPlan(path=path, label=dataset, uf_params=uf_params, query_params={})]

    @staticmethod
    def _fallback_uf_params_for_year(year: int) -> tuple[str, ...]:
        if year == 2020:
            return ("uf_estabelecimento", "uf_paciente")
        if year in {2021, 2023}:
            return ("uf_estabelecimento",)
        if year == 2022:
            return ("uf_paciente",)
        return ()

    @staticmethod
    def _select_uf_param(uf_params: tuple[str, ...]) -> Optional[str]:
        if not uf_params:
            return None
        if "uf_estabelecimento" in uf_params:
            return "uf_estabelecimento"
        if "uf_paciente" in uf_params:
            return "uf_paciente"
        if "uf" in uf_params:
            return "uf"
        return None

    @staticmethod
    def _candidate_uf_param_names() -> tuple[str, ...]:
        return (
            "uf",
            "sg_uf",
            "sg_uf_not",
            "uf_notificacao",
            "uf_residencia",
            "uf_paciente",
            "uf_estabelecimento",
        )

    @staticmethod
    def _extract_demas_rows(payload: Mapping[str, object]) -> List[Dict[str, object]]:
        for value in payload.values():
            if isinstance(value, list):
                rows: List[Dict[str, object]] = []
                for item in value:
                    if isinstance(item, Mapping):
                        rows.append({str(key): item_value for key, item_value in item.items()})
                return rows
        return []

    def _filter_demas_rows(
        self,
        *,
        rows: List[Dict[str, object]],
        start: Optional[date],
        end: Optional[date],
        uf: Optional[str],
    ) -> List[Dict[str, object]]:
        accepted: List[Dict[str, object]] = []
        for row in rows:
            if start is not None or end is not None:
                row_date = self._extract_record_date(row)
                if row_date is None:
                    continue
                if start is not None and row_date < start:
                    continue
                if end is not None and row_date > end:
                    continue

            if uf is not None:
                row_uf = self._extract_record_uf(row)
                if row_uf != uf:
                    continue

            accepted.append(row)
        return accepted

    @staticmethod
    def _extract_record_date(row: Mapping[str, object]) -> Optional[date]:
        candidates = [
            "data_vacina",
            "vacina_dataAplicacao",
            "data_aplicacao",
            "dataAplicacao",
            "dt_notific",
            "dt_sin_pri",
            "dt_invest",
            "dt_digita",
        ]
        for key in candidates:
            raw_value = row.get(key)
            if raw_value is None:
                continue
            text = str(raw_value).strip()
            if len(text) < 10:
                continue
            candidate = text[:10]
            try:
                return datetime.strptime(candidate, "%Y-%m-%d").date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_record_uf(row: Mapping[str, object]) -> Optional[str]:
        uf_fields = [
            "sigla_uf_estabelecimento",
            "uf_estabelecimento",
            "estabelecimento_uf",
            "sigla_uf_paciente",
            "uf_paciente",
            "paciente_endereco_uf",
            "sg_uf_not",
            "sg_uf",
            "sg_uf_resi",
        ]
        numeric_to_uf = {
            "11": "RO",
            "12": "AC",
            "13": "AM",
            "14": "RR",
            "15": "PA",
            "16": "AP",
            "17": "TO",
            "21": "MA",
            "22": "PI",
            "23": "CE",
            "24": "RN",
            "25": "PB",
            "26": "PE",
            "27": "AL",
            "28": "SE",
            "29": "BA",
            "31": "MG",
            "32": "ES",
            "33": "RJ",
            "35": "SP",
            "41": "PR",
            "42": "SC",
            "43": "RS",
            "50": "MS",
            "51": "MT",
            "52": "GO",
            "53": "DF",
        }
        for field in uf_fields:
            value = row.get(field)
            if value is None:
                continue
            cleaned = str(value).strip().upper()
            if len(cleaned) == 2 and cleaned.isalpha():
                return cleaned
            mapped = numeric_to_uf.get(cleaned)
            if mapped:
                return mapped
        return None

    @staticmethod
    def _records_to_dataframe(records: List[Dict[str, object]]) -> pl.DataFrame:
        # Scan all rows to avoid schema mismatch when columns mix numeric/text values.
        return pl.from_dicts(records, infer_schema_length=None)

    def _count_records(
        self,
        *,
        client: OpenDataSUSClient,
        resource_id: str,
        where_clauses: List[str],
    ) -> int:
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = (
            f"SELECT COUNT(*) AS total FROM {self._quote_identifier(resource_id)} "
            f"WHERE {where_sql}"
        )
        try:
            result = client.datastore_search_sql(sql)
        except OpenDataSUSClientError as exc:
            raise self._annotate_client_error(
                exc,
                context=(
                    "OpenDataSUS CKAN count query failed for "
                    f"resource '{resource_id}'"
                ),
            ) from exc
        records = result.get("records")
        if not isinstance(records, list) or not records:
            return 0
        first = records[0]
        if not isinstance(first, Mapping):
            return 0
        raw_total = first.get("total")
        try:
            return max(0, int(raw_total))
        except (TypeError, ValueError):
            return 0

    def _fetch_records(
        self,
        *,
        client: OpenDataSUSClient,
        resource_id: str,
        date_column: str,
        where_clauses: List[str],
        limit: int,
        offset: int,
    ) -> List[Dict[str, object]]:
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = (
            f"SELECT * FROM {self._quote_identifier(resource_id)} "
            f"WHERE {where_sql} "
            f"ORDER BY {self._quote_identifier(date_column)} ASC "
            f"LIMIT {max(1, int(limit))} OFFSET {max(0, int(offset))}"
        )
        try:
            result = client.datastore_search_sql(sql)
        except OpenDataSUSClientError as exc:
            raise self._annotate_client_error(
                exc,
                context=(
                    "OpenDataSUS CKAN page query failed for "
                    f"resource '{resource_id}' at offset {max(0, int(offset))}"
                ),
            ) from exc
        rows = result.get("records")
        if not isinstance(rows, list):
            return []

        normalized: List[Dict[str, object]] = []
        for item in rows:
            if isinstance(item, Mapping):
                normalized.append({str(key): value for key, value in item.items()})
        return normalized

    def _build_where_clauses(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        start: date,
        end: date,
        uf: Optional[str],
    ) -> List[str]:
        clauses = [
            f"{self._quote_identifier(spec.date_column)} >= {self._quote_literal(start.isoformat())}",
            f"{self._quote_identifier(spec.date_column)} <= {self._quote_literal(end.isoformat())}",
        ]
        if uf:
            clauses.append(
                f"UPPER({self._quote_identifier(spec.uf_column)}) = {self._quote_literal(uf)}"
            )
        return clauses

    def _build_artifact_stem(
        self,
        *,
        dataset: str,
        start: date,
        end: date,
        uf: Optional[str],
    ) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        uf_suffix = uf or "ALL"
        return f"{dataset}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{uf_suffix}_{timestamp}"

    def _write_raw_snapshot(self, *, stem: str, records: List[Dict[str, object]]) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        file_path = raw_dir / f"{stem}.jsonl"
        with file_path.open("w", encoding="utf-8") as handler:
            for item in records:
                handler.write(json.dumps(item, ensure_ascii=False))
                handler.write("\n")
        return file_path

    def _write_manifest(
        self,
        *,
        dataset: str,
        resource_id: str,
        start_year: int,
        end_year: int,
        start: Optional[date],
        end: Optional[date],
        effective_start: date,
        effective_end: date,
        uf: Optional[str],
        total_records: int,
        records_downloaded: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: List[str],
        api_base_url: str,
        warnings: Optional[List[str]] = None,
        extra_metadata: Optional[Mapping[str, object]] = None,
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        payload = {
            "source": dataset,
            "dataset": dataset,
            "resource_id": resource_id,
            "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "request": {
                "start_year": start_year,
                "end_year": end_year,
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "query_start_date": effective_start.isoformat(),
                "query_end_date": effective_end.isoformat(),
                "uf": uf,
                "keep_raw": keep_raw,
            },
            "summary": {
                "documents_found": total_records,
                "downloaded_count": records_downloaded,
                "failed_count": 0,
            },
            "api_base_url": api_base_url,
            "output_dir": str(self.output_path),
            "raw_file": str(raw_path) if raw_path else None,
            "output_format": output_format,
            "exported_files": list(exported_files),
            "warnings": list(warnings or []),
        }
        if extra_metadata:
            payload["details"] = dict(extra_metadata)
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    @staticmethod
    def _annotate_client_error(
        exc: OpenDataSUSClientError,
        *,
        context: str,
    ) -> OpenDataSUSClientError:
        return exc.with_context(context)

    @staticmethod
    def _combine_warnings(warnings: List[str]) -> Optional[str]:
        cleaned = [item.strip() for item in warnings if str(item).strip()]
        if not cleaned:
            return None
        return " ".join(cleaned)

    @staticmethod
    def _build_export_failure_warning(
        *,
        exc: Exception,
        keep_raw: bool,
    ) -> str:
        if keep_raw:
            artifact_note = "Raw snapshot and manifest were generated."
        else:
            artifact_note = (
                "Manifest was generated, but no data artifact was preserved. "
                "Re-run with keep_raw=true to retain the raw payload."
            )
        return (
            "OpenDataSUS export failed after download. "
            f"{artifact_note} Error: {exc}"
        )

    @staticmethod
    def _parse_iso_date(value: str, *, field_name: str) -> date:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"Parameter '{field_name}' must use date format YYYY-MM-DD."
            ) from exc

    def _parse_optional_iso_date(self, value: Optional[str], *, field_name: str) -> Optional[date]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return self._parse_iso_date(cleaned, field_name=field_name)

    @staticmethod
    def _normalize_year_window(
        *,
        start_year: Optional[int],
        end_year: Optional[int],
    ) -> tuple[int, int]:
        default_year = datetime.utcnow().year - 1
        start_value = int(start_year if start_year is not None else default_year)
        end_value = int(end_year if end_year is not None else start_value)
        if start_value > end_value:
            raise ValueError("Parameter 'start_year' cannot be greater than 'end_year'.")
        if start_value < 1900:
            raise ValueError("Parameter 'start_year' must be >= 1900.")
        return start_value, end_value

    @staticmethod
    def _normalize_uf(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            return None
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("Parameter 'uf' must be a two-letter UF code (e.g., SP).")
        return cleaned

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
    def _quote_identifier(value: str) -> str:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
