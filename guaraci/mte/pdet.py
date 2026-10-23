"""Transporte e exportação comuns aos microdados do PDET/MTE (FTP + 7z).

Só o FTP ``ftp.mtps.gov.br`` responde (pelo HTTPS a conexão cai). A listagem usa
``ftplib`` (NLST, nomes em latin-1: há pastas como ``2024 Parcial`` e arquivos
com acento); o download usa o ``HttpFileClient`` de ``arquivos/http_files.py``,
que já trata ``ftp://`` com ``.part`` e conferência de tamanho. O conteúdo do 7z
é decodificado linha a linha (``transcode_lines``) e exportado como texto, sem
interpretar nenhum campo.
"""

from __future__ import annotations

import ftplib
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

import polars as pl

from guaraci.arquivos.http_files import (
    HttpFileClient,
    _normalize_format,
    _sink_atomic,
    encoding_warnings,
    transcode_lines,
)
from guaraci.core.datasource import DataSource
from guaraci.core.http import ApiClientError
from guaraci.mte.sevenzip import SevenZipError, SevenZipExtractor, default_extractor

__all__ = [
    "FTP_HOST",
    "FTP_ROOT",
    "FtpLister",
    "PdetDataSource",
    "PdetItem",
    "ftp_url",
]

FTP_HOST = "ftp.mtps.gov.br"
FTP_ROOT = "/pdet/microdados"
ProgressCallback = Callable[[Dict[str, object]], None]


def ftp_url(path: str, host: str = FTP_HOST) -> str:
    """URL ``ftp://`` com o caminho codificado (``NOVO CAGED`` vira ``NOVO%20CAGED``)."""
    return f"ftp://{host}{quote(path)}"


class FtpLister:
    """Listagem e metadados no FTP do MTE, uma conexão curta por consulta."""

    def __init__(self, host: str = FTP_HOST, *, timeout_seconds: int = 60) -> None:
        self.host = host
        self.timeout_seconds = timeout_seconds

    def _connect(self) -> ftplib.FTP:
        ftp = ftplib.FTP(self.host, timeout=self.timeout_seconds, encoding="latin-1")
        ftp.login()
        ftp.voidcmd("TYPE I")
        return ftp

    def names(self, path: str) -> List[str]:
        """Nomes (sem o caminho) dentro de ``path``; pasta inexistente devolve ``[]``."""
        ftp = self._connect()
        try:
            try:
                found = ftp.nlst(path)
            except ftplib.error_perm as exc:
                if str(exc).startswith("550"):
                    return []
                raise
            return [item.rstrip("/").rsplit("/", 1)[-1] for item in found]
        finally:
            _quit(ftp)

    def stat(self, path: str) -> Tuple[Optional[int], Optional[str]]:
        """``(tamanho em bytes, data de modificação ISO)``; ``None`` onde o servidor não informa."""
        ftp = self._connect()
        try:
            try:
                size: Optional[int] = ftp.size(path)
            except ftplib.error_perm:
                size = None
            modified: Optional[str] = None
            try:
                stamp = ftp.sendcmd(f"MDTM {path}").split()[-1]
                modified = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").isoformat()
            except (ftplib.error_perm, ValueError):
                modified = None
            return size, modified
        finally:
            _quit(ftp)


def _quit(ftp: ftplib.FTP) -> None:
    try:
        ftp.quit()
    except (ftplib.all_errors, EOFError):
        ftp.close()


@dataclass(frozen=True)
class PdetItem:
    """Um 7z a baixar e exportar."""

    code: str  # ex. "202608" ou "2024_SP"; entra no nome do CSV
    path: str  # caminho absoluto no FTP
    label: str


