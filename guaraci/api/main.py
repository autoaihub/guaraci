"""Minimal FastAPI application for Guaraci download operations."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from guaraci import __version__
from guaraci.core.config import config
from guaraci.services import DownloadJobService, DownloadService

app = FastAPI(title="Guaraci API", version=__version__)
download_service = DownloadService()
job_service = DownloadJobService(
    download_service=download_service,
    storage_path=config.data_root / "jobs" / "download_jobs.json",
)
_UI_INDEX_PATH = Path(__file__).with_name("static") / "index.html"
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).with_name("static")),
    name="static",
)


class SourceResponse(BaseModel):
    source: str
    title: str
    mode: str
    supports_discovery: bool = False


class SourceParamResponse(BaseModel):
    name: str
    type: str
    description: str
    phase: str = "coleta"
    required: bool
    default: Optional[object] = None
    allowed_values: Optional[List[str]] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None


class SourceSchemaResponse(BaseModel):
    source: str
    title: str
    mode: str
    params: List[SourceParamResponse]


class DownloadResponse(BaseModel):
    source: str
    status: str
    documents_found: int
    downloaded_count: int
    skipped_count: int
    failed_count: int
    manifest_path: Optional[str]


class SnisDownloadRequest(BaseModel):
    output_dir: Optional[str] = None
    results_url: Optional[str] = None
    file_kinds: Optional[List[str]] = Field(default=None)
    modules: Optional[List[str]] = Field(default=None)
    extract_archives: bool = True
    overwrite: bool = False
    timeout: int = 120


class JobCreateRequest(BaseModel):
    source: str
    params: Dict[str, object] = Field(default_factory=dict)


class SourceDiscoveryRequest(BaseModel):
    params: Dict[str, object] = Field(default_factory=dict)


class SourceDiscoveryResponse(BaseModel):
    source: str
    documents_found: int
    total_size_bytes: int
    by_group: Dict[str, int] = Field(default_factory=dict)
    by_state: Dict[str, int] = Field(default_factory=dict)
    sample: List[Dict[str, object]] = Field(default_factory=list)
    filters: Dict[str, object] = Field(default_factory=dict)


class SourcePreflightResponse(BaseModel):
    source: str
    warnings: List[str] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: str
    source: str
    params: Dict[str, object]
    status: str
    progress: float
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[Dict[str, object]] = None
    error: Optional[str] = None
    cancel_requested: bool = False
    attempt: int = 1
    retry_of: Optional[str] = None
    current_file: Optional[str] = None
    files_total: int = 0
    files_completed: int = 0
    bytes_downloaded: int = 0
    bytes_total: Optional[int] = None
    elapsed_seconds: float = 0.0
    eta_seconds: Optional[float] = None
    output_dir: Optional[str] = None
    events: List[Dict[str, object]] = Field(default_factory=list)


class JobLogResponse(BaseModel):
    timestamp_utc: str
    event: str
    level: str
    message: str


class JobOutputResponse(BaseModel):
    job_id: str
    status: str
    output_dir: Optional[str] = None
    host_output_dir: Optional[str] = None
    manifest_path: Optional[str] = None
    output_format: Optional[str] = None
    export_warning: Optional[str] = None
    exported_files: List[str] = Field(default_factory=list)
    materialized_paths: List[str] = Field(default_factory=list)
    available: bool = False


class OpenOutputResponse(BaseModel):
    opened: bool
    output_dir: str
    host_output_dir: Optional[str] = None
    message: str


def _load_ui_html() -> str:
    if _UI_INDEX_PATH.exists():
        return _UI_INDEX_PATH.read_text(encoding="utf-8")
    return (
        "<html><body><h1>Guaraci UI not found</h1>"
        "<p>Expected file at guaraci/api/static/index.html</p></body></html>"
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui_home() -> HTMLResponse:
    return HTMLResponse(content=_load_ui_html())


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui_index() -> HTMLResponse:
    return HTMLResponse(content=_load_ui_html())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/sources", response_model=List[SourceResponse])
def list_sources() -> List[SourceResponse]:
    return [
        SourceResponse(
            **item.__dict__,
            supports_discovery=download_service.supports_discovery(item.source),
        )
        for item in download_service.list_sources()
    ]


@app.get("/sources/{source}/schema", response_model=SourceSchemaResponse)
def get_source_schema(source: str) -> SourceSchemaResponse:
    try:
        schema = download_service.get_source_schema(source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SourceSchemaResponse(**schema)


@app.post("/sources/{source}/preflight", response_model=SourcePreflightResponse)
def preflight_source(source: str, payload: SourceDiscoveryRequest) -> SourcePreflightResponse:
    """Avisos conhecidos antes de disparar o download (ex.: teto de paginacao).

    Puramente informativo e sem I/O de download: a UI chama isso no clique de
    submissao para o usuario poder desistir antes de gerar um arquivo truncado.
    """
    return SourcePreflightResponse(
        source=source,
        warnings=download_service.preflight_warnings(source, **payload.params),
    )


@app.post("/sources/{source}/discovery", response_model=SourceDiscoveryResponse)
def discover_source(source: str, payload: SourceDiscoveryRequest) -> SourceDiscoveryResponse:
    try:
        discovery = download_service.discover(source, **payload.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        # Não vazar detalhes do ambiente (nomes de módulos) ao cliente.
        raise HTTPException(
            status_code=500,
            detail="Source discovery unavailable: missing optional dependency on the server.",
        ) from exc
    return SourceDiscoveryResponse(**discovery)


@app.post("/downloads/snis", response_model=DownloadResponse)
def download_snis(payload: SnisDownloadRequest) -> DownloadResponse:
    result = download_service.download_snis(**payload.model_dump())
    return DownloadResponse(**result.to_dict())


@app.post("/downloads/sinisa", response_model=DownloadResponse)
def download_sinisa(payload: SnisDownloadRequest) -> DownloadResponse:
    result = download_service.download_sinisa(**payload.model_dump())
    return DownloadResponse(**result.to_dict())


@app.post("/jobs", response_model=JobStatusResponse, status_code=202)
def create_job(payload: JobCreateRequest) -> JobStatusResponse:
    try:
        job = job_service.create_job(source=payload.source, params=payload.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobStatusResponse(**job.to_dict())


@app.get("/jobs", response_model=List[JobStatusResponse])
def list_jobs(limit: int = Query(50, ge=1, le=500)) -> List[JobStatusResponse]:
    jobs = job_service.list_jobs(limit=limit)
    return [JobStatusResponse(**job.to_dict()) for job in jobs]


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    try:
        job = job_service.get_job(job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from exc
    return JobStatusResponse(**job.to_dict())


@app.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(job_id: str) -> JobStatusResponse:
    try:
        job = job_service.cancel_job(job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from exc
    return JobStatusResponse(**job.to_dict())


@app.post("/jobs/{job_id}/retry", response_model=JobStatusResponse, status_code=202)
def retry_job(job_id: str) -> JobStatusResponse:
    try:
        job = job_service.retry_job(job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobStatusResponse(**job.to_dict())


@app.get("/jobs/{job_id}/logs", response_model=List[JobLogResponse])
def get_job_logs(job_id: str, limit: int = Query(200, ge=1, le=2000)) -> List[JobLogResponse]:
    try:
        logs = job_service.get_job_logs(job_id=job_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from exc
    return [JobLogResponse(**item) for item in logs]


@app.get("/jobs/{job_id}/output", response_model=JobOutputResponse)
def get_job_output(job_id: str) -> JobOutputResponse:
    try:
        payload = job_service.get_job_output_info(job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from exc
    return JobOutputResponse(**payload)


@app.post("/jobs/{job_id}/open-output", response_model=OpenOutputResponse)
def open_job_output(job_id: str) -> OpenOutputResponse:
    try:
        payload = job_service.open_job_output_dir(job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OpenOutputResponse(**payload)
