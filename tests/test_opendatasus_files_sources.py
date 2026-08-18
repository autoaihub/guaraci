"""Tests for the 'opendatasus files' family registration and service wiring.

Verifies that srag_arquivos/SISAGUA are registered with the expected schema,
and that DownloadService.discover()/.run() dispatch correctly through the
new PortalFileDownloadSource adapter (guaraci/services/downloads.py) down to
PortalFileDataSource — without any network access (PortalFilesClient is
monkeypatched at the class level).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from guaraci.opendatasus import portal_files as portal_files_module
from guaraci.services.downloads import DownloadService

EXPECTED_SOURCES = [
    "srag_arquivos",
    "sisagua_controle_mensal_parametros_basicos",
    "sisagua_controle_semestral",
    "sisagua_vigilancia_parametros_basicos",
    "sisagua_tratamento_agua",
    "sisagua_populacao_abastecida",
]


def test_all_phase_a_sources_are_registered() -> None:
    service = DownloadService()
    registered = {d.source for d in service.list_sources()}
    for name in EXPECTED_SOURCES:
        assert name in registered, name


def test_phase_a_sources_use_opendatasus_files_mode() -> None:
    service = DownloadService()
    for name in EXPECTED_SOURCES:
        schema = service.get_source_schema(name)
        assert schema["mode"] == "opendatasus files"
        param_names = {p["name"] for p in schema["params"]}
        assert {"start_year", "end_year", "resource_filter", "output_format"} <= param_names
        # 'dataset' is fixed by the adapter (fixed_dataset=name), never user-facing.
        assert "dataset" not in param_names


def _patch_portal_client(monkeypatch, *, dataset_html: str, resource_html_by_id: dict) -> list:
    calls: list = []

    def fake_get_dataset_page(self, slug):  # noqa: ANN001
        calls.append(("dataset_page", slug))
        return dataset_html

    def fake_get_resource_page(self, slug, resource_id):  # noqa: ANN001
        calls.append(("resource_page", slug, resource_id))
        return resource_html_by_id.get(resource_id, "<html></html>")

    def fake_head_content_length(self, url):  # noqa: ANN001
        return 123

    def fake_download_file(self, url, destination: Path, **_kwargs):  # noqa: ANN001
        calls.append(("download", url))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake")
        return 4

    monkeypatch.setattr(
        portal_files_module.PortalFilesClient, "get_dataset_page", fake_get_dataset_page
    )
    monkeypatch.setattr(
        portal_files_module.PortalFilesClient, "get_resource_page", fake_get_resource_page
    )
    monkeypatch.setattr(
        portal_files_module.PortalFilesClient,
        "head_content_length",
        fake_head_content_length,
    )
    monkeypatch.setattr(
        portal_files_module.PortalFilesClient, "download_file", fake_download_file
    )
    return calls


_SLUG = "srag-2019-a-2026"
_RID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
# Mirrors the real dataset-page markup (verified live 2026-08-17): the
# resource name lives in a sibling div.text-weight-bold *before* the anchor,
# whose own text is just "Explorar" — never the resource name.
_DATASET_HTML = (
    '<div class="br-card"><div class="text-weight-bold">2019- Banco vivo 05/01/2025 - PARQUET</div>'
    f'<a href="/dataset/{_SLUG}/resource/{_RID}">Explorar</a></div>'
)
_RESOURCE_HTML = {
    _RID: (
        '<a href="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/'
        'SRAG/2019/INFLUD19.parquet">baixar</a>'
    )
}


def test_download_service_discover_dispatches_to_portal_file_source(
    monkeypatch, tmp_path
) -> None:
    _patch_portal_client(
        monkeypatch, dataset_html=_DATASET_HTML, resource_html_by_id=_RESOURCE_HTML
    )
    service = DownloadService()

    summary = service.discover(
        "srag_arquivos", start_year=2019, end_year=2019, output_dir=str(tmp_path)
    )

    assert summary["documents_found"] == 1
    assert summary["resources"][0]["format"] == "parquet"


def test_download_service_run_dispatches_to_portal_file_source(
    monkeypatch, tmp_path
) -> None:
    calls = _patch_portal_client(
        monkeypatch, dataset_html=_DATASET_HTML, resource_html_by_id=_RESOURCE_HTML
    )
    service = DownloadService()

    result = service.run("srag_arquivos", start_year=2019, end_year=2019, output_dir=str(tmp_path))

    assert result.downloaded_count == 1
    assert any(event[0] == "download" for event in calls)
