"""Helpers to discover real OpenDataSUS DEMAS endpoints from swagger.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

_PNI_PATH_PATTERN = re.compile(r"^/vacinacao/doses-aplicadas-pni-(\d{4})$")
_UF_PARAM_NAMES = ("uf_estabelecimento", "uf_paciente")


@dataclass(frozen=True)
class DemasPniEndpoint:
    """Metadata for one yearly DEMAS endpoint."""

    year: int
    path: str
    uf_params: tuple[str, ...]


def load_swagger_document(swagger_path: Path) -> Optional[Dict[str, object]]:
    """Load local swagger document as dict or return None when unavailable."""

    try:
        text = swagger_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def discover_pni_endpoints(swagger_document: Mapping[str, object]) -> List[DemasPniEndpoint]:
    """Extract yearly PNI endpoints from swagger `paths`."""

    raw_paths = swagger_document.get("paths")
    if not isinstance(raw_paths, Mapping):
        return []

    discovered: List[DemasPniEndpoint] = []
    for raw_path, item in raw_paths.items():
        if not isinstance(raw_path, str):
            continue
        match = _PNI_PATH_PATTERN.match(raw_path.strip())
        if match is None:
            continue
        year = int(match.group(1))

        if not isinstance(item, Mapping):
            continue
        get_section = item.get("get")
        if not isinstance(get_section, Mapping):
            continue

        params = get_section.get("parameters")
        uf_params: List[str] = []
        if isinstance(params, list):
            for param in params:
                if not isinstance(param, Mapping):
                    continue
                name = str(param.get("name") or "").strip()
                if name in _UF_PARAM_NAMES and name not in uf_params:
                    uf_params.append(name)

        discovered.append(
            DemasPniEndpoint(
                year=year,
                path=raw_path,
                uf_params=tuple(uf_params),
            )
        )

    return sorted(discovered, key=lambda item: item.year)


def load_local_pni_catalog(swagger_path: Path) -> List[DemasPniEndpoint]:
    """Load and parse local swagger into endpoint catalog."""

    document = load_swagger_document(swagger_path)
    if document is None:
        return []
    return discover_pni_endpoints(document)


def discover_get_params_by_path(swagger_document: Mapping[str, object]) -> Dict[str, tuple[str, ...]]:
    """Extract GET query parameter names by path."""

    raw_paths = swagger_document.get("paths")
    if not isinstance(raw_paths, Mapping):
        return {}

    catalog: Dict[str, tuple[str, ...]] = {}
    for raw_path, item in raw_paths.items():
        if not isinstance(raw_path, str):
            continue
        if not isinstance(item, Mapping):
            continue
        get_section = item.get("get")
        if not isinstance(get_section, Mapping):
            continue
        params = get_section.get("parameters")
        names: List[str] = []
        if isinstance(params, list):
            for param in params:
                if not isinstance(param, Mapping):
                    continue
                name = str(param.get("name") or "").strip()
                if name and name not in names:
                    names.append(name)
        catalog[raw_path] = tuple(names)
    return catalog


def load_local_get_params_catalog(swagger_path: Path) -> Dict[str, tuple[str, ...]]:
    """Load local swagger and return GET query parameter catalog by path."""

    document = load_swagger_document(swagger_path)
    if document is None:
        return {}
    return discover_get_params_by_path(document)
