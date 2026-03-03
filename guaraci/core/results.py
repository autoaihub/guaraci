"""
Guaraci Download Results
========================

Shared result objects returned by datasource download jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional


@dataclass(frozen=True)
class JobResult(Mapping[str, object]):
    """Standard outcome for download jobs."""

    source: str
    documents_found: int = 0
    downloaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    manifest_path: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.failed_count > 0 and self.downloaded_count == 0:
            return "failed"
        if self.failed_count > 0:
            return "partial_success"
        return "success"

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "source": self.source,
            "status": self.status,
            "documents_found": self.documents_found,
            "downloaded_count": self.downloaded_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "manifest_path": self.manifest_path,
        }
        payload.update(self.metadata)
        return payload

    def __getitem__(self, key: str) -> object:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    @classmethod
    def from_payload(cls, source: str, payload: Any) -> "JobResult":
        """Build a JobResult from datasource-specific payloads."""
        if isinstance(payload, cls):
            return payload

        if isinstance(payload, Mapping):
            known_keys = {
                "documents_found",
                "total_files",
                "downloaded_count",
                "successful_downloads",
                "skipped_count",
                "failed_count",
                "failed_downloads",
                "manifest_path",
            }
            metadata = {
                str(key): value
                for key, value in payload.items()
                if str(key) not in known_keys
            }
            return cls(
                source=source,
                documents_found=int(payload.get("documents_found", payload.get("total_files", 0))),
                downloaded_count=int(
                    payload.get("downloaded_count", payload.get("successful_downloads", 0))
                ),
                skipped_count=int(payload.get("skipped_count", 0)),
                failed_count=int(
                    payload.get("failed_count", len(payload.get("failed_downloads", [])))
                ),
                manifest_path=(
                    str(payload["manifest_path"])
                    if payload.get("manifest_path") is not None
                    else None
                ),
                metadata=metadata,
            )

        if isinstance(payload, Path):
            return cls(
                source=source,
                documents_found=1,
                downloaded_count=1,
                manifest_path=str(payload),
                metadata={"output_path": str(payload)},
            )

        raise TypeError(f"Unsupported payload type for JobResult conversion: {type(payload)!r}")
