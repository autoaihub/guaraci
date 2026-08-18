"""Tests for the 'opendatasus files' dictionary-sampling category/sampler.

No network: the datasource passed to sample_opendatasus_files() is a fake
stand-in with the same discover()/download() shape as
guaraci.opendatasus.portal_files.PortalFileDataSource, and downloads are
materialized from real (small, in-repo-built) zip/csv bytes on disk.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from guaraci.services.dictionary_sampling import classify_source, sample_opendatasus_files


def test_classify_source_recognises_opendatasus_files_family() -> None:
    assert classify_source("srag_arquivos") == "opendatasus_files"
    assert classify_source("sisagua_pontos_de_captacao") == "opendatasus_files"
    assert classify_source("sisagua_cadastro_carro_pipa_procedencia") == "opendatasus_files"
    # Unrelated source names still fall back to the generic DEMAS category.
    assert classify_source("cnes_estabelecimentos") == "demas_generic"


class _FakePortalFileDataSource:
    """Mimics PortalFileDataSource.discover()/download() for one fixed source."""

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        resources: List[Dict[str, Any]],
        materialized_factory,
    ) -> None:
        self.output_path = Path(output_path) if output_path else None
        self._resources = resources
        self._materialized_factory = materialized_factory

    def discover(self, dataset: str, *, fetch_sizes: bool = False, **_kwargs) -> Dict[str, Any]:
        return {"dataset": dataset, "resources": self._resources}

    def download(self, dataset: str, *, resource_filter=None, keep_raw=False, **_kwargs) -> Dict[str, Any]:
        path = self._materialized_factory(self.output_path)
        return {"materialized_paths": [str(path)]}


def _make_cls(*, resources, materialized_factory):
    def _cls(output_path: Optional[str] = None) -> _FakePortalFileDataSource:
        return _FakePortalFileDataSource(
            output_path, resources=resources, materialized_factory=materialized_factory
        )

    return _cls


def _write_zip_csv(out_dir: Path, *, header: Optional[List[str]], rows: List[List[str]]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_lines = []
    if header:
        csv_lines.append(";".join(f'"{h}"' for h in header))
    for row in rows:
        csv_lines.append(";".join(f'"{v}"' for v in row))
    csv_bytes = ("\r\n".join(csv_lines) + "\r\n").encode("latin1")
    zip_path = out_dir / "resource.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("resource.csv", csv_bytes)
    return zip_path


def test_sample_opendatasus_files_reads_columns_from_small_zip(tmp_path) -> None:
    resources = [{"name": "Pontos de Captação", "format": "csv", "size_bytes": 1024}]
    cls = _make_cls(
        resources=resources,
        materialized_factory=lambda out_dir: _write_zip_csv(
            out_dir, header=["UF", "MUNICIPIO"], rows=[["RS", "SANTIAGO"]]
        ),
    )

    outcome = sample_opendatasus_files(cls, "sisagua_pontos_de_captacao", max_download_mb=20)

    assert outcome["status"] == "ok"
    assert outcome["fields"] == ["UF", "MUNICIPIO"]


def test_sample_opendatasus_files_handles_headerless_source(tmp_path) -> None:
    resources = [{"name": "Cadastro Carro Pipa", "format": "csv", "size_bytes": 1024}]
    cls = _make_cls(
        resources=resources,
        materialized_factory=lambda out_dir: _write_zip_csv(
            out_dir, header=None, rows=[["SUL", "RS", "SANTIAGO"]]
        ),
    )

    outcome = sample_opendatasus_files(cls, "sisagua_cadastro_carro_pipa_procedencia", max_download_mb=20)

    assert outcome["status"] == "ok"
    # No header in the source file: polars falls back to positional names.
    assert len(outcome["fields"]) == 3


def test_sample_opendatasus_files_refuses_large_resource_without_downloading() -> None:
    resources = [{"name": "Controle Mensal", "format": "csv", "size_bytes": 200 * 1024 * 1024}]
    called = {"download": False}

    def _materialized_factory(out_dir):
        called["download"] = True
        raise AssertionError("download() should not be called for an oversized resource")

    cls = _make_cls(resources=resources, materialized_factory=_materialized_factory)

    outcome = sample_opendatasus_files(
        cls, "sisagua_controle_mensal_parametros_basicos", max_download_mb=20
    )

    assert outcome["status"] == "empty"
    assert "20MB" in outcome["note"]
    assert called["download"] is False


def test_sample_opendatasus_files_empty_when_no_resources() -> None:
    cls = _make_cls(resources=[], materialized_factory=lambda out_dir: out_dir)

    outcome = sample_opendatasus_files(cls, "srag_arquivos")

    assert outcome["status"] == "empty"
