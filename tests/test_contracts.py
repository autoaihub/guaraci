"""Tests for shared source contracts and manifest model."""

from __future__ import annotations

import pytest

from guaraci.core.contracts import (
    DownloadManifest,
    SourceParameterSpec,
    validate_source_params,
)


def test_validate_source_params_accepts_valid_payload() -> None:
    specs = [
        SourceParameterSpec(
            name="timeout",
            param_type="integer",
            description="Timeout",
            minimum=1,
        ),
        SourceParameterSpec(
            name="file_kinds",
            param_type="string_list",
            description="Kinds",
            allowed_values=["planilhas", "relatorios"],
        ),
    ]

    validate_source_params(
        params={"timeout": 120, "file_kinds": ["planilhas"]},
        specs=specs,
    )


def test_validate_source_params_rejects_unknown_and_invalid_values() -> None:
    specs = [
        SourceParameterSpec(
            name="timeout",
            param_type="integer",
            description="Timeout",
            minimum=1,
        ),
        SourceParameterSpec(
            name="file_kinds",
            param_type="string_list",
            description="Kinds",
            allowed_values=["planilhas"],
        ),
    ]

    with pytest.raises(ValueError):
        validate_source_params(params={"unknown": True}, specs=specs)

    with pytest.raises(ValueError):
        validate_source_params(params={"timeout": 0}, specs=specs)

    with pytest.raises(ValueError):
        validate_source_params(params={"file_kinds": ["x"]}, specs=specs)


def test_download_manifest_contains_standard_and_legacy_fields() -> None:
    manifest = DownloadManifest(
        source="snis",
        results_url="https://example.org/snis",
        filters={"file_kinds": ["planilhas"]},
        documents_found=3,
        downloaded_files=["a.zip"],
        skipped_files=["b.zip"],
        extracted_dirs=["extracted/a"],
        failed_urls=[],
    ).to_dict(include_legacy_fields=True)

    assert manifest["manifest_schema_version"] == "1.0"
    assert manifest["source"] == "snis"
    assert manifest["results_url"] == "https://example.org/snis"
    assert manifest["stats"]["documents_found"] == 3
    assert manifest["artifacts"]["downloaded_files"] == ["a.zip"]
    assert manifest["timestamp_utc"] == manifest["generated_at_utc"]
    assert manifest["downloaded_files"] == ["a.zip"]
