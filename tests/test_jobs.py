"""Tests for asynchronous job orchestration service."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from guaraci.core.results import JobResult
from guaraci.services.downloads import SourceDescriptor
from guaraci.services.jobs import DownloadJobService


class _DummyDownloadService:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("unsupported source")
        if params.get("invalid_param") is True:
            raise ValueError("Unsupported parameter(s): invalid_param")

    def run(self, source: str, **kwargs):  # noqa: ANN003
        if self.fail:
            raise RuntimeError("simulated error")
        return JobResult(source=source, documents_found=1, downloaded_count=1)

class _NonRetryableError(RuntimeError):
    def __init__(self, msg: str) -> None:
        self.retryable = False
        super().__init__(msg)

class _NonRetryableDownloadService:
    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        pass

    def run(self, source: str, **kwargs):  # noqa: ANN003
        raise _NonRetryableError("simulated non-retryable error")


class _OpenDataSUSDummyDownloadService:
    def list_sources(self):
        return [SourceDescriptor(source="doses_aplicadas_pni", title="OpenDataSUS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "doses_aplicadas_pni":
            raise ValueError("unsupported source")
        if "start_year" not in params or "end_year" not in params:
            raise ValueError("year range is required")

    def run(self, source: str, **kwargs):  # noqa: ANN003
        return JobResult(
            source=source,
            documents_found=kwargs.get("documents_found", 2),
            downloaded_count=kwargs.get("documents_found", 2),
            metadata={"dataset": kwargs.get("dataset")},
        )


class _SlowDownloadService:
    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("unsupported source")

    def run(self, source: str, **kwargs):  # noqa: ANN003
        delay = float(kwargs.get("delay", 0.02))
        time.sleep(delay)
        return JobResult(source=source, documents_found=1, downloaded_count=1)


class _TrackingDownloadService:
    def __init__(self, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self._lock = threading.Lock()
        self._active_by_source: dict[str, int] = {}
        self.max_active_by_source: dict[str, int] = {}
        self._attempt_by_key: dict[str, int] = {}

    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("unsupported source")
        if params.get("invalid_param") is True:
            raise ValueError("invalid param")

    def run(self, source: str, **kwargs):  # noqa: ANN003
        delay = float(kwargs.get("delay", 0.03))
        retry_key = str(kwargs.get("retry_key", "default"))

        with self._lock:
            active = self._active_by_source.get(source, 0) + 1
            self._active_by_source[source] = active
            current_max = self.max_active_by_source.get(source, 0)
            if active > current_max:
                self.max_active_by_source[source] = active
            attempt = self._attempt_by_key.get(retry_key, 0) + 1
            self._attempt_by_key[retry_key] = attempt

        try:
            time.sleep(delay)
            if self.fail_first and attempt == 1:
                raise RuntimeError("simulated transient error")
            return JobResult(source=source, documents_found=1, downloaded_count=1)
        finally:
            with self._lock:
                self._active_by_source[source] = self._active_by_source[source] - 1


class _ProgressDownloadService:
    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("unsupported source")

    def run(self, source: str, **kwargs):  # noqa: ANN003
        callback = kwargs.get("progress_callback")
        if callable(callback):
            callback({"event": "download_start", "documents_total": 1, "source": source})
            callback(
                {
                    "event": "file_start",
                    "source": source,
                    "document_index": 1,
                    "documents_total": 1,
                    "file_path": "data/snis/raw/file.zip",
                    "url": "https://example.org/file.zip",
                }
            )
            callback(
                {
                    "event": "file_progress",
                    "source": source,
                    "document_index": 1,
                    "documents_total": 1,
                    "file_path": "data/snis/raw/file.zip",
                    "url": "https://example.org/file.zip",
                    "file_bytes_downloaded": 512,
                    "file_total_bytes": 1024,
                }
            )
            time.sleep(0.01)
            callback(
                {
                    "event": "file_progress",
                    "source": source,
                    "document_index": 1,
                    "documents_total": 1,
                    "file_path": "data/snis/raw/file.zip",
                    "url": "https://example.org/file.zip",
                    "file_bytes_downloaded": 1024,
                    "file_total_bytes": 1024,
                }
            )
            callback(
                {
                    "event": "file_completed",
                    "source": source,
                    "document_index": 1,
                    "documents_total": 1,
                    "file_path": "data/snis/raw/file.zip",
                    "url": "https://example.org/file.zip",
                    "file_bytes_downloaded": 1024,
                    "file_total_bytes": 1024,
                }
            )
            callback(
                {
                    "event": "download_complete",
                    "source": source,
                    "documents_total": 1,
                    "downloaded_count": 1,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "output_dir": "data/snis",
                }
            )
        return JobResult(
            source=source,
            documents_found=1,
            downloaded_count=1,
            manifest_path="data/snis/manifest.json",
            metadata={"output_dir": "data/snis"},
        )


class _ResultFailedDownloadService:
    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("unsupported source")

    def run(self, source: str, **kwargs):  # noqa: ANN003
        return JobResult(
            source=source,
            documents_found=3,
            downloaded_count=0,
            failed_count=3,
        )


def test_create_job_and_complete() -> None:
    service = DownloadJobService(download_service=_DummyDownloadService())

    job = service.create_job(source="snis", params={"timeout": 1})
    finished = service.wait_for_job(job.job_id, timeout_seconds=2.0)

    assert finished.status == "completed"
    assert finished.result is not None
    assert finished.result.source == "snis"


def test_create_doses_aplicadas_pni_job_and_complete() -> None:
    service = DownloadJobService(download_service=_OpenDataSUSDummyDownloadService())

    job = service.create_job(
        source="doses_aplicadas_pni",
        params={
            "start_year": 2025,
            "end_year": 2025,
            "documents_found": 3,
            "dataset": "doses_aplicadas_pni",
        },
    )
    finished = service.wait_for_job(job.job_id, timeout_seconds=2.0)

    assert finished.status == "completed"
    assert finished.result is not None
    assert finished.result.source == "doses_aplicadas_pni"
    assert finished.result.downloaded_count == 3
    assert finished.result["dataset"] == "doses_aplicadas_pni"


def test_create_job_failure() -> None:
    service = DownloadJobService(download_service=_DummyDownloadService(fail=True))

    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=2.0)

    assert finished.status == "failed"
    assert finished.error == "simulated error"


def test_reject_unknown_source() -> None:
    service = DownloadJobService(download_service=_DummyDownloadService())

    with pytest.raises(ValueError):
        service.create_job(source="unknown", params={})


def test_reject_invalid_params_before_enqueue() -> None:
    service = DownloadJobService(download_service=_DummyDownloadService())

    with pytest.raises(ValueError):
        service.create_job(source="snis", params={"invalid_param": True})


def test_list_jobs_returns_recent_first() -> None:
    service = DownloadJobService(download_service=_DummyDownloadService())

    first = service.create_job(source="snis", params={})
    second = service.create_job(source="snis", params={})

    service.wait_for_job(first.job_id, timeout_seconds=2.0)
    service.wait_for_job(second.job_id, timeout_seconds=2.0)

    listed = service.list_jobs(limit=2)

    assert len(listed) == 2
    assert listed[0].created_at >= listed[1].created_at


def test_persist_and_reload_jobs(tmp_path) -> None:  # noqa: ANN001
    storage_path = tmp_path / "jobs.json"
    service = DownloadJobService(
        download_service=_DummyDownloadService(),
        storage_path=storage_path,
    )

    created = service.create_job(source="snis", params={"timeout": 1})
    finished = service.wait_for_job(created.job_id, timeout_seconds=2.0)

    assert finished.status == "completed"
    assert storage_path.exists()

    restored_service = DownloadJobService(
        download_service=_DummyDownloadService(),
        storage_path=storage_path,
    )
    restored = restored_service.get_job(created.job_id)

    assert restored.status == "completed"
    assert restored.result is not None
    assert restored.result.downloaded_count == 1


def test_restart_marks_inflight_jobs_as_failed(tmp_path) -> None:  # noqa: ANN001
    storage_path = tmp_path / "jobs.json"
    payload = [
        {
            "job_id": "job-1",
            "source": "snis",
            "params": {},
            "status": "running",
            "progress": 30.0,
            "created_at": "2026-02-22T00:00:00+00:00",
            "started_at": "2026-02-22T00:00:05+00:00",
            "finished_at": None,
            "result": None,
            "error": None,
        }
    ]
    storage_path.write_text(json.dumps(payload), encoding="utf-8")

    service = DownloadJobService(
        download_service=_DummyDownloadService(),
        storage_path=storage_path,
    )
    restored = service.get_job("job-1")

    assert restored.status == "failed"
    assert restored.progress == 100.0
    assert restored.error == "Job interrupted by process restart."


def test_concurrent_job_creation_is_thread_safe(tmp_path) -> None:  # noqa: ANN001
    storage_path = tmp_path / "jobs.json"
    service = DownloadJobService(
        download_service=_SlowDownloadService(),
        max_workers=8,
        storage_path=storage_path,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(service.create_job, "snis", {"delay": 0.03})
            for _ in range(20)
        ]
        created_jobs = [future.result(timeout=3.0) for future in futures]

    finished_jobs = [
        service.wait_for_job(job.job_id, timeout_seconds=4.0) for job in created_jobs
    ]
    listed = service.list_jobs(limit=100)

    assert len({job.job_id for job in created_jobs}) == 20
    assert all(job.status == "completed" for job in finished_jobs)
    assert len(listed) == 20
    assert storage_path.exists()


def test_invalid_persisted_json_does_not_break_startup(tmp_path) -> None:  # noqa: ANN001
    storage_path = tmp_path / "jobs.json"
    storage_path.write_text("{invalid json", encoding="utf-8")

    service = DownloadJobService(
        download_service=_DummyDownloadService(),
        storage_path=storage_path,
    )
    assert service.list_jobs(limit=10) == []

    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=2.0)
    assert finished.status == "completed"


def test_cancel_queued_job_marks_canceled() -> None:
    service = DownloadJobService(
        download_service=_SlowDownloadService(),
        max_workers=2,
        source_concurrency_limits={"snis": 1},
    )
    first = service.create_job(source="snis", params={"delay": 0.2})
    second = service.create_job(source="snis", params={"delay": 0.01})

    time.sleep(0.03)
    canceled = service.cancel_job(second.job_id)

    assert canceled.status in {"canceled", "cancel_requested"}
    service.wait_for_job(first.job_id, timeout_seconds=3.0)
    finished_second = service.wait_for_job(second.job_id, timeout_seconds=3.0)
    assert finished_second.status == "canceled"


def test_cancel_running_job_marks_canceled_after_completion() -> None:
    service = DownloadJobService(download_service=_SlowDownloadService(), max_workers=2)

    job = service.create_job(source="snis", params={"delay": 0.2})
    time.sleep(0.05)
    canceled = service.cancel_job(job.job_id)

    assert canceled.status in {"cancel_requested", "canceled"}
    finished = service.wait_for_job(job.job_id, timeout_seconds=3.0)
    assert finished.status == "canceled"


def test_retry_failed_job_creates_new_attempt() -> None:
    service = DownloadJobService(download_service=_TrackingDownloadService(fail_first=True))

    failed = service.create_job(source="snis", params={"retry_key": "abc", "delay": 0.02})
    failed_done = service.wait_for_job(failed.job_id, timeout_seconds=3.0)
    assert failed_done.status == "failed"

    retried = service.retry_job(failed_done.job_id)
    retried_done = service.wait_for_job(retried.job_id, timeout_seconds=3.0)

    assert retried_done.status == "completed"
    assert retried_done.retry_of == failed_done.job_id
    assert retried_done.attempt == failed_done.attempt + 1


def test_retry_rejects_non_retryable_status() -> None:
    service = DownloadJobService(download_service=_DummyDownloadService())

    completed = service.create_job(source="snis", params={})
    completed = service.wait_for_job(completed.job_id, timeout_seconds=2.0)
    assert completed.status == "completed"

    with pytest.raises(ValueError):
        service.retry_job(completed.job_id)


def test_retry_rejects_non_retryable_error_flag() -> None:
    service = DownloadJobService(download_service=_NonRetryableDownloadService())

    failed = service.create_job(source="snis", params={})
    failed = service.wait_for_job(failed.job_id, timeout_seconds=2.0)
    
    assert failed.status == "failed"
    assert failed.error == "simulated non-retryable error"
    assert failed.error_retryable is False

    with pytest.raises(ValueError, match="non-retryable error"):
        service.retry_job(failed.job_id)


def test_job_marks_failed_when_result_payload_is_failed() -> None:
    service = DownloadJobService(download_service=_ResultFailedDownloadService())

    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=2.0)

    assert finished.status == "failed"
    assert finished.result is not None
    assert finished.result.status == "failed"
    retried = service.retry_job(finished.job_id)
    assert retried.retry_of == finished.job_id


def test_source_concurrency_limit_is_respected() -> None:
    tracker = _TrackingDownloadService()
    service = DownloadJobService(
        download_service=tracker,
        max_workers=6,
        source_concurrency_limits={"snis": 1},
    )

    jobs = [service.create_job(source="snis", params={"delay": 0.04}) for _ in range(6)]
    finished = [service.wait_for_job(job.job_id, timeout_seconds=4.0) for job in jobs]

    assert all(job.status == "completed" for job in finished)
    assert tracker.max_active_by_source.get("snis", 0) == 1


def test_job_collects_progress_metrics_and_logs() -> None:
    service = DownloadJobService(download_service=_ProgressDownloadService())

    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=3.0)

    assert finished.status == "completed"
    assert finished.progress == 100.0
    assert finished.files_total == 1
    assert finished.files_completed == 1
    assert finished.bytes_downloaded >= 1024
    assert finished.bytes_total == 1024
    assert finished.output_dir == "data/snis"
    assert len(finished.events) > 0
    logs = service.get_job_logs(finished.job_id, limit=20)
    assert len(logs) > 0
    assert any(item["event"] == "file_completed" for item in logs)


def test_get_job_output_info_reads_output_dir_metadata() -> None:
    service = DownloadJobService(download_service=_ProgressDownloadService())
    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=3.0)
    output = service.get_job_output_info(finished.job_id)

    assert output["available"] is True
    assert output["output_dir"] == "data/snis"
    assert output["manifest_path"] == "data/snis/manifest.json"


def test_get_job_output_info_exposes_export_metadata() -> None:
    class _ExportingDownloadService:
        def list_sources(self):
            return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

        def validate_source_params(self, source: str, params):  # noqa: ANN001
            if source != "snis":
                raise ValueError("unsupported source")

        def run(self, source: str, **kwargs):  # noqa: ANN003
            return JobResult(
                source=source,
                documents_found=1,
                downloaded_count=1,
                metadata={
                    "output_dir": "data/snis",
                    "output_format": "csv",
                    "exported_files": ["data/snis/RJ_2024_2025.csv"],
                    "export_warning": None,
                },
            )

    service = DownloadJobService(download_service=_ExportingDownloadService())
    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=3.0)
    output = service.get_job_output_info(finished.job_id)

    assert output["output_format"] == "csv"
    assert output["exported_files"] == ["data/snis/RJ_2024_2025.csv"]
    assert output["export_warning"] is None


def test_open_job_output_dir_returns_not_opened_in_docker() -> None:
    if not Path("/.dockerenv").exists():
        pytest.skip("Docker-specific behavior")

    service = DownloadJobService(download_service=_ProgressDownloadService())
    job = service.create_job(source="snis", params={})
    finished = service.wait_for_job(job.job_id, timeout_seconds=3.0)

    payload = service.open_job_output_dir(finished.job_id)
    assert payload["opened"] is False
    assert "docker" in str(payload["message"]).lower()


class _SlowLoopDownloadService:
    """Simula um download longo que reporta progresso a cada iteração."""

    def __init__(self) -> None:
        self.iterations_done = 0
        self.started = threading.Event()

    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        pass

    def run(self, source: str, progress_callback=None, **kwargs):  # noqa: ANN001, ANN003
        for index in range(200):
            self.iterations_done = index + 1
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_progress",
                        "file_path": "big_file.zip",
                        "file_bytes_downloaded": index + 1,
                        "file_total_bytes": 200,
                    }
                )
            self.started.set()
            time.sleep(0.01)
        return JobResult(source=source, documents_found=1, downloaded_count=1)


def test_cancel_aborts_in_flight_download(tmp_path: Path):
    """Cancelar deve interromper o download em andamento, não só marcá-lo."""
    slow_service = _SlowLoopDownloadService()
    service = DownloadJobService(
        download_service=slow_service,
        storage_path=tmp_path / "jobs.json",
    )
    job = service.create_job(source="snis", params={})
    assert slow_service.started.wait(timeout=5.0), "download não iniciou"

    service.cancel_job(job.job_id)
    finished = service.wait_for_job(job.job_id, timeout_seconds=10.0)

    assert finished.status == "canceled"
    # O laço tem 200 iterações de 10ms; abortar de verdade significa parar
    # muito antes do fim.
    assert slow_service.iterations_done < 200
