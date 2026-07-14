"""Download orchestration services used by CLI and API layers."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from loguru import logger

from guaraci.core.contracts import DownloadManifest, SourceParameterSpec, validate_source_params
from guaraci.core.results import JobResult
from guaraci.datasus import SihDataSource, SimDataSource, SinanDataSource
from guaraci.datasus.ftp import specs as ftp_specs
from guaraci.datasus.ftp_source import FtpDataSource
from guaraci.ibge import (
    IbgePibMunicipiosDataSource,
    IbgePopulacaoDataSource,
    IbgePopulacaoIdadeSexoDataSource,
)
from guaraci.nasa import (
    NasaFirmsDataSource,
    NasaGpmDataSource,
    NasaPowerDataSource,
)
from guaraci.opendatasus import OpenDataSUSDataSource
from guaraci.snis import SinisaDataSource, SnisDataSource
from guaraci.utils.mapping import UF_DICT

EXPORT_FORMAT_VALUES = ["csv", "parquet", "sqlite"]


@dataclass(frozen=True)
class SourceDescriptor:
    """Human-readable metadata for supported sources."""

    source: str
    title: str
    mode: str


class DownloadSource(Protocol):
    """Contract for pluggable download sources."""

    descriptor: SourceDescriptor

    def params_schema(self) -> List[SourceParameterSpec]:
        """Return supported input params for this source."""

    def validate_params(self, params: Mapping[str, object]) -> None:
        """Validate user-provided params before datasource execution."""

    def download(self, **kwargs: object) -> JobResult:
        """Execute source download and return normalized result."""


class GovBrDownloadSource:
    """Adapter for gov.br crawler datasources with shared params."""

    def __init__(
        self,
        descriptor: SourceDescriptor,
        datasource_cls: Callable[..., Any],
    ) -> None:
        self.descriptor = descriptor
        self._datasource_cls = datasource_cls
        self._params_schema = self._build_default_param_schema()

    def params_schema(self) -> List[SourceParameterSpec]:
        return list(self._params_schema)

    def _build_default_param_schema(self) -> List[SourceParameterSpec]:
        valid_kinds = list(getattr(self._datasource_cls, "VALID_FILE_KINDS", []))
        valid_modules = list(getattr(self._datasource_cls, "VALID_MODULES", []))
        return [
            SourceParameterSpec(
                name="output_dir",
                        phase="tecnica",
                param_type="string",
                description="Output directory for downloaded files.",
                required=False,
                default=None,
            ),
            SourceParameterSpec(
                name="results_url",
                        phase="coleta",
                param_type="string",
                description="Custom results page URL for discovery.",
                required=False,
                default=None,
            ),
            SourceParameterSpec(
                name="file_kinds",
                        phase="coleta",
                param_type="string_list",
                description="Kinds of files to collect for the selected source.",
                required=False,
                default=["planilhas"],
                allowed_values=valid_kinds or None,
            ),
            SourceParameterSpec(
                name="modules",
                        phase="coleta",
                param_type="string_list",
                description="Functional modules to filter results.",
                required=False,
                default=None,
                allowed_values=valid_modules or None,
            ),
            SourceParameterSpec(
                name="extract_archives",
                        phase="tecnica",
                param_type="boolean",
                description="If true, extract ZIP files after download.",
                required=False,
                default=True,
            ),
            SourceParameterSpec(
                name="overwrite",
                        phase="tecnica",
                param_type="boolean",
                description="If true, overwrite existing local files.",
                required=False,
                default=False,
            ),
            SourceParameterSpec(
                name="timeout",
                        phase="tecnica",
                param_type="integer",
                description="HTTP timeout in seconds.",
                required=False,
                default=120,
                minimum=1,
            ),
        ]

    def validate_params(self, params: Mapping[str, object]) -> None:
        validate_source_params(params=params, specs=self._params_schema, reject_unknown=True)

    def download(self, **kwargs: object) -> JobResult:
        output_dir = kwargs.get("output_dir")
        datasource = self._datasource_cls(output_path=output_dir)
        payload = datasource.download(**kwargs)
        return JobResult.from_payload(source=self.descriptor.source, payload=payload)

    def download_with_progress(
        self,
        progress_callback: Callable[[Dict[str, object]], None],
        **kwargs: object,
    ) -> JobResult:
        output_dir = kwargs.get("output_dir")
        datasource = self._datasource_cls(output_path=output_dir)
        payload = datasource.download(progress_callback=progress_callback, **kwargs)
        return JobResult.from_payload(source=self.descriptor.source, payload=payload)


class PysusDownloadSource:
    """Adapter for PySUS-backed DATASUS datasources."""

    def __init__(
        self,
        descriptor: SourceDescriptor,
        datasource_cls: Callable[..., Any],
        params_schema: Sequence[SourceParameterSpec],
        normalize_params: Optional[Callable[[Dict[str, object]], Dict[str, object]]] = None,
    ) -> None:
        self.descriptor = descriptor
        self._datasource_cls = datasource_cls
        self._params_schema = list(params_schema)
        self._normalize_params = normalize_params

    def params_schema(self) -> List[SourceParameterSpec]:
        return list(self._params_schema)

    def validate_params(self, params: Mapping[str, object]) -> None:
        validate_source_params(params=params, specs=self._params_schema, reject_unknown=True)

    def _prepare_kwargs(self, kwargs: Mapping[str, object]) -> Dict[str, object]:
        prepared = dict(kwargs)
        if self._normalize_params is not None:
            prepared = self._normalize_params(prepared)
        return prepared

    def _download(
        self,
        *,
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
        **kwargs: object,
    ) -> JobResult:
        output_dir = kwargs.get("output_dir")
        datasource = self._datasource_cls(output_path=output_dir)
        prepared = self._prepare_kwargs(dict(kwargs))
        prepared.pop("output_dir", None)
        download_kwargs, postprocess_kwargs = self._split_download_and_postprocess_kwargs(prepared)

        if progress_callback is None:
            payload = datasource.download(**download_kwargs)
        else:
            progress_state = {"started": False}

            def pysus_progress(completed: int, total: int) -> None:
                completed_int = max(0, int(completed))
                total_int = max(0, int(total))
                if not progress_state["started"]:
                    progress_callback(
                        {
                            "event": "download_start",
                            "source": self.descriptor.source,
                            "documents_total": total_int,
                        }
                    )
                    progress_state["started"] = True
                progress_callback(
                    {
                        "event": "file_progress",
                        "source": self.descriptor.source,
                        "documents_total": total_int,
                        "document_index": completed_int,
                        "files_completed": completed_int,
                    }
                )

            payload = datasource.download(progress_callback=pysus_progress, **download_kwargs)

            total_files = int(payload.get("total_files", 0)) if isinstance(payload, Mapping) else 0
            downloaded = (
                int(payload.get("successful_downloads", 0))
                if isinstance(payload, Mapping)
                else 0
            )
            failed = (
                len(payload.get("failed_downloads", []))
                if isinstance(payload, Mapping)
                else 0
            )
            progress_callback(
                {
                    "event": "download_complete",
                    "source": self.descriptor.source,
                    "documents_total": total_files,
                    "downloaded_count": downloaded,
                    "failed_count": failed,
                    "skipped_count": max(0, total_files - downloaded - failed),
                    "output_dir": str(datasource.output_path),
                }
            )

        materialized_paths: List[str] = []
        local_paths = self._collect_datasource_local_paths(datasource)
        if local_paths:
            materialized_paths = self._materialize_local_artifacts(
                local_paths=local_paths,
                output_root=Path(datasource.output_path),
            )
        exported_files = self._export_processed_outputs(
            datasource=datasource,
            download_kwargs=download_kwargs,
            postprocess_kwargs=postprocess_kwargs,
        )
        requested_output_format = str(postprocess_kwargs.get("output_format") or "").strip().lower()

        if isinstance(payload, dict):
            if payload.get("output_dir") is None:
                payload["output_dir"] = str(datasource.output_path)
            if materialized_paths or exported_files:
                payload["materialized_paths"] = materialized_paths
                payload["exported_files"] = exported_files
                
                warnings: List[str] = []
                if not exported_files and requested_output_format:
                    warnings.append("No processed file was exported. Check format and export filters.")
                    payload["export_warning"] = warnings[0]
                
                payload["manifest_path"] = str(
                    self._write_manifest(
                        output_root=Path(datasource.output_path),
                        payload=payload,
                        materialized_paths=materialized_paths,
                        exported_files=exported_files,
                        download_kwargs=download_kwargs,
                        postprocess_kwargs=postprocess_kwargs,
                        warnings=warnings,
                        )
                    )
            if requested_output_format:
                payload["output_format"] = requested_output_format
        return JobResult.from_payload(source=self.descriptor.source, payload=payload)

    def download(self, **kwargs: object) -> JobResult:
        return self._download(progress_callback=None, **kwargs)

    def download_with_progress(
        self,
        progress_callback: Callable[[Dict[str, object]], None],
        **kwargs: object,
    ) -> JobResult:
        return self._download(progress_callback=progress_callback, **kwargs)

    @staticmethod
    def _collect_datasource_local_paths(datasource: Any) -> List[Path]:
        data = getattr(datasource, "data", None)
        if not isinstance(data, dict):
            return []

        collected: List[Path] = []
        seen: set[str] = set()
        for items in data.values():
            if not isinstance(items, list):
                continue
            for item in items:
                candidate = None
                if hasattr(item, "path"):
                    candidate = getattr(item, "path")
                elif isinstance(item, (str, Path)):
                    candidate = item
                if candidate is None:
                    continue
                try:
                    resolved = Path(str(candidate)).resolve()
                except OSError:
                    continue
                if not resolved.exists():
                    continue
                key = str(resolved)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(resolved)
        return collected

    @staticmethod
    def _materialize_local_artifacts(local_paths: Sequence[Path], output_root: Path) -> List[str]:
        raw_root = output_root / "raw"
        raw_root.mkdir(parents=True, exist_ok=True)

        materialized: List[str] = []
        for source_path in local_paths:
            destination = raw_root / source_path.name
            if source_path.is_dir():
                shutil.copytree(source_path, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)
            materialized.append(str(destination))
        return materialized

    def _write_manifest(
        self,
        *,
        output_root: Path,
        payload: Mapping[str, object],
        materialized_paths: Sequence[str],
        exported_files: Sequence[str],
        download_kwargs: Mapping[str, object],
        postprocess_kwargs: Mapping[str, object],
        warnings: Sequence[str],
    ) -> Path:
        manifest_path = output_root / "manifest.json"
        
        request_filters = dict(download_kwargs)
        request_filters.update(postprocess_kwargs)
        
        manifest = DownloadManifest(
            source=self.descriptor.source,
            filters=request_filters,
            documents_found=int(payload.get("total_files", 0)),
            downloaded_files=[],  # Pysus doesn't track raw files one-by-one by default
            materialized_paths=list(materialized_paths),
            exported_files=list(exported_files),
            warnings=list(warnings),
        )
        
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    def _split_download_and_postprocess_kwargs(
        self,
        params: Mapping[str, object],
    ) -> tuple[Dict[str, object], Dict[str, object]]:
        source = self.descriptor.source
        post_keys = {"output_format"}
        if source == "sinan":
            post_keys |= {
                "uf",
                "municipio",
                "sexo",
                "faixa_etaria",
                "evolucao",
                "classificacao",
            }
        elif source == "sim":
            post_keys |= {"uf", "municipio", "sexo", "causa_basica", "ano_obito"}
        elif source == "sih":
            post_keys |= {"uf", "municipio", "sexo"}

        download_kwargs = {
            key: value for key, value in params.items() if key not in post_keys
        }
        postprocess_kwargs = {
            key: value for key, value in params.items() if key in post_keys
        }
        return download_kwargs, postprocess_kwargs

    def _export_processed_outputs(
        self,
        *,
        datasource: Any,
        download_kwargs: Mapping[str, object],
        postprocess_kwargs: Mapping[str, object],
    ) -> List[str]:
        output_format = str(postprocess_kwargs.get("output_format") or "").strip().lower()
        if not output_format:
            return []

        source = self.descriptor.source
        exported: List[str] = []
        if source == "sinan":
            exported.extend(
                self._export_sinan(
                    datasource=datasource,
                    output_format=output_format,
                    download_kwargs=download_kwargs,
                    postprocess_kwargs=postprocess_kwargs,
                )
            )
        elif source == "sim":
            exported.extend(
                self._export_sim(
                    datasource=datasource,
                    output_format=output_format,
                    download_kwargs=download_kwargs,
                    postprocess_kwargs=postprocess_kwargs,
                )
            )
        elif source == "sih":
            exported.extend(
                self._export_sih(
                    datasource=datasource,
                    output_format=output_format,
                    download_kwargs=download_kwargs,
                    postprocess_kwargs=postprocess_kwargs,
                )
            )
        elif source in _FTP_SOURCE_NAMES:
            exported.extend(
                self._export_ftp(
                    datasource=datasource,
                    output_format=output_format,
                    download_kwargs=download_kwargs,
                )
            )
        return exported

    @staticmethod
    def _compact_filter_kwargs(raw: Mapping[str, object], keys: Sequence[str]) -> Dict[str, object]:
        payload: Dict[str, object] = {}
        for key in keys:
            value = raw.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            payload[key] = value
        return payload

    def _export_sinan(
        self,
        *,
        datasource: Any,
        output_format: str,
        download_kwargs: Mapping[str, object],
        postprocess_kwargs: Mapping[str, object],
    ) -> List[str]:
        diseases = list(download_kwargs.get("diseases") or getattr(datasource, "NEGLECTED_DISEASES", []))
        start_year = int(download_kwargs.get("start_year", datetime.now().year))
        end_year = int(download_kwargs.get("end_year", start_year))
        filter_kwargs = self._compact_filter_kwargs(
            postprocess_kwargs,
            ["uf", "municipio", "sexo", "faixa_etaria", "evolucao", "classificacao"],
        )
        exported: List[str] = []
        for disease in diseases:
            available = getattr(datasource, "data", {}).get(disease, [])
            if not available:
                continue
            try:
                df = datasource.load_dataframe(str(disease))
                if filter_kwargs:
                    df = datasource.filter(df, **filter_kwargs)
                exported_path = datasource.export(
                    df,
                    format=output_format,
                    name=f"{disease}_{start_year}_{end_year}",
                )
                if exported_path is not None:
                    exported.append(str(exported_path))
            except Exception as exc:
                logger.warning(
                    "Failed to export SINAN disease '{}' to format '{}': {}",
                    disease,
                    output_format,
                    exc,
                )
                continue
        return exported

    def _export_sim(
        self,
        *,
        datasource: Any,
        output_format: str,
        download_kwargs: Mapping[str, object],
        postprocess_kwargs: Mapping[str, object],
    ) -> List[str]:
        groups = list(download_kwargs.get("groups") or getattr(datasource, "ALL_GROUPS", getattr(datasource, "DEFAULT_GROUPS", [])))
        start_year = int(download_kwargs.get("start_year", datetime.now().year))
        end_year = int(download_kwargs.get("end_year", start_year))
        filter_kwargs = self._compact_filter_kwargs(
            postprocess_kwargs,
            ["uf", "municipio", "sexo", "causa_basica", "ano_obito"],
        )
        exported: List[str] = []
        for group in groups:
            available = getattr(datasource, "data", {}).get(group, [])
            if not available:
                continue
            try:
                df = datasource.load_dataframe(str(group))
                if filter_kwargs:
                    df = datasource.filter(df, **filter_kwargs)
                exported_path = datasource.export(
                    df,
                    format=output_format,
                    name=f"{group}_{start_year}_{end_year}",
                )
                if exported_path is not None:
                    exported.append(str(exported_path))
            except Exception as exc:
                logger.warning(
                    "Failed to export SIM group '{}' to format '{}': {}",
                    group,
                    output_format,
                    exc,
                )
                continue
        return exported

    def _export_sih(
        self,
        *,
        datasource: Any,
        output_format: str,
        download_kwargs: Mapping[str, object],
        postprocess_kwargs: Mapping[str, object],
    ) -> List[str]:
        groups = list(download_kwargs.get("groups") or getattr(datasource, "DEFAULT_GROUPS", []))
        start_year = int(download_kwargs.get("start_year", datetime.now().year))
        end_year = int(download_kwargs.get("end_year", start_year))
        filter_kwargs = self._compact_filter_kwargs(
            postprocess_kwargs,
            ["uf", "municipio", "sexo"],
        )
        exported: List[str] = []
        for group in groups:
            available = getattr(datasource, "data", {}).get(group, [])
            if not available:
                continue
            try:
                df = datasource.load_dataframe(str(group))
                if filter_kwargs:
                    df = datasource.filter(df, **filter_kwargs)
                exported_path = datasource.export(
                    df,
                    format=output_format,
                    name=f"{group}_{start_year}_{end_year}",
                )
                if exported_path is not None:
                    exported.append(str(exported_path))
            except Exception as exc:
                logger.warning(
                    "Failed to export SIH group '{}' to format '{}': {}",
                    group,
                    output_format,
                    exc,
                )
                continue
        return exported

    def _export_ftp(
        self,
        *,
        datasource: Any,
        output_format: str,
        download_kwargs: Mapping[str, object],
    ) -> List[str]:
        """Generic export for the phase-5 FTP sources.

        These sources have no bespoke per-field refinement filters, so the
        export simply combines every downloaded group into one frame and
        writes a single file in the requested format.
        """
        start_year = int(download_kwargs.get("start_year", datetime.now().year))
        end_year = int(download_kwargs.get("end_year", start_year))
        try:
            df = datasource.load_dataframe()
            exported_path = datasource.export(
                df,
                format=output_format,
                name=f"{self.descriptor.source}_{start_year}_{end_year}",
            )
            return [str(exported_path)] if exported_path is not None else []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to export {} to format '{}': {}",
                self.descriptor.source,
                output_format,
                exc,
            )
            return []


class OpenDataSUSDownloadSource:
    """Adapter for OpenDataSUS API-backed datasources."""

    def __init__(
        self,
        descriptor: SourceDescriptor,
        datasource_cls: Callable[..., Any],
        params_schema: Sequence[SourceParameterSpec],
        fixed_dataset: Optional[str] = None,
        normalize_params: Optional[Callable[[Dict[str, object]], Dict[str, object]]] = None,
    ) -> None:
        self.descriptor = descriptor
        self._datasource_cls = datasource_cls
        self._params_schema = list(params_schema)
        self._fixed_dataset = fixed_dataset.strip().lower() if fixed_dataset else None
        self._normalize_params = normalize_params

    def params_schema(self) -> List[SourceParameterSpec]:
        return list(self._params_schema)

    def validate_params(self, params: Mapping[str, object]) -> None:
        prepared = self._prepare_kwargs(params)
        validate_source_params(params=prepared, specs=self._params_schema, reject_unknown=True)
        for name in self._required_path_params():
            value = prepared.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(
                    f"Parameter '{name}' is required for OpenDataSUS source "
                    f"'{self.descriptor.source}'."
                )

    def _prepare_kwargs(self, kwargs: Mapping[str, object]) -> Dict[str, object]:
        prepared = dict(kwargs)
        if self._normalize_params is not None:
            prepared = self._normalize_params(prepared)
        return prepared

    def _download(
        self,
        *,
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
        **kwargs: object,
    ) -> JobResult:
        output_dir = kwargs.get("output_dir")
        datasource = self._datasource_cls(output_path=output_dir)
        prepared = self._prepare_kwargs(dict(kwargs))
        prepared.pop("output_dir", None)
        if self._fixed_dataset is not None:
            prepared["dataset"] = self._fixed_dataset
        if progress_callback is not None:
            prepared["progress_callback"] = progress_callback
        payload = datasource.download(**prepared)
        return JobResult.from_payload(source=self.descriptor.source, payload=payload)

    def _required_path_params(self) -> List[str]:
        if not self._fixed_dataset:
            return []
        return re.findall(r"{([^{}]+)}", self._fixed_dataset)

    def download(self, **kwargs: object) -> JobResult:
        return self._download(progress_callback=None, **kwargs)

    def download_with_progress(
        self,
        progress_callback: Callable[[Dict[str, object]], None],
        **kwargs: object,
    ) -> JobResult:
        return self._download(progress_callback=progress_callback, **kwargs)


class NasaDownloadSource:
    """Adapter for NASA API-backed datasources (POWER and future products)."""

    def __init__(
        self,
        descriptor: SourceDescriptor,
        datasource_cls: Callable[..., Any],
        params_schema: Sequence[SourceParameterSpec],
        normalize_params: Optional[Callable[[Dict[str, object]], Dict[str, object]]] = None,
    ) -> None:
        self.descriptor = descriptor
        self._datasource_cls = datasource_cls
        self._params_schema = list(params_schema)
        self._normalize_params = normalize_params

    def params_schema(self) -> List[SourceParameterSpec]:
        return list(self._params_schema)

    def validate_params(self, params: Mapping[str, object]) -> None:
        prepared = self._prepare_kwargs(params)
        validate_source_params(
            params=prepared, specs=self._params_schema, reject_unknown=True
        )

    def _prepare_kwargs(self, kwargs: Mapping[str, object]) -> Dict[str, object]:
        prepared = dict(kwargs)
        if self._normalize_params is not None:
            prepared = self._normalize_params(prepared)
        return prepared

    def _download(
        self,
        *,
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
        **kwargs: object,
    ) -> JobResult:
        output_dir = kwargs.get("output_dir")
        datasource = self._datasource_cls(output_path=output_dir)
        prepared = self._prepare_kwargs(dict(kwargs))
        prepared.pop("output_dir", None)
        if progress_callback is not None:
            prepared["progress_callback"] = progress_callback
        payload = datasource.download(**prepared)
        return JobResult.from_payload(source=self.descriptor.source, payload=payload)

    def download(self, **kwargs: object) -> JobResult:
        return self._download(progress_callback=None, **kwargs)

    def download_with_progress(
        self,
        progress_callback: Callable[[Dict[str, object]], None],
        **kwargs: object,
    ) -> JobResult:
        return self._download(progress_callback=progress_callback, **kwargs)


class DownloadService:
    """Facade with source registry and normalized `JobResult` responses."""

    def __init__(self, sources: Optional[Sequence[DownloadSource]] = None) -> None:
        self._sources: Dict[str, DownloadSource] = {}
        for source in sources or self._default_sources():
            self.register_source(source)

    @staticmethod
    def _normalize_source_name(source: str) -> str:
        key = source.strip().lower()
        if not key:
            raise ValueError("Source name cannot be empty.")
        return key

    def _default_sources(self) -> List[DownloadSource]:
        current_year = datetime.now().year
        last_year = current_year - 1
        uf_values = sorted(set(UF_DICT.values()))
        sources: List[DownloadSource] = [
            GovBrDownloadSource(
                descriptor=SourceDescriptor(
                    source="snis",
                    title="SNIS",
                    mode="gov.br crawl",
                ),
                datasource_cls=SnisDataSource,
            ),
            GovBrDownloadSource(
                descriptor=SourceDescriptor(
                    source="sinisa",
                    title="SINISA",
                    mode="gov.br crawl",
                ),
                datasource_cls=SinisaDataSource,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="doses_aplicadas_pni",
                    title="Doses Aplicadas PNI",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS (endpoint anual).",
                        required=True,
                        default=last_year,
                        minimum=2020,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS (endpoint anual).",
                        required=True,
                        default=last_year,
                        minimum=2020,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Filtro opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched per year in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="resource_id",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional explicit resource id (CKAN mode). "
                            "Ignored in DEMAS mode."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br | CKAN: .../api/3/action)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset=OpenDataSUSDataSource.DEFAULT_DATASET,
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="zikavirus",
                    title="Arboviroses Zikavirus",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="zikavirus",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="febre_amarela",
                    title="Arboviroses Febre Amarela",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(1994, last_year),
                        minimum=1994,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(1994, last_year),
                        minimum=1994,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="febre_amarela",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="dengue",
                    title="Arboviroses Dengue",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="dengue",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="chikungunya",
                    title="Arboviroses Chikungunya",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="chikungunya",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="srag_demas",
                    title="SRAG (Vigilância Epidemiológica da Gripe)",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="srag_demas",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="sindrome_gripal_leve",
                    title="Síndrome Gripal Leve",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="sindrome_gripal_leve",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="mpox",
                    title="Mpox",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="mpox",
                normalize_params=_normalize_opendatasus_params,
            ),
            OpenDataSUSDownloadSource(
                descriptor=SourceDescriptor(
                    source="esavi",
                    title="ESAVI - Eventos Adversos Pós-Vacinação",
                    mode="opendatasus api",
                ),
                datasource_cls=OpenDataSUSDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final para consulta na API OpenDataSUS.",
                        required=True,
                        default=max(2016, last_year),
                        minimum=2016,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data inicial (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="refinamento",
                        param_type="string",
                        description=(
                            "Refinamento opcional local: data final (YYYY-MM-DD) "
                            "dentro do intervalo start_year/end_year."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Refinamento local opcional por UF.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva snapshot bruto JSONL além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="batch_size",
                        phase="tecnica",
                        param_type="integer",
                        description="Page size for OpenDataSUS API pagination.",
                        required=False,
                        default=1000,
                        minimum=1,
                        maximum=1000,
                    ),
                    SourceParameterSpec(
                        name="max_pages",
                        phase="tecnica",
                        param_type="integer",
                        description=(
                            "Maximum number of pages fetched in OpenDataSUS API. "
                            "Increase for broader coverage in large periods."
                        ),
                        required=False,
                        default=OpenDataSUSDataSource.DEFAULT_MAX_PAGES,
                        minimum=1,
                        maximum=200000,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Optional OpenDataSUS API base URL override "
                            "(DEMAS: apidadosabertos.saude.gov.br)."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                fixed_dataset="esavi",
                normalize_params=_normalize_opendatasus_params,
            ),
            PysusDownloadSource(
                descriptor=SourceDescriptor(
                    source="sinan",
                    title="SINAN",
                    mode="pysus ftp",
                ),
                datasource_cls=SinanDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Starting year for file discovery.",
                        required=True,
                        default=last_year,
                        minimum=1990,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ending year for file discovery.",
                        required=True,
                        default=last_year,
                        minimum=1990,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="diseases",
                        phase="coleta",
                        param_type="string_list",
                        description="Disease code list to download.",
                        required=False,
                        default=list(SinanDataSource.NEGLECTED_DISEASES),
                        allowed_values=list(SinanDataSource.NEGLECTED_DISEASES),
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Optional UF filter for exported dataset.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="municipio",
                        phase="refinamento",
                        param_type="string",
                        description="Optional municipality name filter for export.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="sexo",
                        phase="refinamento",
                        param_type="string",
                        description="Optional sex filter for export.",
                        required=False,
                        default=None,
                        allowed_values=["M", "F"],
                    ),
                    SourceParameterSpec(
                        name="faixa_etaria",
                        phase="refinamento",
                        param_type="string",
                        description="Optional age-band code filter for export.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="evolucao",
                        phase="refinamento",
                        param_type="string",
                        description="Optional case evolution filter for export.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="classificacao",
                        phase="refinamento",
                        param_type="string",
                        description="Optional classification filter for export.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_sinan_params,
            ),
            PysusDownloadSource(
                descriptor=SourceDescriptor(
                    source="sim",
                    title="SIM",
                    mode="pysus ftp",
                ),
                datasource_cls=SimDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Starting year for file discovery.",
                        required=True,
                        default=last_year,
                        minimum=1979,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ending year for file discovery.",
                        required=True,
                        default=last_year,
                        minimum=1979,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="groups",
                        phase="coleta",
                        param_type="string_list",
                        description="SIM groups to download.",
                        required=False,
                        default=list(SimDataSource.DEFAULT_GROUPS),
                        allowed_values=list(SimDataSource.ALL_GROUPS),
                    ),
                    SourceParameterSpec(
                        name="states",
                        phase="coleta",
                        param_type="string_list",
                        description="UF filter list.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Optional UF filter for exported dataset.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="municipio",
                        phase="refinamento",
                        param_type="string",
                        description="Optional municipality filter for export.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="sexo",
                        phase="refinamento",
                        param_type="string",
                        description="Optional sex filter for export.",
                        required=False,
                        default=None,
                        allowed_values=["M", "F"],
                    ),
                    SourceParameterSpec(
                        name="causa_basica",
                        phase="refinamento",
                        param_type="string",
                        description="Optional basic cause filter for export.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="ano_obito",
                        phase="refinamento",
                        param_type="integer",
                        description="Optional year-of-death filter for export.",
                        required=False,
                        default=None,
                        minimum=1979,
                        maximum=current_year,
                    ),
                ],
                normalize_params=_normalize_sim_params,
            ),
            PysusDownloadSource(
                descriptor=SourceDescriptor(
                    source="sih",
                    title="SIH",
                    mode="pysus ftp",
                ),
                datasource_cls=SihDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for processed datasets.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Starting year for file discovery.",
                        required=True,
                        default=last_year,
                        minimum=1979,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ending year for file discovery.",
                        required=True,
                        default=last_year,
                        minimum=1979,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="groups",
                        phase="coleta",
                        param_type="string_list",
                        description="SIH groups to download. Leave empty to include all groups.",
                        required=False,
                        default=None,
                        allowed_values=list(SihDataSource.ALL_GROUPS),
                    ),
                    SourceParameterSpec(
                        name="states",
                        phase="coleta",
                        param_type="string_list",
                        description="UF filter list.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="months",
                        phase="coleta",
                        param_type="string_list",
                        description="Month list (1-12). Leave empty to include all months.",
                        required=False,
                        default=None,
                        allowed_values=[str(item) for item in range(1, 13)],
                    ),
                    SourceParameterSpec(
                        name="uf",
                        phase="refinamento",
                        param_type="string",
                        description="Optional UF filter for exported dataset.",
                        required=False,
                        default=None,
                        allowed_values=uf_values,
                    ),
                    SourceParameterSpec(
                        name="municipio",
                        phase="refinamento",
                        param_type="string",
                        description="Optional municipality filter for export.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="sexo",
                        phase="refinamento",
                        param_type="string",
                        description="Optional sex filter for export.",
                        required=False,
                        default=None,
                        allowed_values=["M", "F"],
                    ),
                ],
                normalize_params=_normalize_sih_params,
            ),
            *[
                _build_ftp_source(spec, last_year=last_year, uf_values=uf_values)
                for spec in ftp_specs.ALL_SPECS
            ],
            NasaDownloadSource(
                descriptor=SourceDescriptor(
                    source="nasa_power",
                    title="NASA POWER (Clima)",
                    mode="nasa power api",
                ),
                datasource_cls=NasaPowerDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for the climate series.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="latitude",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Latitude do ponto (-90 a 90, decimal). "
                            "Ex.: -23.55 para São Paulo."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="longitude",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Longitude do ponto (-180 a 180, decimal). "
                            "Ex.: -46.63 para São Paulo."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Data inicial (YYYY-MM-DD). Cobertura diária do "
                            "POWER desde 1981."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="coleta",
                        param_type="string",
                        description="Data final (YYYY-MM-DD).",
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="parameters",
                        phase="coleta",
                        param_type="string_list",
                        description="Variáveis climáticas NASA POWER a coletar.",
                        required=False,
                        default=list(NasaPowerDataSource.DEFAULT_PARAMETERS),
                        allowed_values=list(
                            NasaPowerDataSource.SUPPORTED_PARAMETERS.keys()
                        ),
                    ),
                    SourceParameterSpec(
                        name="temporal",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Resolução temporal: daily (diário) ou "
                            "monthly (mensal)."
                        ),
                        required=False,
                        default=NasaPowerDataSource.DEFAULT_TEMPORAL,
                        allowed_values=list(NasaPowerDataSource.VALID_TEMPORAL),
                    ),
                    SourceParameterSpec(
                        name="community",
                        phase="tecnica",
                        param_type="string",
                        description=(
                            "Comunidade POWER: AG (agroclima), "
                            "RE (energia renovável), SB (edificações)."
                        ),
                        required=False,
                        default=NasaPowerDataSource.DEFAULT_COMMUNITY,
                        allowed_values=list(NasaPowerDataSource.VALID_COMMUNITIES),
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description=(
                            "Se true, salva o JSON bruto da resposta além "
                            "da exportação."
                        ),
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="timeout",
                        phase="tecnica",
                        param_type="integer",
                        description="HTTP timeout in seconds.",
                        required=False,
                        default=NasaPowerDataSource.DEFAULT_TIMEOUT,
                        minimum=1,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description="Optional NASA POWER API base URL override.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_nasa_power_params,
            ),
            NasaDownloadSource(
                descriptor=SourceDescriptor(
                    source="nasa_firms",
                    title="NASA FIRMS (Focos de Incêndio)",
                    mode="nasa firms api",
                ),
                datasource_cls=NasaFirmsDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for the detections.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="coleta",
                        param_type="string",
                        description="Data inicial (YYYY-MM-DD).",
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Data final (YYYY-MM-DD). Janelas longas são "
                            "fatiadas em blocos de até 10 dias."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="product",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Produto de satélite FIRMS, a 'source' da API (NRT = "
                            "quase tempo real; SP = processamento padrão/arquivo)."
                        ),
                        required=False,
                        default=NasaFirmsDataSource.DEFAULT_PRODUCT,
                        allowed_values=list(NasaFirmsDataSource.VALID_PRODUCTS),
                    ),
                    SourceParameterSpec(
                        name="country",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Código ISO de 3 letras do país (padrão BRA). "
                            "Ignorado quando 'area' é informado."
                        ),
                        required=False,
                        default=NasaFirmsDataSource.DEFAULT_COUNTRY,
                    ),
                    SourceParameterSpec(
                        name="area",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Caixa delimitadora opcional 'oeste,sul,leste,norte' "
                            "ou 'world'; tem precedência sobre 'country'."
                        ),
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva o CSV bruto além da exportação.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="timeout",
                        phase="tecnica",
                        param_type="integer",
                        description="HTTP timeout in seconds.",
                        required=False,
                        default=NasaFirmsDataSource.DEFAULT_TIMEOUT,
                        minimum=1,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description="Optional NASA FIRMS API base URL override.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_nasa_firms_params,
            ),
            NasaDownloadSource(
                descriptor=SourceDescriptor(
                    source="nasa_gpm",
                    title="NASA GPM IMERG (Precipitação)",
                    mode="nasa gpm api",
                ),
                datasource_cls=NasaGpmDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for the series.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="latitude",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Latitude do ponto (-90 a 90, decimal). "
                            "Ex.: -23.55 para São Paulo."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="longitude",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Longitude do ponto (-180 a 180, decimal). "
                            "Ex.: -46.63 para São Paulo."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="start_date",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Data inicial (YYYY-MM-DD). Uma requisição OPeNDAP "
                            "por dia; janela limitada a ~1 ano."
                        ),
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="end_date",
                        phase="coleta",
                        param_type="string",
                        description="Data final (YYYY-MM-DD).",
                        required=True,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="variable",
                        phase="coleta",
                        param_type="string",
                        description="Variável IMERG (diária GPM_3IMERGDF V07).",
                        required=False,
                        default=NasaGpmDataSource.DEFAULT_VARIABLE,
                        allowed_values=list(NasaGpmDataSource.VALID_VARIABLES),
                    ),
                    SourceParameterSpec(
                        name="product",
                        phase="coleta",
                        param_type="string",
                        description="Produto temporal IMERG (apenas 'daily' por ora).",
                        required=False,
                        default=NasaGpmDataSource.DEFAULT_PRODUCT,
                        allowed_values=list(NasaGpmDataSource.VALID_PRODUCTS),
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva as respostas OPeNDAP brutas.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="timeout",
                        phase="tecnica",
                        param_type="integer",
                        description="HTTP timeout in seconds.",
                        required=False,
                        default=NasaGpmDataSource.DEFAULT_TIMEOUT,
                        minimum=1,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description="Optional GES DISC OPeNDAP base URL override.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_nasa_gpm_params,
            ),
            NasaDownloadSource(
                descriptor=SourceDescriptor(
                    source="ibge_populacao",
                    title="IBGE População Estimada",
                    mode="ibge api",
                ),
                datasource_cls=IbgePopulacaoDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for the population table.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description=(
                            "Ano inicial das estimativas de população "
                            "(IBGE SIDRA tabela 6579, desde 2001)."
                        ),
                        required=False,
                        default=last_year,
                        minimum=2001,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final das estimativas de população.",
                        required=False,
                        default=last_year,
                        minimum=2001,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="level",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Nível territorial: municipio, uf, regiao ou brasil."
                        ),
                        required=False,
                        default=IbgePopulacaoDataSource.DEFAULT_LEVEL,
                        allowed_values=["municipio", "uf", "regiao", "brasil"],
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva o JSON bruto da resposta.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="timeout",
                        phase="tecnica",
                        param_type="integer",
                        description="HTTP timeout in seconds.",
                        required=False,
                        default=IbgePopulacaoDataSource.DEFAULT_TIMEOUT,
                        minimum=1,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description="Optional IBGE API base URL override.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_ibge_params,
            ),
            NasaDownloadSource(
                descriptor=SourceDescriptor(
                    source="ibge_pib_municipios",
                    title="IBGE PIB dos Municípios",
                    mode="ibge api",
                ),
                datasource_cls=IbgePibMunicipiosDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for the GDP table.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano inicial do PIB municipal (IBGE SIDRA 5938, desde 2002).",
                        required=False,
                        default=last_year,
                        minimum=2002,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final do PIB municipal.",
                        required=False,
                        default=last_year,
                        minimum=2002,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="level",
                        phase="coleta",
                        param_type="string",
                        description="Nível territorial: municipio, uf, regiao ou brasil.",
                        required=False,
                        default="municipio",
                        allowed_values=["municipio", "uf", "regiao", "brasil"],
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva o JSON bruto da resposta.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="timeout",
                        phase="tecnica",
                        param_type="integer",
                        description="HTTP timeout in seconds.",
                        required=False,
                        default=IbgePibMunicipiosDataSource.DEFAULT_TIMEOUT,
                        minimum=1,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description="Optional IBGE API base URL override.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_ibge_params,
            ),
            NasaDownloadSource(
                descriptor=SourceDescriptor(
                    source="ibge_populacao_idade_sexo",
                    title="IBGE População por Idade e Sexo (Censo)",
                    mode="ibge api",
                ),
                datasource_cls=IbgePopulacaoIdadeSexoDataSource,
                params_schema=[
                    SourceParameterSpec(
                        name="output_dir",
                        phase="tecnica",
                        param_type="string",
                        description="Output directory for downloaded files.",
                        required=False,
                        default=None,
                    ),
                    SourceParameterSpec(
                        name="output_format",
                        phase="exportacao",
                        param_type="string",
                        description="Optional export format for the age/sex table.",
                        required=False,
                        default=None,
                        allowed_values=EXPORT_FORMAT_VALUES,
                    ),
                    SourceParameterSpec(
                        name="start_year",
                        phase="coleta",
                        param_type="integer",
                        description=(
                            "Ano inicial (população por idade/sexo do Censo, "
                            "IBGE SIDRA 9514; referência 2022)."
                        ),
                        required=False,
                        default=2022,
                        minimum=2010,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="end_year",
                        phase="coleta",
                        param_type="integer",
                        description="Ano final.",
                        required=False,
                        default=2022,
                        minimum=2010,
                        maximum=current_year,
                    ),
                    SourceParameterSpec(
                        name="level",
                        phase="coleta",
                        param_type="string",
                        description="Nível territorial: uf, municipio, regiao ou brasil.",
                        required=False,
                        default="uf",
                        allowed_values=["municipio", "uf", "regiao", "brasil"],
                    ),
                    SourceParameterSpec(
                        name="sexo",
                        phase="coleta",
                        param_type="string",
                        description="Recorte de sexo: ambos, homens, mulheres ou total.",
                        required=False,
                        default="ambos",
                        allowed_values=["ambos", "homens", "mulheres", "total"],
                    ),
                    SourceParameterSpec(
                        name="faixa_etaria",
                        phase="coleta",
                        param_type="string",
                        description=(
                            "Recorte de idade: quinquenal (grupos de 5 anos), "
                            "total ou todos (todas as idades detalhadas)."
                        ),
                        required=False,
                        default="quinquenal",
                        allowed_values=["quinquenal", "total", "todos"],
                    ),
                    SourceParameterSpec(
                        name="keep_raw",
                        phase="tecnica",
                        param_type="boolean",
                        description="Se true, salva o JSON bruto da resposta.",
                        required=False,
                        default=False,
                    ),
                    SourceParameterSpec(
                        name="timeout",
                        phase="tecnica",
                        param_type="integer",
                        description="HTTP timeout in seconds.",
                        required=False,
                        default=IbgePopulacaoIdadeSexoDataSource.DEFAULT_TIMEOUT,
                        minimum=1,
                    ),
                    SourceParameterSpec(
                        name="api_base_url",
                        phase="tecnica",
                        param_type="string",
                        description="Optional IBGE API base URL override.",
                        required=False,
                        default=None,
                    ),
                ],
                normalize_params=_normalize_ibge_params,
            ),
        ]

        # Append the auto-generated OpenDataSUS sources
        from guaraci.services.opendatasus_registry import get_opendatasus_sources
        existing_keys = {self._normalize_source_name(s.descriptor.source) for s in sources}
        for auto_src in get_opendatasus_sources():
            key = self._normalize_source_name(auto_src.descriptor.source)
            if key not in existing_keys:
                sources.append(auto_src)

        return sources

    def register_source(self, source: DownloadSource, replace: bool = False) -> None:
        key = self._normalize_source_name(source.descriptor.source)
        if not replace and key in self._sources:
            raise ValueError(f"Source '{key}' is already registered.")
        self._sources[key] = source

    def _get_registered_source(self, source: str) -> DownloadSource:
        key = self._normalize_source_name(source)
        selected = self._sources.get(key)
        if selected is None:
            supported = ", ".join(sorted(self._sources))
            raise ValueError(f"Unsupported source '{source}'. Supported: {supported}")
        return selected

    @staticmethod
    def _get_source_param_specs(source: DownloadSource) -> List[SourceParameterSpec]:
        getter = getattr(source, "params_schema", None)
        if callable(getter):
            return getter()
        return []

    def list_sources(self) -> List[SourceDescriptor]:
        items = [item.descriptor for item in self._sources.values()]
        return sorted(items, key=lambda item: (item.title.lower(), item.source.lower()))

    def list_source_schemas(self) -> List[Dict[str, object]]:
        return [self.get_source_schema(item.source) for item in self.list_sources()]

    def get_source_schema(self, source: str) -> Dict[str, object]:
        selected = self._get_registered_source(source)
        return {
            "source": selected.descriptor.source,
            "title": selected.descriptor.title,
            "mode": selected.descriptor.mode,
            "params": [item.to_dict() for item in self._get_source_param_specs(selected)],
        }

    def validate_source_params(
        self,
        source: str,
        params: Mapping[str, object],
    ) -> None:
        selected = self._get_registered_source(source)
        selected.validate_params(params)

    def run(
        self,
        source: str,
        *,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
        **kwargs: object,
    ) -> JobResult:
        self.validate_source_params(source=source, params=kwargs)
        selected = self._get_registered_source(source)
        if progress_callback is not None:
            download_with_progress = getattr(selected, "download_with_progress", None)
            if callable(download_with_progress):
                return download_with_progress(progress_callback=progress_callback, **kwargs)
        return selected.download(**kwargs)

    def discover(
        self, source: str, *, fetch_sizes: bool = False, **kwargs: object
    ) -> Dict[str, object]:
        self.validate_source_params(source=source, params=kwargs)
        key = self._normalize_source_name(source)

        if key in _FTP_SOURCE_NAMES:
            prepared = _normalize_ftp_params(dict(kwargs))
            output_dir = prepared.pop("output_dir", None)
            prepared.pop("output_format", None)
            spec = ftp_specs.get_spec(key)
            datasource = FtpDataSource(spec, output_path=output_dir)
            return dict(
                datasource.discover(
                    start_year=int(prepared["start_year"]),
                    end_year=int(prepared["end_year"]),
                    groups=prepared.get("groups"),  # type: ignore[arg-type]
                    states=prepared.get("states"),  # type: ignore[arg-type]
                    fetch_sizes=fetch_sizes,
                )
            )

        if key != "sih":
            raise ValueError(f"Discovery is not supported for source '{source}'.")

        prepared = _normalize_sih_params(dict(kwargs))
        output_dir = prepared.pop("output_dir", None)
        download_kwargs, _ = PysusDownloadSource._split_download_and_postprocess_kwargs(
            PysusDownloadSource(
                descriptor=SourceDescriptor(source="sih", title="SIH", mode="pysus ftp"),
                datasource_cls=SihDataSource,
                params_schema=[],
            ),
            prepared,
        )
        datasource = SihDataSource(output_path=output_dir)
        return dict(datasource.discover(**download_kwargs))

    def download_snis(
        self,
        output_dir: Optional[str] = None,
        results_url: Optional[str] = None,
        file_kinds: Optional[Sequence[str]] = None,
        modules: Optional[Sequence[str]] = None,
        extract_archives: bool = True,
        overwrite: bool = False,
        timeout: int = 120,
    ) -> JobResult:
        return self.run(
            "snis",
            output_dir=output_dir,
            results_url=results_url,
            file_kinds=file_kinds,
            modules=modules,
            extract_archives=extract_archives,
            overwrite=overwrite,
            timeout=timeout,
        )

    def download_sinisa(
        self,
        output_dir: Optional[str] = None,
        results_url: Optional[str] = None,
        file_kinds: Optional[Sequence[str]] = None,
        modules: Optional[Sequence[str]] = None,
        extract_archives: bool = True,
        overwrite: bool = False,
        timeout: int = 120,
    ) -> JobResult:
        return self.run(
            "sinisa",
            output_dir=output_dir,
            results_url=results_url,
            file_kinds=file_kinds,
            modules=modules,
            extract_archives=extract_archives,
            overwrite=overwrite,
            timeout=timeout,
        )


def _normalize_sinan_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)
    diseases = normalized.get("diseases")
    if isinstance(diseases, list):
        normalized["diseases"] = [str(item).strip().upper() for item in diseases if str(item).strip()]
    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None
    sexo = normalized.get("sexo")
    if isinstance(sexo, str):
        normalized["sexo"] = sexo.strip().upper()
    uf = normalized.get("uf")
    if isinstance(uf, str):
        normalized["uf"] = uf.strip().upper()
    return normalized


_FTP_SOURCE_NAMES = frozenset(spec.name for spec in ftp_specs.ALL_SPECS)


def _normalize_ftp_params(params: Dict[str, object]) -> Dict[str, object]:
    """Normalise params for the phase-5 generic FTP DATASUS sources."""
    normalized = dict(params)
    for key in ("groups", "states"):
        value = normalized.get(key)
        if isinstance(value, list):
            normalized[key] = [
                str(item).strip().upper() for item in value if str(item).strip()
            ]
    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None
    return normalized


def _build_ftp_source(spec, *, last_year: int, uf_values: List[str]) -> "PysusDownloadSource":
    """Build a ``PysusDownloadSource`` adapter for one phase-5 FTP system spec.

    The schema is derived from the spec's dimensions: every source exposes
    ``start_year``/``end_year``; only systems with selectable groups expose
    ``groups``; only state-level systems expose ``states``.
    """
    # The in-progress current year is collectable (partial); only genuinely
    # future years are out of range. ``last_year`` is ``current_year - 1`` at
    # the call site, so reconstruct ``current_year`` here for the schema cap.
    current_year = last_year + 1
    schema = [
        SourceParameterSpec(
            name="output_dir",
            phase="tecnica",
            param_type="string",
            description="Output directory for downloaded files.",
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="output_format",
            phase="exportacao",
            param_type="string",
            description="Optional export format for processed datasets.",
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year",
            phase="coleta",
            param_type="integer",
            description="Starting year for file discovery.",
            required=True,
            default=last_year,
            minimum=spec.min_year,
            maximum=current_year,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ending year for file discovery.",
            required=True,
            default=last_year,
            minimum=spec.min_year,
            maximum=current_year,
        ),
    ]
    if spec.groups:
        schema.append(
            SourceParameterSpec(
                name="groups",
                phase="coleta",
                param_type="string_list",
                description=f"{spec.title} groups to download.",
                required=False,
                default=list(spec.default_groups),
                allowed_values=list(spec.groups),
            )
        )
    if spec.has_state:
        schema.append(
            SourceParameterSpec(
                name="states",
                phase="coleta",
                param_type="string_list",
                description="UF filter list.",
                required=False,
                default=None,
                allowed_values=uf_values,
            )
        )

    def _factory(output_path=None, _spec=spec):
        return FtpDataSource(_spec, output_path=output_path)

    return PysusDownloadSource(
        descriptor=SourceDescriptor(source=spec.name, title=spec.title, mode="datasus ftp"),
        datasource_cls=_factory,
        params_schema=schema,
        normalize_params=_normalize_ftp_params,
    )


def _normalize_sim_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)
    groups = normalized.get("groups")
    states = normalized.get("states")
    if isinstance(groups, list):
        normalized["groups"] = [str(item).strip().upper() for item in groups if str(item).strip()]
    if isinstance(states, list):
        normalized["states"] = [str(item).strip().upper() for item in states if str(item).strip()]
    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None
    sexo = normalized.get("sexo")
    if isinstance(sexo, str):
        normalized["sexo"] = sexo.strip().upper()
    uf = normalized.get("uf")
    if isinstance(uf, str):
        normalized["uf"] = uf.strip().upper()
    return normalized


def _normalize_sih_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = _normalize_sim_params(params)
    months = normalized.get("months")
    if isinstance(months, list):
        parsed = []
        for item in months:
            raw = str(item).strip()
            if raw:
                parsed.append(int(raw))
        normalized["months"] = parsed
    mes = normalized.get("mes")
    if mes is not None:
        normalized["mes"] = int(mes)
    return normalized


def _normalize_opendatasus_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)
    dataset = normalized.get("dataset")
    if isinstance(dataset, str):
        normalized["dataset"] = dataset.strip().lower()

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    uf = normalized.get("uf")
    if isinstance(uf, str):
        cleaned_uf = uf.strip().upper()
        normalized["uf"] = cleaned_uf if cleaned_uf else None

    uf_like_keys = {
        "sg_uf",
        "sg_uf_not",
        "uf_notificacao",
        "uf_residencia",
        "uf_paciente",
        "uf_estabelecimento",
        "sigla_unidade_federacao",
    }
    for key, value in list(normalized.items()):
        if key in {
            "dataset",
            "output_format",
            "uf",
            "start_date",
            "end_date",
            "resource_id",
            "api_base_url",
        }:
            continue
        if isinstance(value, str):
            cleaned_value = value.strip()
            if not cleaned_value:
                normalized[key] = None
            elif key in uf_like_keys:
                normalized[key] = cleaned_value.upper()
            else:
                normalized[key] = cleaned_value

    for key in ("start_date", "end_date", "resource_id", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned_value = value.strip()
            normalized[key] = cleaned_value if cleaned_value else None

    for key in ("start_year", "end_year", "batch_size", "max_pages"):
        value = normalized.get(key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                normalized[key] = None
                continue
            normalized[key] = int(stripped)
            continue
        normalized[key] = int(value)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_ibge_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    for key in ("level", "sexo", "faixa_etaria"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                normalized[key] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    api_base_url = normalized.get("api_base_url")
    if isinstance(api_base_url, str):
        normalized["api_base_url"] = api_base_url.strip() or None

    for key in ("start_year", "end_year"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            try:
                normalized[key] = int(value.strip())
            except ValueError:
                pass

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            try:
                normalized["timeout"] = int(stripped)
            except ValueError:
                normalized.pop("timeout", None)
        else:
            normalized.pop("timeout", None)

    return normalized


def _normalize_nasa_power_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    parameters = normalized.get("parameters")
    if isinstance(parameters, list):
        normalized["parameters"] = [
            str(item).strip().upper() for item in parameters if str(item).strip()
        ]

    temporal = normalized.get("temporal")
    if isinstance(temporal, str):
        cleaned = temporal.strip().lower()
        if cleaned:
            normalized["temporal"] = cleaned

    community = normalized.get("community")
    if isinstance(community, str):
        cleaned = community.strip().upper()
        if cleaned:
            normalized["community"] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    for key in ("latitude", "longitude", "start_date", "end_date", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            normalized[key] = cleaned if cleaned else None

    # Empty/invalid timeout is dropped so the datasource default applies; a
    # None timeout would break the int() coercion in the client resolver.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            normalized["timeout"] = int(stripped)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_nasa_firms_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    product = normalized.get("product")
    if isinstance(product, str):
        cleaned = product.strip().upper()
        if cleaned:
            normalized["product"] = cleaned

    country = normalized.get("country")
    if isinstance(country, str):
        cleaned = country.strip().upper()
        if cleaned:
            normalized["country"] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    for key in ("area", "start_date", "end_date", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            normalized[key] = cleaned if cleaned else None

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            normalized["timeout"] = int(stripped)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_nasa_gpm_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    product = normalized.get("product")
    if isinstance(product, str):
        cleaned = product.strip().lower()
        if cleaned:
            normalized["product"] = cleaned

    variable = normalized.get("variable")
    if isinstance(variable, str):
        cleaned = variable.strip()
        if cleaned:
            normalized["variable"] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    for key in ("latitude", "longitude", "start_date", "end_date", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            normalized[key] = cleaned if cleaned else None

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            normalized["timeout"] = int(stripped)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized
