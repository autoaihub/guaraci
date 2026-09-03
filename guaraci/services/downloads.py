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

from guaraci.ana import AnaHidroDataSource
from guaraci.core.contracts import (
    DownloadManifest,
    SourceParameterSpec,
    validate_param_relationships,
    validate_source_params,
)
from guaraci.core.results import JobResult
from guaraci.core.security import ensure_allowed_crawl_url, ensure_allowed_output_dir
from guaraci.datasus import SihDataSource, SimDataSource, SinanDataSource
from guaraci.datasus.ftp import specs as ftp_specs
from guaraci.datasus.ftp_source import FtpDataSource
from guaraci.ibge import (
    IbgeAreaTerritorialDataSource,
    IbgeCasamentosDataSource,
    IbgeDivorciosDataSource,
    IbgeNascidosVivosRcDataSource,
    IbgeObitosRcDataSource,
    IbgePibMunicipiosDataSource,
    IbgePopulacaoDataSource,
    IbgePopulacaoIdadeSexoDataSource,
    IbgeSaneamentoAguaDataSource,
    IbgeSaneamentoEsgotoDataSource,
    IbgeSaneamentoLixoDataSource,
)
from guaraci.inmet import InmetEstacoesDataSource
from guaraci.inpe import InpeQueimadasDataSource
from guaraci.nasa import (
    NasaFirmsDataSource,
    NasaGpmDataSource,
    NasaPowerDataSource,
)
from guaraci.opendatasus import OpenDataSUSDataSource, PortalFileDataSource
from guaraci.opendatasus.demas_quirks import check_required_filters
from guaraci.snis import SinisaDataSource, SnisDataSource

# Reexport dos normalizadores (movidos para guaraci/services/normalizers.py)
# para compatibilidade: o registry gerado (opendatasus_registry.py) importa
# _normalize_opendatasus_params deste modulo.
from guaraci.services.normalizers import (  # noqa: F401  (reexports)
    _normalize_ana_hidro_params,
    _normalize_ftp_params,
    _normalize_ibge_params,
    _normalize_inmet_params,
    _normalize_inpe_queimadas_params,
    _normalize_nasa_firms_params,
    _normalize_nasa_gpm_params,
    _normalize_nasa_power_params,
    _normalize_opendatasus_params,
    _normalize_portal_files_params,
    _normalize_sih_params,
    _normalize_sim_params,
    _normalize_sinan_params,
)

EXPORT_FORMAT_VALUES = ["csv", "parquet", "sqlite"]

# Nomes das fontes FTP genericas (fase 5); usados no export e no discover.
_FTP_SOURCE_NAMES = frozenset(spec.name for spec in ftp_specs.ALL_SPECS)


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
        normalize_params: Optional[Callable[[Dict[str, object]], Dict[str, object]]] = None,
    ) -> None:
        self.descriptor = descriptor
        self._datasource_cls = datasource_cls
        self._params_schema = self._build_default_param_schema()
        # Simetria com os demais adapters; hoje nenhuma fonte gov.br usa.
        self._normalize_params = normalize_params

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
        # Normaliza antes de validar (mesmo contrato dos demais adapters),
        # para que a validacao veja os valores canonicos e nao o input cru.
        prepared = self._prepare_kwargs(params)
        validate_source_params(params=prepared, specs=self._params_schema, reject_unknown=True)

    def _prepare_kwargs(self, kwargs: Mapping[str, object]) -> Dict[str, object]:
        prepared = dict(kwargs)
        if self._normalize_params is not None:
            prepared = self._normalize_params(prepared)
        return prepared

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
        # Normaliza antes de validar (ex.: states=["sp"] vira ["SP"]) para que
        # a validacao aceite o mesmo input que o download aceitaria; antes o
        # input cru era rejeitado embora o download normalizasse depois.
        prepared = self._prepare_kwargs(params)
        validate_source_params(params=prepared, specs=self._params_schema, reject_unknown=True)

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
                # Streaming quando a fonte oferece o plano lazy: exportar uma
                # doença com muitos anos não pode exigir todos em memória.
                scan = getattr(datasource, "scan_dataframe", None)
                df = scan(str(disease)) if callable(scan) else datasource.load_dataframe(str(disease))
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
                scan = getattr(datasource, "scan_dataframe", None)
                df = scan(str(group)) if callable(scan) else datasource.load_dataframe(str(group))
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
                scan = getattr(datasource, "scan_dataframe", None)
                df = scan(str(group)) if callable(scan) else datasource.load_dataframe(str(group))
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

    @property
    def fixed_dataset(self) -> Optional[str]:
        """Dataset/endpoint DEMAS fixado nesta fonte (usado no dedup por endpoint)."""
        return self._fixed_dataset

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
        # Alguns endpoints exigem ao menos um de dois filtros, condição que o
        # schema por parâmetro isolado não expressa. Validar aqui, e não no
        # meio da coleta, é o que rende erro de uso limpo na CLI e 400 na API.
        if self._fixed_dataset:
            check_required_filters(self._fixed_dataset, prepared)

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


class ApiDownloadSource:
    """Adapter generico para datasources de APIs HTTP sem estado (NASA, IBGE)."""

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


