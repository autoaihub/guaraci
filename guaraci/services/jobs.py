"""Asynchronous job execution for download requests."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional
from uuid import uuid4

from guaraci.core.results import JobResult
from guaraci.services.downloads import DownloadService


@dataclass
class DownloadJob:
    """Represents one asynchronous download execution."""

    job_id: str
    source: str
    params: Dict[str, object]
    status: str
    progress: float
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[JobResult] = None
    error: Optional[str] = None
    error_retryable: bool = True
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
    events: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "job_id": self.job_id,
            "source": self.source,
            "params": self.params,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "error_retryable": self.error_retryable,
            "cancel_requested": self.cancel_requested,
            "attempt": self.attempt,
            "retry_of": self.retry_of,
            "current_file": self.current_file,
            "files_total": self.files_total,
            "files_completed": self.files_completed,
            "bytes_downloaded": self.bytes_downloaded,
            "bytes_total": self.bytes_total,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "eta_seconds": None if self.eta_seconds is None else round(self.eta_seconds, 2),
            "output_dir": self.output_dir,
            "events": list(self.events),
        }


class DownloadJobService:
    """Thread-backed background runner for datasource downloads."""

    TERMINAL_STATES = {"completed", "failed", "canceled"}
    RETRYABLE_STATES = {"failed", "canceled"}
    INTERRUPTED_STATES = {"queued", "running", "cancel_requested"}
    _EVENTS_MAX = 300

    def __init__(
        self,
        download_service: Optional[DownloadService] = None,
        max_workers: int = 2,
        storage_path: Optional[str | Path] = None,
        source_concurrency_limits: Optional[Mapping[str, int]] = None,
        default_source_concurrency: Optional[int] = None,
    ):
        self._download_service = download_service or DownloadService()
        self._jobs: Dict[str, DownloadJob] = {}
        self._lock = threading.RLock()
        self._storage_path = Path(storage_path) if storage_path else None
        self._source_limits = self._normalize_source_limits(source_concurrency_limits)
        self._default_source_concurrency = max(
            1,
            int(default_source_concurrency or max_workers),
        )
        self._source_semaphores: Dict[str, threading.Semaphore] = {}

        if self._storage_path is not None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_persisted_jobs()

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="guaraci-job",
        )

    def create_job(self, source: str, params: Optional[Dict[str, object]] = None) -> DownloadJob:
        parsed_params = dict(params or {})
        normalized_source = source.strip().lower()
        self._download_service.validate_source_params(normalized_source, parsed_params)

        job = DownloadJob(
            job_id=uuid4().hex,
            source=normalized_source,
            params=parsed_params,
            status="queued",
            progress=0.0,
            created_at=self._utcnow(),
            attempt=1,
            retry_of=None,
        )

        with self._lock:
            self._jobs[job.job_id] = job
            self._append_event_locked(job, level="info", message="Job queued.", event="queued")
            self._persist_jobs_locked()

        self._executor.submit(self._run_job, job.job_id)
        return self.get_job(job.job_id)

    def cancel_job(self, job_id: str) -> DownloadJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id]

            if job.status in self.TERMINAL_STATES:
                return self._clone(job)

            if job.status == "queued":
                self._mark_canceled_locked(job, message="Canceled by user.")
                self._append_event_locked(
                    job,
                    level="warning",
                    message="Queued job canceled before start.",
                    event="canceled",
                )
                self._persist_jobs_locked()
                return self._clone(job)

            job.cancel_requested = True
            job.status = "cancel_requested"
            job.error = "Cancellation requested by user."
            job.error_retryable = True
            self._append_event_locked(
                job,
                level="warning",
                message="Cancellation requested.",
                event="cancel_requested",
            )
            self._persist_jobs_locked()
            return self._clone(job)

    def retry_job(self, job_id: str) -> DownloadJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            previous = self._jobs[job_id]

        if previous.status not in self.RETRYABLE_STATES:
            raise ValueError(
                f"Cannot retry job '{job_id}' with status '{previous.status}'. "
                f"Retry allowed only for: {', '.join(sorted(self.RETRYABLE_STATES))}."
            )
        
        if not previous.error_retryable:
            raise ValueError(
                f"Job '{job_id}' failed with a non-retryable error. Check parameters or configuration before trying again."
            )

        params = dict(previous.params)
        self._download_service.validate_source_params(previous.source, params)

        retried = DownloadJob(
            job_id=uuid4().hex,
            source=previous.source,
            params=params,
            status="queued",
            progress=0.0,
            created_at=self._utcnow(),
            attempt=previous.attempt + 1,
            retry_of=previous.job_id,
        )
        with self._lock:
            self._jobs[retried.job_id] = retried
            self._append_event_locked(
                retried,
                level="info",
                message=f"Retry created from {previous.job_id}.",
                event="retry_created",
            )
            self._persist_jobs_locked()

        self._executor.submit(self._run_job, retried.job_id)
        return self.get_job(retried.job_id)

    def get_job(self, job_id: str) -> DownloadJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._clone(self._jobs[job_id])

    def list_jobs(self, limit: int = 50) -> List[DownloadJob]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            return [self._clone(item) for item in items[: max(limit, 0)]]

    def get_job_logs(self, job_id: str, limit: int = 200) -> List[Dict[str, object]]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            events = self._jobs[job_id].events
            if limit <= 0:
                return []
            return [dict(item) for item in events[-limit:]]

    def get_job_output_info(self, job_id: str) -> Dict[str, object]:
        job = self.get_job(job_id)
        output_dir = self._detect_output_dir(job)
        host_output_dir = self._detect_host_output_dir(output_dir)
        result_payload = job.result.to_dict() if job.result else {}
        exported_files = result_payload.get("exported_files")
        materialized_paths = result_payload.get("materialized_paths")
        return {
            "job_id": job.job_id,
            "status": job.status,
            "output_dir": output_dir,
            "host_output_dir": host_output_dir,
            "manifest_path": job.result.manifest_path if job.result else None,
            "output_format": result_payload.get("output_format"),
            "export_warning": result_payload.get("export_warning"),
            "exported_files": (
                list(exported_files) if isinstance(exported_files, list) else []
            ),
            "materialized_paths": (
                list(materialized_paths) if isinstance(materialized_paths, list) else []
            ),
            "available": output_dir is not None,
        }

    def open_job_output_dir(self, job_id: str) -> Dict[str, object]:
        output = self.get_job_output_info(job_id)
        output_dir = output["output_dir"]
        if not output_dir:
            raise ValueError("Output directory not available for this job yet.")

        folder = Path(str(output_dir)).resolve()

        if Path("/.dockerenv").exists():
            host_output_dir = output.get("host_output_dir")
            host_hint = (
                f" Host path: {host_output_dir}."
                if host_output_dir
                else ""
            )
            return {
                "opened": False,
                "output_dir": str(folder),
                "host_output_dir": host_output_dir,
                "message": (
                    "Running in Docker: open folder from host using the path shown above."
                    + host_hint
                ),
            }

        if not folder.exists() or not folder.is_dir():
            raise FileNotFoundError(f"Output directory does not exist: {folder}")

        try:
            system = platform.system().lower()
            if system.startswith("win"):
                subprocess.Popen(["explorer", str(folder)])
            elif system == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError:
            return {
                "opened": False,
                "output_dir": str(folder),
                "host_output_dir": output.get("host_output_dir"),
                "message": (
                    "Could not open folder automatically in this environment. "
                    "Use the output path shown above."
                ),
            }

        return {
            "opened": True,
            "output_dir": str(folder),
            "host_output_dir": output.get("host_output_dir"),
            "message": "Folder open command executed.",
        }

    def wait_for_job(self, job_id: str, timeout_seconds: float = 10.0) -> DownloadJob:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            job = self.get_job(job_id)
            if job.status in self.TERMINAL_STATES:
                return job
            time.sleep(0.01)
        raise TimeoutError(f"Timed out waiting for job {job_id}")

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            source = job.source

        source_semaphore = self._get_source_semaphore(source)
        source_semaphore.acquire()
        started_monotonic = time.monotonic()
        per_file_bytes: Dict[str, int] = {}
        per_file_totals: Dict[str, int] = {}
        completed_files: set[str] = set()
        progress_log_state = {"last_persist_ts": 0.0}

        def progress_callback(event_payload: Dict[str, object]) -> None:
            now = time.monotonic()
            with self._lock:
                if job_id not in self._jobs:
                    return
                running_job = self._jobs[job_id]
                self._apply_progress_event_locked(
                    running_job,
                    event_payload,
                    now,
                    started_monotonic,
                    per_file_bytes,
                    per_file_totals,
                    completed_files,
                )
                should_persist = (now - progress_log_state["last_persist_ts"]) >= 0.5
                if str(event_payload.get("event", "")) in {
                    "file_completed",
                    "file_failed",
                    "file_skipped",
                    "download_complete",
                }:
                    should_persist = True
                if should_persist:
                    self._persist_jobs_locked()
                    progress_log_state["last_persist_ts"] = now

        try:
            with self._lock:
                job = self._jobs[job_id]
                if job.status == "canceled":
                    return
                job.status = "running"
                job.started_at = job.started_at or self._utcnow()
                job.progress = 0.0
                source = job.source
                params = dict(job.params)
                job.error = None
                self._append_event_locked(job, level="info", message="Job started.", event="started")
                self._persist_jobs_locked()

            try:
                result = self._download_service.run(
                    source,
                    progress_callback=progress_callback,
                    **params,
                )
            except Exception as exc:
                with self._lock:
                    job = self._jobs[job_id]
                    if job.cancel_requested:
                        self._mark_canceled_locked(job, message="Canceled by user.")
                        self._append_event_locked(
                            job,
                            level="warning",
                            message="Job canceled during execution.",
                            event="canceled",
                        )
                    else:
                        job.status = "failed"
                        job.finished_at = self._utcnow()
                        job.progress = 100.0
                        job.error = str(exc)
                        if hasattr(exc, "retryable"):
                            job.error_retryable = bool(getattr(exc, "retryable", True))
                        else:
                            job.error_retryable = True
                        self._append_event_locked(
                            job,
                            level="error",
                            message=f"Job failed: {exc}",
                            event="failed",
                        )
                    job.elapsed_seconds = max(0.0, time.monotonic() - started_monotonic)
                    job.eta_seconds = None
                    self._persist_jobs_locked()
                return

            with self._lock:
                job = self._jobs[job_id]
                if job.cancel_requested:
                    self._mark_canceled_locked(job, message="Canceled by user.")
                    self._append_event_locked(
                        job,
                        level="warning",
                        message="Job canceled before completion.",
                        event="canceled",
                    )
                else:
                    job.finished_at = self._utcnow()
                    job.progress = 100.0
                    job.result = result
                    job.output_dir = self._detect_output_dir(job)
                    if result.status == "failed":
                        job.status = "failed"
                        job.error = (
                            "Download finished with no successful files. "
                            f"Failed files: {result.failed_count}."
                        )
                        self._append_event_locked(
                            job,
                            level="error",
                            message=job.error,
                            event="failed",
                        )
                    else:
                        job.status = "completed"
                        job.error = None
                        completion_message = "Job completed successfully."
                        if result.status == "partial_success":
                            completion_message = (
                                "Job completed with partial success. "
                                f"Failures: {result.failed_count}."
                            )
                        self._append_event_locked(
                            job,
                            level="info",
                            message=completion_message,
                            event="completed",
                        )
                job.elapsed_seconds = max(0.0, time.monotonic() - started_monotonic)
                job.eta_seconds = None
                self._persist_jobs_locked()
        finally:
            source_semaphore.release()

    def _apply_progress_event_locked(
        self,
        job: DownloadJob,
        event_payload: Dict[str, object],
        now: float,
        started_monotonic: float,
        per_file_bytes: Dict[str, int],
        per_file_totals: Dict[str, int],
        completed_files: set[str],
    ) -> None:
        event = str(event_payload.get("event", "progress"))
        file_key = self._event_file_key(event_payload)

        docs_total = self._to_int(event_payload.get("documents_total"), default=job.files_total)
        if docs_total > 0:
            job.files_total = docs_total
        files_completed_hint = self._to_int(
            event_payload.get("files_completed"),
            default=job.files_completed,
        )
        if files_completed_hint > job.files_completed:
            job.files_completed = min(files_completed_hint, max(job.files_total, files_completed_hint))

        if event in {"file_start", "file_progress", "file_completed", "file_failed", "file_skipped"}:
            current_file = event_payload.get("file_path") or event_payload.get("url")
            if current_file is not None:
                job.current_file = self._short_name(current_file)

        if event in {"file_progress", "file_completed"} and file_key:
            new_file_bytes = self._to_int(event_payload.get("file_bytes_downloaded"), default=0)
            previous_file_bytes = per_file_bytes.get(file_key, 0)
            if new_file_bytes < previous_file_bytes:
                previous_file_bytes = 0
            delta = max(0, new_file_bytes - previous_file_bytes)
            if delta > 0:
                job.bytes_downloaded += delta
                per_file_bytes[file_key] = new_file_bytes

            file_total_bytes = self._to_int(event_payload.get("file_total_bytes"), default=0)
            if file_total_bytes > 0:
                previous_total = per_file_totals.get(file_key, 0)
                if job.bytes_total is None:
                    job.bytes_total = 0
                if file_total_bytes > previous_total:
                    job.bytes_total += file_total_bytes - previous_total
                    per_file_totals[file_key] = file_total_bytes

        if event in {"file_completed", "file_failed", "file_skipped"} and file_key:
            if file_key not in completed_files:
                completed_files.add(file_key)
                job.files_completed += 1

        if event == "download_complete":
            output_dir = event_payload.get("output_dir")
            if output_dir:
                job.output_dir = str(output_dir)

        self._recompute_progress_locked(job, event_payload, now, started_monotonic)

        should_append = event in {
            "download_start",
            "file_start",
            "file_completed",
            "file_failed",
            "file_skipped",
            "file_extracted",
            "download_complete",
        }

        if should_append:
            message = self._event_to_message(job, event_payload)
            level = "info"
            if event in {"file_failed"}:
                level = "error"
            elif event in {"file_skipped", "cancel_requested"}:
                level = "warning"
            self._append_event_locked(job, level=level, message=message, event=event)

    def _recompute_progress_locked(
        self,
        job: DownloadJob,
        event_payload: Dict[str, object],
        now: float,
        started_monotonic: float,
    ) -> None:
        progress_candidates: List[float] = []

        if job.files_total > 0:
            progress_candidates.append((job.files_completed / job.files_total) * 100.0)

        if job.bytes_total is not None and job.bytes_total > 0:
            progress_candidates.append((job.bytes_downloaded / job.bytes_total) * 100.0)

        doc_index = self._to_int(event_payload.get("document_index"), default=0)
        docs_total = self._to_int(event_payload.get("documents_total"), default=0)
        file_bytes = self._to_int(event_payload.get("file_bytes_downloaded"), default=0)
        file_total = self._to_int(event_payload.get("file_total_bytes"), default=0)
        if doc_index > 0 and docs_total > 0 and file_total > 0:
            frac = min(1.0, max(0.0, file_bytes / file_total))
            progress_candidates.append(((doc_index - 1 + frac) / docs_total) * 100.0)

        if progress_candidates:
            job.progress = min(99.5, max(progress_candidates))

        job.elapsed_seconds = max(0.0, now - started_monotonic)
        if job.progress > 0.0 and job.progress < 100.0:
            job.eta_seconds = job.elapsed_seconds * ((100.0 - job.progress) / job.progress)
        else:
            job.eta_seconds = None

    def _event_to_message(self, job: DownloadJob, event_payload: Dict[str, object]) -> str:
        event = str(event_payload.get("event", "progress"))
        file_path = event_payload.get("file_path") or event_payload.get("url")
        file_name = self._short_name(file_path)
        if event == "download_start":
            total = self._to_int(event_payload.get("documents_total"), default=0)
            return f"Download started. Files to process: {total}."
        if event == "file_start":
            return f"Starting download: {file_name}."
        if event == "file_progress":
            return f"Progress updated ({job.progress:.1f}%)."
        if event == "file_completed":
            return f"Finished download: {file_name}."
        if event == "file_extracted":
            extracted_dir = event_payload.get("extracted_dir")
            return f"Extracted archive to {self._short_name(extracted_dir)}."
        if event == "file_failed":
            error = event_payload.get("error")
            return f"Download failed: {file_name} ({error})"
        if event == "file_skipped":
            reason = event_payload.get("reason", "unknown")
            return f"Skipped {file_name} (reason: {reason})."
        if event == "download_complete":
            pages_scanned = self._to_int(event_payload.get("pages_scanned"), default=0)
            downloaded = self._to_int(event_payload.get("downloaded_count"), default=0)
            if pages_scanned > 0:
                return (
                    "Download pipeline completed. "
                    f"Pages processed: {pages_scanned}. Records downloaded: {downloaded}."
                )
            return "Download pipeline completed."
        return f"Event: {event}."

    @staticmethod
    def _short_name(path_or_url: object) -> str:
        if path_or_url is None:
            return "--"
        raw = str(path_or_url).strip()
        if not raw:
            return "--"
        return Path(raw).name or raw

    @staticmethod
    def _event_file_key(event_payload: Dict[str, object]) -> Optional[str]:
        file_path = event_payload.get("file_path")
        if file_path:
            return str(file_path)
        url = event_payload.get("url")
        if url:
            return str(url)
        return None

    def _mark_canceled_locked(self, job: DownloadJob, message: str) -> None:
        job.status = "canceled"
        job.cancel_requested = True
        job.finished_at = self._utcnow()
        job.progress = 100.0
        job.result = None
        job.error = message
        job.error_retryable = True
        job.eta_seconds = None

    def _get_source_semaphore(self, source: str) -> threading.Semaphore:
        normalized = source.strip().lower()
        with self._lock:
            semaphore = self._source_semaphores.get(normalized)
            if semaphore is not None:
                return semaphore

            limit = self._source_limits.get(normalized, self._default_source_concurrency)
            semaphore = threading.Semaphore(max(1, limit))
            self._source_semaphores[normalized] = semaphore
            return semaphore

    @staticmethod
    def _normalize_source_limits(
        source_concurrency_limits: Optional[Mapping[str, int]],
    ) -> Dict[str, int]:
        normalized: Dict[str, int] = {}
        if not source_concurrency_limits:
            return normalized
        for source, raw_limit in source_concurrency_limits.items():
            limit = int(raw_limit)
            if limit <= 0:
                raise ValueError(
                    f"Invalid concurrency limit for source '{source}': {raw_limit}. "
                    "Limit must be >= 1."
                )
            normalized[source.strip().lower()] = limit
        return normalized

    def _detect_output_dir(self, job: DownloadJob) -> Optional[str]:
        if job.output_dir:
            return job.output_dir
        if job.result is None:
            return None
        from_metadata = job.result.metadata.get("output_dir")
        if from_metadata:
            return str(from_metadata)
        if job.result.manifest_path:
            manifest = Path(job.result.manifest_path)
            return str(manifest.parent)
        return None

    @staticmethod
    def _detect_host_output_dir(output_dir: Optional[str]) -> Optional[str]:
        if not output_dir:
            return None
        resolved = str(Path(output_dir).resolve())

        mappings = [
            (
                os.getenv("GUARACI_CONTAINER_DOWNLOADS_ROOT", "/downloads"),
                os.getenv("GUARACI_HOST_DOWNLOADS_ROOT"),
            ),
            (
                os.getenv("GUARACI_CONTAINER_APP_ROOT", "/app"),
                os.getenv("GUARACI_HOST_APP_ROOT"),
            ),
        ]

        for container_root_raw, host_root in mappings:
            if not host_root:
                continue
            container_root = str(container_root_raw or "").rstrip("/")
            if not container_root:
                continue
            prefix = f"{container_root}/"
            if resolved == container_root:
                suffix = ""
            elif resolved.startswith(prefix):
                suffix = resolved[len(prefix) :]
            else:
                continue

            host_sep = "\\" if ("\\" in host_root or ":" in host_root) else "/"
            host_root_clean = host_root.rstrip("\\/")
            if not suffix:
                return host_root_clean
            mapped_suffix = suffix.replace("/", host_sep)
            return f"{host_root_clean}{host_sep}{mapped_suffix}"

        return None

    @staticmethod
    def _clone(job: DownloadJob) -> DownloadJob:
        return DownloadJob(
            job_id=job.job_id,
            source=job.source,
            params=dict(job.params),
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            result=job.result,
            error=job.error,
            error_retryable=job.error_retryable,
            cancel_requested=job.cancel_requested,
            attempt=job.attempt,
            retry_of=job.retry_of,
            current_file=job.current_file,
            files_total=job.files_total,
            files_completed=job.files_completed,
            bytes_downloaded=job.bytes_downloaded,
            bytes_total=job.bytes_total,
            elapsed_seconds=job.elapsed_seconds,
            eta_seconds=job.eta_seconds,
            output_dir=job.output_dir,
            events=[dict(item) for item in job.events],
        )

    def _append_event_locked(
        self,
        job: DownloadJob,
        *,
        level: str,
        message: str,
        event: str,
    ) -> None:
        job.events.append(
            {
                "timestamp_utc": self._utcnow_compact(),
                "event": event,
                "level": level,
                "message": message,
            }
        )
        if len(job.events) > self._EVENTS_MAX:
            job.events = job.events[-self._EVENTS_MAX :]

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _utcnow_compact() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _to_jsonable(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): DownloadJobService._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [DownloadJobService._to_jsonable(item) for item in value]
        return str(value)

    def _persist_jobs_locked(self) -> None:
        if self._storage_path is None:
            return
        payload = [
            self._to_jsonable(item.to_dict())
            for item in sorted(self._jobs.values(), key=lambda job: job.created_at)
        ]
        tmp_path = self._storage_path.with_suffix(f"{self._storage_path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._storage_path)

    def _load_persisted_jobs(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return

        try:
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return

        changed = False
        for item in raw:
            if not isinstance(item, dict):
                continue
            job = self._job_from_payload(item)
            if job.status in self.INTERRUPTED_STATES:
                job.status = "failed"
                job.progress = 100.0
                job.finished_at = job.finished_at or self._utcnow()
                job.error = job.error or "Job interrupted by process restart."
                job.eta_seconds = None
                self._append_event_locked(
                    job,
                    level="warning",
                    message="Job interrupted by process restart.",
                    event="interrupted",
                )
                changed = True
            if not job.output_dir:
                job.output_dir = self._detect_output_dir(job)
            self._jobs[job.job_id] = job

        if changed:
            with self._lock:
                self._persist_jobs_locked()

    def _job_from_payload(self, payload: Dict[str, object]) -> DownloadJob:
        source = str(payload.get("source", "unknown"))
        result_payload = payload.get("result")
        result = (
            JobResult.from_payload(source=source, payload=result_payload)
            if isinstance(result_payload, dict)
            else None
        )
        params = payload.get("params")
        parsed_params = params if isinstance(params, dict) else {}
        started_at = self._optional_str(payload.get("started_at"))
        finished_at = self._optional_str(payload.get("finished_at"))
        error = self._optional_str(payload.get("error"))
        retry_of = self._optional_str(payload.get("retry_of"))

        events_raw = payload.get("events")
        parsed_events: List[Dict[str, object]] = []
        if isinstance(events_raw, list):
            for item in events_raw:
                if isinstance(item, dict):
                    parsed_events.append({str(k): v for k, v in item.items()})

        return DownloadJob(
            job_id=str(payload.get("job_id", uuid4().hex)),
            source=source,
            params=parsed_params,
            status=str(payload.get("status", "failed")),
            progress=self._to_float(payload.get("progress"), default=0.0),
            created_at=str(payload.get("created_at", self._utcnow())),
            started_at=started_at,
            finished_at=finished_at,
            result=result,
            error=error,
            cancel_requested=bool(payload.get("cancel_requested", False)),
            attempt=self._to_int(payload.get("attempt"), default=1),
            retry_of=retry_of,
            current_file=self._optional_str(payload.get("current_file")),
            files_total=self._to_int(payload.get("files_total"), default=0),
            files_completed=self._to_int(payload.get("files_completed"), default=0),
            bytes_downloaded=self._to_int(payload.get("bytes_downloaded"), default=0),
            bytes_total=self._optional_int(payload.get("bytes_total")),
            elapsed_seconds=self._to_float(payload.get("elapsed_seconds"), default=0.0),
            eta_seconds=self._optional_float(payload.get("eta_seconds")),
            output_dir=self._optional_str(payload.get("output_dir")),
            events=parsed_events,
        )

    @staticmethod
    def _optional_str(value: object) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _to_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_float(value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: object, default: int = 1) -> int:
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_int(value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
