"""
Shared contracts for download sources and manifest serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Literal, Mapping, Optional, Sequence

ParameterType = Literal["string", "integer", "boolean", "string_list"]


@dataclass(frozen=True)
class SourceParameterSpec:
    """Declarative parameter schema for a download source."""

    name: str
    param_type: ParameterType
    description: str
    phase: str = "coleta"
    required: bool = False
    default: Optional[object] = None
    allowed_values: Optional[Sequence[str]] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "type": self.param_type,
            "description": self.description,
            "phase": self.phase,
            "required": self.required,
            "default": self.default,
            "allowed_values": list(self.allowed_values) if self.allowed_values else None,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


def validate_source_params(
    params: Mapping[str, object],
    specs: Sequence[SourceParameterSpec],
    *,
    reject_unknown: bool = True,
) -> None:
    """Validate source input params against a declarative schema."""

    by_name = {item.name: item for item in specs}
    if reject_unknown:
        unknown = sorted(key for key in params if key not in by_name)
        if unknown:
            raise ValueError(
                f"Unsupported parameter(s): {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(by_name))}"
            )

    for spec in specs:
        value = params.get(spec.name)
        if value is None:
            if spec.required and spec.default is None:
                raise ValueError(f"Parameter '{spec.name}' is required.")
            continue
        _validate_param_value(spec, value)


def _validate_param_value(spec: SourceParameterSpec, value: object) -> None:
    name = spec.name
    if spec.param_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"Parameter '{name}' must be a string.")
        _validate_allowed(spec, [value])
        return

    if spec.param_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Parameter '{name}' must be an integer.")
        if spec.minimum is not None and value < spec.minimum:
            raise ValueError(f"Parameter '{name}' must be >= {spec.minimum}.")
        if spec.maximum is not None and value > spec.maximum:
            raise ValueError(f"Parameter '{name}' must be <= {spec.maximum}.")
        return

    if spec.param_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Parameter '{name}' must be a boolean.")
        return

    if spec.param_type == "string_list":
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise ValueError(f"Parameter '{name}' must be a list of strings.")
        # Inteiros são aceitos e coagidos para string na checagem de
        # allowed_values: a validação roda sobre params já normalizados e
        # normalizadores convertem itens numéricos (ex.: months) para int.
        if any(
            isinstance(item, bool) or not isinstance(item, (str, int))
            for item in value
        ):
            raise ValueError(f"Parameter '{name}' must contain only strings.")
        _validate_allowed(spec, [str(item) for item in value])
        return

    raise ValueError(f"Unsupported parameter type '{spec.param_type}' for '{name}'.")


def _validate_allowed(spec: SourceParameterSpec, values: Sequence[str]) -> None:
    if not spec.allowed_values:
        return
    allowed = set(spec.allowed_values)
    invalid = sorted(item for item in values if item not in allowed)
    if invalid:
        raise ValueError(
            f"Invalid value(s) for '{spec.name}': {', '.join(invalid)}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )


@dataclass(frozen=True)
class DownloadManifest:
    """Standardized manifest persisted by download-based sources."""

    source: str
    results_url: Optional[str] = None
    filters: Dict[str, object] = field(default_factory=dict)
    documents_found: int = 0
    downloaded_files: List[str] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    extracted_dirs: List[str] = field(default_factory=list)
    failed_urls: List[str] = field(default_factory=list)
    materialized_paths: List[str] = field(default_factory=list)
    exported_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "1.1"

    def to_dict(self, include_legacy_fields: bool = True) -> Dict[str, object]:
        stats = {
            "documents_found": self.documents_found,
            "downloaded_count": len(self.downloaded_files) or len(self.materialized_paths),
            "skipped_count": len(self.skipped_files),
            "failed_count": len(self.failed_urls),
        }
        artifacts = {
            "downloaded_files": list(self.downloaded_files),
            "skipped_files": list(self.skipped_files),
            "extracted_dirs": list(self.extracted_dirs),
            "failed_urls": list(self.failed_urls),
            "materialized_paths": list(self.materialized_paths),
            "exported_files": list(self.exported_files),
        }
        payload: Dict[str, object] = {
            "manifest_schema_version": self.schema_version,
            "source": self.source,
            "generated_at_utc": self.generated_at_utc,
            "results_url": self.results_url,
            "request": {"filters": dict(self.filters)},
            "stats": stats,
            "artifacts": artifacts,
            "warnings": list(self.warnings),
        }
        if include_legacy_fields:
            payload.update(
                {
                    "timestamp_utc": self.generated_at_utc,
                    "filters": dict(self.filters),
                    "documents_found": self.documents_found,
                    "downloaded_files": list(self.downloaded_files),
                    "skipped_files": list(self.skipped_files),
                    "extracted_dirs": list(self.extracted_dirs),
                    "failed_urls": list(self.failed_urls),
                    "materialized_paths": list(self.materialized_paths),
                    "exported_files": list(self.exported_files),
                    "warnings": list(self.warnings),
                }
            )
        return payload