class PortalFileDownloadSource:
    """Adapter for bulk file datasources (S3-backed, scraped from a portal page).

    Same shape as :class:`OpenDataSUSDownloadSource`, plus a ``discover``
    method so ``DownloadService.discover`` can preflight resources (list of
    files matched) without downloading — see
    :meth:`guaraci.opendatasus.portal_files.PortalFileDataSource.discover`.
    """

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

    @property
    def fixed_dataset(self) -> Optional[str]:
        return self._fixed_dataset

    def params_schema(self) -> List[SourceParameterSpec]:
        return list(self._params_schema)

    def validate_params(self, params: Mapping[str, object]) -> None:
        prepared = self._prepare_kwargs(params)
        prepared.pop("dataset", None)
        validate_source_params(params=prepared, specs=self._params_schema, reject_unknown=True)

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

    def download(self, **kwargs: object) -> JobResult:
        return self._download(progress_callback=None, **kwargs)

    def download_with_progress(
        self,
        progress_callback: Callable[[Dict[str, object]], None],
        **kwargs: object,
    ) -> JobResult:
        return self._download(progress_callback=progress_callback, **kwargs)

    def discover(self, *, fetch_sizes: bool = False, **kwargs: object) -> Dict[str, object]:
        output_dir = kwargs.pop("output_dir", None)
        datasource = self._datasource_cls(output_path=output_dir)
        prepared = self._prepare_kwargs(dict(kwargs))
        prepared.pop("output_dir", None)
        prepared.pop("output_format", None)
        prepared.pop("keep_raw", None)
        if self._fixed_dataset is not None:
            prepared["dataset"] = self._fixed_dataset
        return dict(datasource.discover(fetch_sizes=fetch_sizes, **prepared))


# Deprecated: nome antigo do adapter (também servia IBGE, o que era enganoso).
# Mantido como alias por uma release para consumidores externos.
NasaDownloadSource = ApiDownloadSource


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
        # As specs declarativas por familia vivem em guaraci/services/sources/.
        # Import tardio: esses modulos importam os adapters deste modulo no
        # topo (mesmo padrao do opendatasus_registry); importar cedo criaria
        # ciclo de import.
        from guaraci.services.sources import build_default_sources

        sources: List[DownloadSource] = build_default_sources()

        # Append the auto-generated OpenDataSUS sources.
        # Dedup em duas dimensões: por nome de fonte E por endpoint DEMAS —
        # sem a segunda, o mesmo endpoint entra duas vezes (ex.: 'dengue'
        # manual com filtros temporais vs 'arboviroses_dengue' gerada sem
        # recorte, que baixaria o dataset inteiro).
        from guaraci.services.opendatasus_registry import get_opendatasus_sources

        existing_keys = {self._normalize_source_name(s.descriptor.source) for s in sources}
        manual_endpoints = {
            str(spec.demas_static_path).strip().lower().lstrip("/")
            for spec in OpenDataSUSDataSource.DATASET_SPECS.values()
            if getattr(spec, "demas_static_path", None)
        }
        for auto_src in get_opendatasus_sources():
            key = self._normalize_source_name(auto_src.descriptor.source)
            if key in existing_keys:
                continue
            endpoint_key = (auto_src.fixed_dataset or "").strip().lower().lstrip("/")
            if endpoint_key and endpoint_key in manual_endpoints:
                continue
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
        # Guardrails de segurança antes da validação de schema: URLs de crawl
        # restritas a domínios permitidos (anti-SSRF) e output_dir confinado à
        # raiz configurada (GUARACI_OUTPUT_ROOT), quando definida.
        ensure_allowed_crawl_url(params.get("results_url"))
        ensure_allowed_output_dir(params.get("output_dir"))
        # Regras que cruzam parâmetros (intervalo invertido, data impossível)
        # valem para toda fonte, então ficam aqui e não em cada adapter.
        validate_param_relationships(params)
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

    def supports_discovery(self, source: str) -> bool:
        """Indica se ``discover()`` tem suporte para a fonte informada.

        Usa a mesma lógica de despacho de ``discover()`` (FTP DATASUS, SIH,
        ou qualquer adapter registrado que exponha seu próprio ``discover()``,
        como as fontes ``PortalFileDownloadSource``), para que a API e a UI
        consultem uma única fonte de verdade em vez de duplicar a regra.
        """
        key = self._normalize_source_name(source)
        if key in _FTP_SOURCE_NAMES:
            return True
        if key == "sih":
            return True
        selected = self._get_registered_source(source)
        discover_fn = getattr(selected, "discover", None)
        return callable(discover_fn)

    def discover(
        self, source: str, *, fetch_sizes: bool = False, **kwargs: object
    ) -> Dict[str, object]:
        self.validate_source_params(source=source, params=kwargs)
        key = self._normalize_source_name(source)

        if not self.supports_discovery(source):
            raise ValueError(f"Discovery is not supported for source '{source}'.")

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

        if key == "sih":
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

        # Generic dispatch: any registered source whose adapter exposes its own
        # ``discover(fetch_sizes=..., **kwargs)`` (e.g. PortalFileDownloadSource
        # for the bulk-file opendatasus sources) is preflighted directly.
        selected = self._get_registered_source(source)
        discover_fn = getattr(selected, "discover", None)
        if callable(discover_fn):
            return dict(discover_fn(fetch_sizes=fetch_sizes, **kwargs))

        raise ValueError(f"Discovery is not supported for source '{source}'.")

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
