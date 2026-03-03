"""Focused tests for SINAN download stability helpers."""

from __future__ import annotations

import sys
from concurrent.futures import Future
from types import ModuleType

from guaraci.datasus import sinan as sinan_mod
from guaraci.datasus.sinan import SinanDataSource


def test_sinan_download_uses_single_worker(monkeypatch, tmp_path) -> None:
    class FakeFile:
        def __init__(self, name: str) -> None:
            self._name = name

        def __str__(self) -> str:
            return self._name

    class FakeSinan:
        def get_files(self, dis_code, year):  # noqa: ANN001
            return [FakeFile("RAIVBR23.dbc"), FakeFile("RAIVBR24.dbc")]

    class CapturingExecutor:
        called_max_workers = None

        def __init__(self, max_workers: int):  # noqa: ANN001
            CapturingExecutor.called_max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def submit(self, fn, *args, **kwargs):  # noqa: ANN001
            future = Future()
            try:
                result = fn(*args, **kwargs)
                future.set_result(result)
            except Exception as exc:  # pragma: no cover
                future.set_exception(exc)
            return future

    ds = SinanDataSource(output_path=str(tmp_path))
    ds._sinan_instance = FakeSinan()

    monkeypatch.setattr(sinan_mod, "ThreadPoolExecutor", CapturingExecutor)
    monkeypatch.setattr(ds, "_download_file_safe", lambda file_obj: file_obj)  # noqa: ARG005

    result = ds.download(start_year=2023, end_year=2023, diseases=["RAIV"])

    assert CapturingExecutor.called_max_workers == 1
    assert result["total_files"] == 2
    assert result["successful_downloads"] == 2


def test_download_file_safe_closes_ftp_singleton(monkeypatch, tmp_path) -> None:
    class FakeFtpSingleton:
        close_calls = 0

        @classmethod
        def close(cls) -> None:
            cls.close_calls += 1

    fake_ftp_module = ModuleType("pysus.ftp")
    fake_ftp_module.FTPSingleton = FakeFtpSingleton

    class FakeFile:
        def __init__(self) -> None:
            self.calls = 0

        def download(self):
            self.calls += 1
            return "ok"

    ds = SinanDataSource(output_path=str(tmp_path))
    monkeypatch.setattr(sinan_mod, "PYSUS_AVAILABLE", True)
    monkeypatch.setitem(sys.modules, "pysus.ftp", fake_ftp_module)

    result = ds._download_file_safe(FakeFile())

    assert result == "ok"
    assert FakeFtpSingleton.close_calls >= 2
