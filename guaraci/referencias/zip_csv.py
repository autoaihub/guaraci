"""Zip de CSVs de códigos (CID-10 do DATASUS e municípios do TSE), um CSV por membro."""

from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from guaraci.arquivos.http_files import HttpFileClient
from guaraci.gestao_publica.rest import RowSpool, finalize_export, normalize_format
from guaraci.referencias.base import ProgressCallback, ReferenciaDataSource


class ZipCsvDataSource(ReferenciaDataSource):
    """Baixa um zip e grava cada CSV interno em UTF-8, tudo como texto."""

    URL = ""
    SUFFIX = ".csv"
    ENCODING = "cp1252"
    DELIMITER = ";"

    def stem_for(self, member: str) -> str:
        stem = Path(member).stem.lower().replace("-", "_")
        return f"{self.name}_{stem}"

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = ReferenciaDataSource.DEFAULT_TIMEOUT,
        url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = self.base_dir(output_dir)
        source_url = url or self.URL
        client = HttpFileClient(timeout_seconds=timeout)
        exported: List[str] = []
        warnings: List[str] = []
        rows_total = 0
        files = 0
        with tempfile.TemporaryDirectory(prefix=f"{self.name}.", dir=str(base_dir)) as tmp:
            raw = Path(tmp) / "origem.zip"
            client.download(source_url, raw)
            with zipfile.ZipFile(raw) as archive:
                members = sorted(
                    n for n in archive.namelist() if n.lower().endswith(self.SUFFIX)
                )
                if progress_callback is not None:
                    progress_callback({
                        "event": "download_start", "source": self.name,
                        "documents_total": len(members),
                    })
                for index, member in enumerate(members, start=1):
                    rows = self._member(archive, member, base_dir, fmt, exported, warnings)
                    rows_total += rows
                    files += 1 if rows else 0
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name,
                            "documents_total": len(members), "files_completed": index,
                            "file_path": member,
                        })
        return self.result(
            base_dir=base_dir, source_url=source_url, fmt=fmt, exported=exported,
            rows=rows_total, files=files, warnings=warnings,
        )

    def _member(
        self, archive: zipfile.ZipFile, member: str, base_dir: Path, fmt: str,
        exported: List[str], warnings: List[str],
    ) -> int:
        text = io.TextIOWrapper(
            archive.open(member), encoding=self.ENCODING, errors="replace", newline=""
        )
        reader = csv.reader(text, delimiter=self.DELIMITER)
        header = next(reader, None)
        if header is None:
            return 0
        header = [h.strip() for h in header]
        # o separador final de cada linha cria uma coluna sem nome; não é dado
        keep = [i for i, name in enumerate(header) if name]
        stem = self.stem_for(member)
        spool = RowSpool(base_dir, stem)
        try:
            for record in reader:
                if not any(cell.strip() for cell in record):
                    continue
                spool.add({header[i]: (record[i] if i < len(record) else "") for i in keep})
        except BaseException:
            spool.discard()
            raise
        rows = spool.rows
        path = spool.write_csv(base_dir / f"{stem}.csv", columns=[header[i] for i in keep])
        if path is None:
            warnings.append(f"{member}: sem linhas.")
            return 0
        exported.extend(finalize_export(path, fmt, stem))
        return rows
