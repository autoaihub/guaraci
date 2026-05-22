#!/usr/bin/env python3
"""Low-volume smoke checks for registered OpenDataSUS sources.

This script intentionally requests at most one small page per source. Path-based
sources are skipped unless sample values are provided with --samples.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from guaraci.services import DownloadService  # noqa: E402


STANDARD_FIELDS = {"output_dir", "output_format", "keep_raw", "batch_size", "max_pages"}


def _load_samples(path: str | None) -> Dict[str, Dict[str, object]]:
    if not path:
        return {}
    sample_path = Path(path)
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--samples must point to a JSON object")
    return {
        str(source): dict(values)
        for source, values in payload.items()
        if isinstance(values, Mapping)
    }


def _selected_sources(service: DownloadService, selected: str | None) -> Iterable[str]:
    for item in service.list_sources():
        if item.mode != "opendatasus api":
            continue
        if selected and item.source != selected:
            continue
        yield item.source


def _build_params(
    *,
    source: str,
    schema: Mapping[str, object],
    output_root: Path,
    samples: Mapping[str, Mapping[str, object]],
) -> tuple[Dict[str, object], list[str]]:
    params: Dict[str, object] = {
        "output_dir": str(output_root / source),
        "keep_raw": False,
        "batch_size": 1,
        "max_pages": 1,
    }
    missing: list[str] = []
    sample_values = samples.get(source, {})

    for spec in schema.get("params", []):
        if not isinstance(spec, Mapping):
            continue
        name = str(spec.get("name") or "")
        if not name or name in STANDARD_FIELDS or name == "api_base_url":
            continue
        if name == "output_format":
            continue
        required = bool(spec.get("required"))
        default = spec.get("default")
        if name in sample_values:
            params[name] = sample_values[name]
        elif required and default is not None:
            params[name] = default
        elif required:
            missing.append(name)

    return params, missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Run one canonical source only.")
    parser.add_argument(
        "--samples",
        help=(
            "JSON file with sample values for required path params, for example "
            "{\"cnes_estabelecimentos_{codigo_cnes}\": {\"codigo_cnes\": \"123\"}}"
        ),
    )
    parser.add_argument(
        "--output-root",
        default="data/smoke/opendatasus",
        help="Output root for smoke manifests.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Return zero even if upstream calls fail.",
    )
    args = parser.parse_args()

    service = DownloadService()
    samples = _load_samples(args.samples)
    output_root = Path(args.output_root)
    results = []

    for source in _selected_sources(service, args.source):
        schema = service.get_source_schema(source)
        params, missing = _build_params(
            source=source,
            schema=schema,
            output_root=output_root,
            samples=samples,
        )
        if missing:
            results.append(
                {
                    "source": source,
                    "status": "skipped",
                    "reason": f"missing required sample values: {', '.join(missing)}",
                }
            )
            continue
        try:
            result = service.run(source, **params)
        except Exception as exc:  # noqa: BLE001
            results.append({"source": source, "status": "failed", "error": str(exc)})
            continue
        results.append(
            {
                "source": source,
                "status": "ok",
                "downloaded_count": result.downloaded_count,
                "documents_found": result.documents_found,
                "export_warning": result.metadata.get("export_warning"),
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = any(item["status"] == "failed" for item in results)
    return 0 if args.allow_failures or not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
