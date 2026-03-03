"""Tests for local OpenDataSUS swagger catalog helpers."""

from __future__ import annotations

import json
from pathlib import Path

from guaraci.opendatasus.utils.swagger_catalog import (
    discover_get_params_by_path,
    discover_pni_endpoints,
    load_local_get_params_catalog,
    load_local_pni_catalog,
    load_swagger_document,
)


def test_discover_pni_endpoints_extracts_year_and_uf_params() -> None:
    payload = {
        "paths": {
            "/vacinacao/doses-aplicadas-pni-2020": {
                "get": {
                    "parameters": [
                        {"name": "uf_estabelecimento"},
                        {"name": "uf_paciente"},
                        {"name": "limit"},
                    ]
                }
            },
            "/vacinacao/doses-aplicadas-pni-2024": {
                "get": {"parameters": [{"name": "limit"}, {"name": "offset"}]}
            },
            "/vacinacao/outro-recurso": {"get": {"parameters": [{"name": "uf"}]}},
        }
    }

    endpoints = discover_pni_endpoints(payload)

    assert [item.year for item in endpoints] == [2020, 2024]
    assert endpoints[0].path == "/vacinacao/doses-aplicadas-pni-2020"
    assert endpoints[0].uf_params == ("uf_estabelecimento", "uf_paciente")
    assert endpoints[1].uf_params == ()


def test_load_swagger_document_and_local_catalog(tmp_path: Path) -> None:
    swagger_path = tmp_path / "swagger.json"
    swagger_path.write_text(
        json.dumps(
            {
                "paths": {
                    "/vacinacao/doses-aplicadas-pni-2025": {
                        "get": {"parameters": [{"name": "limit"}, {"name": "offset"}]}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = load_swagger_document(swagger_path)
    assert isinstance(loaded, dict)

    catalog = load_local_pni_catalog(swagger_path)
    assert len(catalog) == 1
    assert catalog[0].year == 2025


def test_discover_get_params_by_path_reads_get_parameters() -> None:
    payload = {
        "paths": {
            "/arboviroses/zikavirus": {
                "get": {
                    "parameters": [
                        {"name": "limit"},
                        {"name": "offset"},
                        {"name": "sg_uf_not"},
                    ]
                }
            }
        }
    }
    catalog = discover_get_params_by_path(payload)
    assert catalog["/arboviroses/zikavirus"] == ("limit", "offset", "sg_uf_not")


def test_load_local_get_params_catalog(tmp_path: Path) -> None:
    swagger_path = tmp_path / "swagger.json"
    swagger_path.write_text(
        json.dumps(
            {
                "paths": {
                    "/arboviroses/zikavirus": {
                        "get": {
                            "parameters": [{"name": "limit"}, {"name": "offset"}]
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    catalog = load_local_get_params_catalog(swagger_path)
    assert catalog["/arboviroses/zikavirus"] == ("limit", "offset")
