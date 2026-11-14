"""Base comum das fontes de tabelas de códigos."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

import polars as pl

from guaraci.core.datasource import DataSource

ProgressCallback = Callable[[Dict[str, object]], None]


class ReferenciaDataSource(DataSource):
    """Subclasses fixam ``DATASET`` e implementam ``download``."""

    DATASET = ""
    DEFAULT_TIMEOUT = 120

    def __init__(self, output_path: Optional[str] = None) -> None:
        super().__init__(name=self.DATASET, output_path=output_path)

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); o export é lido com polars.scan_*.")

    def base_dir(self, output_dir: Optional[str]) -> Path:
        base = Path(output_dir) if output_dir else self.output_path
        base.mkdir(parents=True, exist_ok=True)
        return base

    @staticmethod
    def result(
        *,
        base_dir: Path,
        source_url: str,
        fmt: str,
        exported: List[str],
        rows: int,
        files: int,
        warnings: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        avisos = list(warnings or [])
        if rows == 0:
            avisos.append("Nenhuma linha retornada.")
        return {
            "documents_found": rows,
            "downloaded_count": files,
            "skipped_count": 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": source_url,
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows,
            "export_warning": " ".join(avisos) or None,
        }
