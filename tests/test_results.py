"""Tests for standardized download result objects."""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.core.results import JobResult


def test_job_result_statuses() -> None:
    ok = JobResult(source="snis", downloaded_count=1)
    partial = JobResult(source="snis", downloaded_count=1, failed_count=1)
    failed = JobResult(source="snis", downloaded_count=0, failed_count=2)

    assert ok.status == "success"
    assert partial.status == "partial_success"
    assert failed.status == "failed"


def test_job_result_from_mapping_payload() -> None:
    payload = {
        "documents_found": 5,
        "downloaded_count": 4,
        "skipped_count": 1,
        "failed_count": 0,
        "manifest_path": "data/snis/manifest.json",
        "output_dir": "data/snis",
    }
    result = JobResult.from_payload(source="snis", payload=payload)

    assert result.source == "snis"
    assert result.documents_found == 5
    assert result.downloaded_count == 4
    assert result["manifest_path"] == "data/snis/manifest.json"
    assert result.metadata["output_dir"] == "data/snis"


def test_job_result_from_path_payload() -> None:
    result = JobResult.from_payload(source="legacy", payload=Path("out.csv"))

    assert result.source == "legacy"
    assert result.downloaded_count == 1
    assert result.metadata["output_path"] == "out.csv"


def test_job_result_from_payload_rejects_unknown_type() -> None:
    with pytest.raises(TypeError):
        JobResult.from_payload(source="snis", payload=123)