class PdetDataSource(DataSource):
    """Base dos datasources do MTE: baixa os 7z por FTP e exporta cada um em CSV UTF-8."""

    DEFAULT_TIMEOUT = HttpFileClient.DEFAULT_TIMEOUT
    # Separador do texto e nº de colunas conferido ao vivo; divergência vira aviso.
    SEPARATOR = ";"
    EXPECTED_COLUMNS: Optional[int] = None

    def __init__(
        self,
        name: str,
        output_path: Optional[str] = None,
        *,
        client: Optional[HttpFileClient] = None,
        lister: Optional[FtpLister] = None,
        extractor: Optional[SevenZipExtractor] = None,
    ) -> None:
        super().__init__(name=name, output_path=output_path)
        self._client = client
        self._lister = lister
        self._extractor = extractor

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported file with polars.scan_*.")

    def lister(self) -> FtpLister:
        if self._lister is None:
            self._lister = FtpLister()
        return self._lister

    def extractor(self) -> SevenZipExtractor:
        if self._extractor is None:
            self._extractor = default_extractor()
        return self._extractor

    def _run(
        self,
        items: Sequence[PdetItem],
        *,
        output_format: Optional[str],
        keep_raw: bool,
        output_dir: Optional[str],
        timeout: int,
        progress_callback: Optional[ProgressCallback],
        warnings: List[str],
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        if requested:
            # Antes de baixar centenas de MB: sem extrator o erro tem de aparecer já.
            self.extractor().backend()
        client = self._client or HttpFileClient(timeout_seconds=timeout)
        total = len(items)
        isolate = total > 1

        def emit(event: Dict[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({"source": self.name, "documents_total": total, **event})

        emit({"event": "download_start"})
        exported: List[str] = []
        downloaded = skipped_count = failed = 0
        first: Optional[Tuple[str, Optional[int], Optional[str]]] = None

        for index, item in enumerate(items, start=1):
            raw_path = base_dir / f"{self.name}_{item.code}.7z"
            try:
                size, modified = self.lister().stat(item.path)
                if first is None:
                    first = (ftp_url(item.path), size, modified)
                skipped = (
                    raw_path.exists() and size is not None and raw_path.stat().st_size == size
                )
                if not skipped:

                    def on_bytes(written: int, _p=raw_path, _i=index, _s=size) -> None:
                        emit({
                            "event": "file_progress", "document_index": _i,
                            "file_path": str(_p), "file_bytes_downloaded": written,
                            "file_total_bytes": _s or 0,
                        })

                    client.download(ftp_url(item.path), raw_path, progress_callback=on_bytes)
                emit({
                    "event": "file_skipped" if skipped else "file_completed",
                    "document_index": index, "file_path": str(raw_path),
                })
                skipped_count += 1 if skipped else 0
                downloaded += 0 if skipped else 1
                if requested:
                    dest = self._export(raw_path, base_dir, requested, item, warnings)
                    exported.append(str(dest))
                    if not keep_raw:
                        raw_path.unlink(missing_ok=True)
            except (ApiClientError, ValueError, SevenZipError, zipfile.BadZipFile, OSError) as exc:
                if not isolate:
                    raise
                failed += 1
                warnings.append(f"{item.label}: {exc}")

        if not requested and not keep_raw:
            warnings.append(
                "7z mantido como o MTE publica; informe output_format para exportar em "
                "csv, parquet ou sqlite (exige o 7-Zip ou o pacote py7zr)."
            )
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped_count,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": first[0] if first else None,
            "source_size": first[1] if first else None,
            "source_last_modified": first[2] if first else None,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(
        self,
        raw_path: Path,
        base_dir: Path,
        fmt: str,
        item: PdetItem,
        warnings: List[str],
    ) -> Path:
        name = f"{self.name}_{item.code}"
        utf8 = base_dir / f"{name}.utf8.tmp.csv"
        try:
            stats: Dict[str, int] = {}
            with self.extractor().open(raw_path) as source, open(
                utf8, "w", encoding="utf-8", newline=""
            ) as sink:
                encoding = transcode_lines(source, sink, stats)
            warnings.extend(encoding_warnings(raw_path.name, stats, encoding))
            frame = pl.scan_csv(
                utf8, separator=self.SEPARATOR, infer_schema=False, quote_char='"'
            )
            names = frame.collect_schema().names()
            stripped = {n: n.strip() for n in names if n != n.strip()}
            if stripped:
                frame = frame.rename(stripped)
            if self.EXPECTED_COLUMNS is not None and len(names) != self.EXPECTED_COLUMNS:
                warnings.append(
                    f"{item.label}: {len(names)} colunas, esperadas {self.EXPECTED_COLUMNS} "
                    "(o MTE pode ter mudado o leiaute; confira a nota técnica)."
                )
            suffix = {"csv": ".csv", "parquet": ".parquet"}.get(fmt, ".sqlite")
            return _sink_atomic(frame, base_dir / f"{name}{suffix}", fmt, name, raw_path.name)
        finally:
            utf8.unlink(missing_ok=True)


def match_name(names: Sequence[str], pattern: str) -> Optional[str]:
    """Primeiro nome que casa com ``pattern`` (sem caixa), ou ``None``."""
    regex = re.compile(pattern, re.IGNORECASE)
    for name in names:
        if regex.fullmatch(name):
            return name
    return None
