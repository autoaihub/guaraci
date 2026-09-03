"""Contract tests for generated OpenDataSUS DEMAS sources."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import pytest

from guaraci.opendatasus.datasource import OpenDataSUSDataSource
from guaraci.opendatasus.demas_quirks import PAGINATION_PARAM_NAMES, required_filters
from guaraci.opendatasus.utils.swagger_catalog import load_local_get_params_catalog
from guaraci.services.opendatasus_registry import get_opendatasus_sources


STANDARD_GENERATED_PARAMS = {
    "output_dir",
    "output_format",
    "keep_raw",
    "batch_size",
    "max_pages",
    "api_base_url",
}


class _RecordingDemasClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def demas_get(self, path: str, params: Mapping[str, object]):  # noqa: ANN201
        self.calls.append((path, dict(params)))
        return {"items": [{"path": path}]}


def _swagger_path_for_source(source) -> str | None:  # noqa: ANN001
    fixed_dataset = getattr(source, "_fixed_dataset", "")
    if not fixed_dataset:
        return None
    if fixed_dataset in OpenDataSUSDataSource.DATASET_SPECS:
        return None
    return "/" + str(fixed_dataset).lstrip("/")


def _path_params(path: str) -> set[str]:
    return set(re.findall(r"{([^{}]+)}", path))


def test_generated_sources_match_local_swagger_parameters() -> None:
    catalog = load_local_get_params_catalog(OpenDataSUSDataSource.LOCAL_SWAGGER_PATH)

    checked = 0
    for source in get_opendatasus_sources():
        path = _swagger_path_for_source(source)
        if path is None:
            continue
        specs = {item.name: item for item in source.params_schema()}
        expected_native = set(catalog[path]) - PAGINATION_PARAM_NAMES
        actual_native = set(specs) - STANDARD_GENERATED_PARAMS

        assert path in catalog
        # A paginação é do laço de coleta, em qualquer um dos dois esquemas da
        # DEMAS; expô-la como parâmetro deixaria o usuário sobrescrever a
        # janela no meio da varredura.
        assert not (PAGINATION_PARAM_NAMES & set(specs))
        assert actual_native == expected_native

        for name in actual_native:
            assert specs[name].phase == "basico"
        for name in _path_params(path):
            assert specs[name].required is True

        checked += 1

    assert checked >= 50


@pytest.mark.parametrize(
    "source",
    [
        source
        for source in get_opendatasus_sources()
        if _swagger_path_for_source(source) is not None
    ],
    ids=lambda source: source.descriptor.source,
)
def test_generated_source_paths_resolve_and_execute_with_fake_client(source, tmp_path: Path) -> None:  # noqa: ANN001
    dataset = getattr(source, "_fixed_dataset")
    path = "/" + str(dataset).lstrip("/")
    required_values = {name: "1" for name in _path_params(path)}
    # Alguns endpoints respondem 400 sem um filtro de recorte; o primeiro da
    # lista basta para exercitar o caminho feliz.
    filtros_exigidos = required_filters(path)
    filtro_query = {filtros_exigidos[0]: "1"} if filtros_exigidos else {}
    client = _RecordingDemasClient()
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    payload = datasource.download(
        dataset=dataset,
        batch_size=1,
        max_pages=1,
        keep_raw=True,
        **required_values,
        **filtro_query,
    )

    assert payload["downloaded_count"] == 1
    assert client.calls
    resolved_path = client.calls[0][0]
    assert "{" not in resolved_path
    assert "}" not in resolved_path
    for name in required_values:
        # Parâmetro de caminho é consumido na URL, não repetido na query.
        assert name not in client.calls[0][1]
    for name in filtro_query:
        assert client.calls[0][1][name] == "1"


def test_no_generated_source_duplicates_manual_demas_endpoint():
    """Endpoints com spec manual curada não podem reaparecer no registry gerado."""
    from guaraci.opendatasus.datasource import OpenDataSUSDataSource
    from guaraci.services.downloads import DownloadService, OpenDataSUSDownloadSource

    manual_endpoints = {
        str(spec.demas_static_path).strip().lower().lstrip("/")
        for spec in OpenDataSUSDataSource.DATASET_SPECS.values()
        if spec.demas_static_path
    }
    service = DownloadService()
    for src in service._sources.values():
        if not isinstance(src, OpenDataSUSDownloadSource):
            continue
        endpoint = (src.fixed_dataset or "").strip().lower().lstrip("/")
        if "/" in endpoint:  # datasets estilo endpoint vêm do registry gerado
            assert endpoint not in manual_endpoints, (
                f"Endpoint '{endpoint}' duplicado: já coberto por spec manual."
            )
