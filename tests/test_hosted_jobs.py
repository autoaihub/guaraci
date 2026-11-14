"""Fila multiusuário do modo hospedado: dono, cotas, revezamento e faxina."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from guaraci.core.results import JobResult
from guaraci.services.downloads import SourceDescriptor
from guaraci.services.job_policy import JobLimitError, JobPolicy
from guaraci.services.jobs import DownloadJobService


class _FileWritingService:
    """Escreve um arquivo na pasta de saída e, se pedido, segura até liberar."""

    def __init__(self, *, hold: bool = False, estimate: int = 0, chunks: int = 0) -> None:
        self.release = threading.Event()
        if not hold:
            self.release.set()
        self.order: list[str] = []
        self.estimate = estimate
        self.chunks = chunks
        self._lock = threading.Lock()

    def list_sources(self):
        return [SourceDescriptor(source="snis", title="SNIS", mode="mock")]

    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("unsupported source")

    def supports_discovery(self, source: str) -> bool:
        return self.estimate > 0

    def discover(self, source: str, **kwargs):  # noqa: ANN003
        return {"total_size_bytes": self.estimate}

    def run(self, source: str, progress_callback=None, **kwargs):  # noqa: ANN001, ANN003
        with self._lock:
            self.order.append(str(kwargs.get("tag", "")))
        for index in range(self.chunks):
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_progress",
                        "file_path": "grande.csv",
                        "file_bytes_downloaded": (index + 1) * 1000,
                        "file_total_bytes": self.chunks * 1000,
                    }
                )
        self.release.wait(timeout=10)
        folder = Path(str(kwargs["output_dir"]))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "dados.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        return JobResult(source=source, documents_found=1, downloaded_count=1)


def _policy(tmp_path: Path, **overrides) -> JobPolicy:
    values = dict(
        max_running_per_owner=1,
        max_active_per_owner=3,
        max_jobs_per_day=10,
        max_active_global=40,
        output_root=tmp_path / "saidas",
        output_ttl_hours=48,
    )
    values.update(overrides)
    return JobPolicy(**values)


def _service(tmp_path: Path, download, **overrides) -> DownloadJobService:
    return DownloadJobService(
        download_service=download,
        storage_path=tmp_path / "jobs.json",
        max_workers=overrides.pop("max_workers", 2),
        policy=_policy(tmp_path, **overrides),
    )


def test_output_dir_is_confined_to_owner_folder(tmp_path: Path) -> None:
    service = _service(tmp_path, _FileWritingService())
    job = service.create_job("snis", {"output_dir": "C:/Windows"}, owner_id="7")
    finished = service.wait_for_job(job.job_id)

    folder = Path(str(finished.params["output_dir"]))
    assert folder == tmp_path / "saidas" / "users" / "7" / job.job_id
    assert (folder / "dados.csv").exists()
    assert finished.expires_at is not None


def test_other_owner_cannot_see_or_cancel(tmp_path: Path) -> None:
    service = _service(tmp_path, _FileWritingService())
    job = service.create_job("snis", {}, owner_id="1")
    service.wait_for_job(job.job_id)

    with pytest.raises(KeyError):
        service.get_job(job.job_id, owner_id="2")
    with pytest.raises(KeyError):
        service.cancel_job(job.job_id, owner_id="2")
    assert service.list_jobs(owner_id="2") == []
    assert [item.job_id for item in service.list_jobs(owner_id="1")] == [job.job_id]


def test_active_limit_per_owner(tmp_path: Path) -> None:
    download = _FileWritingService(hold=True)
    service = _service(tmp_path, download, max_active_per_owner=2)
    try:
        service.create_job("snis", {}, owner_id="1")
        service.create_job("snis", {}, owner_id="1")
        with pytest.raises(JobLimitError) as excinfo:
            service.create_job("snis", {}, owner_id="1")
        assert excinfo.value.status_code == 429
        # Outro usuário segue livre.
        service.create_job("snis", {}, owner_id="2")
    finally:
        download.release.set()


def test_daily_limit_and_user_override(tmp_path: Path) -> None:
    service = _service(tmp_path, _FileWritingService(), max_jobs_per_day=1)
    first = service.create_job("snis", {}, owner_id="1")
    service.wait_for_job(first.job_id)
    with pytest.raises(JobLimitError):
        service.create_job("snis", {}, owner_id="1")

    # Cota própria do usuário substitui o teto da política.
    extra = service.create_job("snis", {}, owner_id="1", daily_limit=3)
    service.wait_for_job(extra.job_id)
    assert service.owner_usage("1")["last_24h"] == 2


def test_global_queue_full_returns_503(tmp_path: Path) -> None:
    download = _FileWritingService(hold=True)
    service = _service(tmp_path, download, max_active_global=1)
    try:
        service.create_job("snis", {}, owner_id="1")
        with pytest.raises(JobLimitError) as excinfo:
            service.create_job("snis", {}, owner_id="2")
        assert excinfo.value.status_code == 503
    finally:
        download.release.set()


def test_volume_precheck_rejects_big_request(tmp_path: Path) -> None:
    service = _service(tmp_path, _FileWritingService(estimate=5_000_000), max_job_bytes=1_000_000)
    with pytest.raises(JobLimitError) as excinfo:
        service.create_job("snis", {}, owner_id="1")
    assert excinfo.value.status_code == 413
    assert service.list_jobs() == []


def test_runtime_byte_cut_fails_job_without_retry(tmp_path: Path) -> None:
    service = _service(tmp_path, _FileWritingService(chunks=10), max_job_bytes=3_000)
    job = service.create_job("snis", {}, owner_id="1")
    finished = service.wait_for_job(job.job_id)

    assert finished.status == "failed"
    assert "limite" in (finished.error or "")
    with pytest.raises(ValueError):
        service.retry_job(job.job_id, owner_id="1")


def test_fair_scheduling_alternates_owners(tmp_path: Path) -> None:
    download = _FileWritingService(hold=True)
    service = _service(tmp_path, download, max_workers=1, max_active_per_owner=5)
    jobs = [
        service.create_job("snis", {"tag": "a1"}, owner_id="a"),
        service.create_job("snis", {"tag": "a2"}, owner_id="a"),
        service.create_job("snis", {"tag": "a3"}, owner_id="a"),
        service.create_job("snis", {"tag": "b1"}, owner_id="b"),
    ]
    download.release.set()
    for job in jobs:
        service.wait_for_job(job.job_id)
    # Com uma vaga, "b" não espera as três coletas de "a".
    assert download.order.index("b1") < download.order.index("a3")


def test_cancel_queued_job_leaves_queue(tmp_path: Path) -> None:
    download = _FileWritingService(hold=True)
    service = _service(tmp_path, download, max_workers=1)
    try:
        running = service.create_job("snis", {}, owner_id="a")
        queued = service.create_job("snis", {}, owner_id="b")
        canceled = service.cancel_job(queued.job_id, owner_id="b")
        assert canceled.status == "canceled"
    finally:
        download.release.set()
    service.wait_for_job(running.job_id)
    time.sleep(0.05)
    assert service.get_job(queued.job_id).status == "canceled"


def test_purge_expired_outputs_removes_only_inside_root(tmp_path: Path) -> None:
    service = _service(tmp_path, _FileWritingService())
    job = service.create_job("snis", {}, owner_id="1")
    service.wait_for_job(job.job_id)
    folder = service.job_output_folder(job.job_id, owner_id="1")
    assert folder is not None and folder.exists()

    assert service.purge_expired_outputs() == []
    later = datetime.now(timezone.utc) + timedelta(hours=49)
    assert service.purge_expired_outputs(now=later) == [job.job_id]

    assert not folder.exists()
    assert (tmp_path / "saidas").exists()
    assert service.job_output_folder(job.job_id, owner_id="1") is None
    info = service.get_job_output_info(job.job_id, owner_id="1")
    assert info["available"] is False
