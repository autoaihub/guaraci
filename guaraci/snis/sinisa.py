"""
Guaraci SINISA Integration
==========================

Extractor for raw SINISA files published on gov.br pages.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from time import monotonic
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd
import polars as pl
from loguru import logger

from guaraci.core.config import config
from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource


@dataclass(frozen=True)
class SinisaDocumentLink:
    """Represents a downloadable SINISA document link."""

    url: str
    text: str
    kind: str
    module: Optional[str]


@dataclass
class _SinisaDownloadState:
    """Mutable state for a SINISA download run."""

    downloaded: List[str]
    skipped: List[str]
    extracted: List[str]
    failed: List[str]


ProgressCallback = Callable[[Dict[str, object]], None]


class _AnchorParser(HTMLParser):
    """Minimal HTML anchor parser for extracting href + text pairs."""

    def __init__(self) -> None:
        super().__init__()
        self._href: Optional[str] = None
        self._text_parts: List[str] = []
        self.links: List[Tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        href = None
        for key, value in attrs:
            if key.lower() == "href":
                href = value
                break
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join(part.strip() for part in self._text_parts if part.strip()).strip()
        self.links.append((self._href, text))
        self._href = None
        self._text_parts = []


class SinisaDataSource(DataSource):
    """SINISA raw-data source via scraping/download from gov.br pages."""

    SINISA_HOME_URL = (
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/"
        "acoes-e-programas/saneamento/sinisa"
    )
    DEFAULT_RESULTS_URL = (
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/"
        "acoes-e-programas/saneamento/sinisa/resultados-sinisa"
    )
    DOWNLOADABLE_EXTENSIONS = (".zip", ".xlsx", ".xls", ".csv", ".ods", ".pdf")
    PLANILHA_SOURCE_EXTENSIONS = (".zip", ".csv", ".xlsx")
    PLANILHA_FINAL_EXTENSIONS = (".csv", ".xlsx")
    VALID_FILE_KINDS = ("planilhas", "relatorios", "glossarios", "atestados", "all")
    VALID_MODULES = ("gestao_municipal", "agua", "esgoto", "residuos", "aguas_pluviais")

    KIND_PATTERNS: Dict[str, Tuple[str, ...]] = {
        "planilhas": ("planilha", "informacoes e indicadores", "indicadores"),
        "relatorios": ("relatorio",),
        "glossarios": ("glossario",),
        "atestados": ("atestado", "adimplencia", "regularidade"),
    }
    MODULE_PATTERNS: Dict[str, Tuple[str, ...]] = {
        "gestao_municipal": ("gestao municipal", "gestao_municipal"),
        "agua": ("agua", "abastecimento"),
        "esgoto": ("esgoto", "esgotamento"),
        "residuos": ("residuo", "residuos"),
        "aguas_pluviais": ("pluvial", "aguas pluviais", "aguaspluviais"),
    }
    USER_AGENT = "guaraci-sinisa-extractor/1.0"

    def __init__(self, output_path: Optional[str] = None):
        base_output = output_path or str(config.data_root / "sinisa")
        super().__init__(name="sinisa", output_path=base_output)

    def download(
        self,
        output_dir: Optional[str] = None,
        results_url: Optional[str] = None,
        file_kinds: Optional[Sequence[str]] = None,
        modules: Optional[Sequence[str]] = None,
        extract_archives: bool = True,
        overwrite: bool = False,
        timeout: int = 120,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        """
        Download raw SINISA files from the results page.

        Parameters
        ----------
        output_dir : str, optional
            Output directory for downloaded files.
        results_url : str, optional
            URL with SINISA result links.
        file_kinds : sequence of str, optional
            Any of: planilhas, relatorios, glossarios, atestados, all.
            Default: planilhas.
        modules : sequence of str, optional
            Any of: gestao_municipal, agua, esgoto, residuos, aguas_pluviais.
        extract_archives : bool
            If True, extracts downloaded .zip files.
        overwrite : bool
            If True, overwrites existing files.
        timeout : int
            HTTP timeout in seconds.
        """
        file_kinds = self._normalize_file_kinds(file_kinds or ["planilhas"])
        normalized_modules = self._normalize_modules(modules)

        source_url = results_url or self.DEFAULT_RESULTS_URL
        documents = self.list_documents(
            results_url=source_url,
            file_kinds=file_kinds,
            modules=normalized_modules,
            timeout=timeout,
        )
        if not documents:
            raise RuntimeError("No SINISA files matched the requested filters.")

        self._emit_progress(
            progress_callback,
            {
                "event": "download_start",
                "source": self.name,
                "results_url": source_url,
                "documents_total": len(documents),
            },
        )

        base_dir, raw_dir, extracted_dir = self._prepare_output_dirs(
            output_dir=output_dir,
            extract_archives=extract_archives,
        )
        state = self._download_documents(
            documents=documents,
            raw_dir=raw_dir,
            extracted_dir=extracted_dir,
            extract_archives=extract_archives,
            overwrite=overwrite,
            timeout=timeout,
            progress_callback=progress_callback,
        )
        manifest = self._build_manifest(
            source_url=source_url,
            file_kinds=file_kinds,
            modules=normalized_modules,
            extract_archives=extract_archives,
            overwrite=overwrite,
            documents_found=len(documents),
            state=state,
        )
        manifest_path = self._write_manifest(base_dir=base_dir, manifest=manifest)

        self._emit_progress(
            progress_callback,
            {
                "event": "download_complete",
                "source": self.name,
                "documents_total": len(documents),
                "downloaded_count": len(state.downloaded),
                "skipped_count": len(state.skipped),
                "failed_count": len(state.failed),
                "output_dir": str(base_dir),
            },
        )

        return {
            "documents_found": len(documents),
            "downloaded_count": len(state.downloaded),
            "skipped_count": len(state.skipped),
            "failed_count": len(state.failed),
            "manifest_path": str(manifest_path),
            "output_dir": str(base_dir),
        }

    def list_documents(
        self,
        results_url: Optional[str] = None,
        file_kinds: Optional[Sequence[str]] = None,
        modules: Optional[Sequence[str]] = None,
        timeout: int = 120,
    ) -> List[SinisaDocumentLink]:
        """List SINISA documents from a results page using local HTML parsing."""
        page_urls = self._resolve_results_urls(results_url=results_url, timeout=timeout)
        selected_kinds = self._normalize_file_kinds(file_kinds or ["all"])
        normalized_modules = self._normalize_modules(modules)
        links = self._collect_documents(page_urls=page_urls, timeout=timeout)
        return self._filter_documents(
            links=links,
            selected_kinds=selected_kinds,
            normalized_modules=normalized_modules,
        )

    def _prepare_output_dirs(
        self,
        output_dir: Optional[str],
        extract_archives: bool,
    ) -> tuple[Path, Path, Optional[Path]]:
        base_dir = Path(output_dir) if output_dir else self.output_path
        raw_dir = base_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        extracted_dir: Optional[Path] = None
        if extract_archives:
            extracted_dir = base_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
        return base_dir, raw_dir, extracted_dir

    def _download_documents(
        self,
        documents: Sequence[SinisaDocumentLink],
        raw_dir: Path,
        extracted_dir: Optional[Path],
        extract_archives: bool,
        overwrite: bool,
        timeout: int,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> _SinisaDownloadState:
        state = _SinisaDownloadState(downloaded=[], skipped=[], extracted=[], failed=[])
        documents_total = len(documents)
        for index, document in enumerate(documents, start=1):
            self._process_document(
                document=document,
                document_index=index,
                documents_total=documents_total,
                raw_dir=raw_dir,
                extracted_dir=extracted_dir,
                extract_archives=extract_archives,
                overwrite=overwrite,
                timeout=timeout,
                state=state,
                progress_callback=progress_callback,
            )
        return state

    def _process_document(
        self,
        document: SinisaDocumentLink,
        document_index: int,
        documents_total: int,
        raw_dir: Path,
        extracted_dir: Optional[Path],
        extract_archives: bool,
        overwrite: bool,
        timeout: int,
        state: _SinisaDownloadState,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        file_path = raw_dir / self._build_filename(document)
        if document.kind == "planilhas" and not self._is_planilha_source(document.url):
            logger.info("Skipping non-spreadsheet planilha link: {}", document.url)
            state.skipped.append(document.url)
            self._emit_progress(
                progress_callback,
                {
                    "event": "file_skipped",
                    "source": self.name,
                    "document_index": document_index,
                    "documents_total": documents_total,
                    "url": document.url,
                    "file_path": str(file_path),
                    "reason": "non_spreadsheet_planilha",
                },
            )
            return

        if file_path.exists() and not overwrite:
            logger.info("Skipping existing file: {}", file_path)
            state.skipped.append(str(file_path))
            self._emit_progress(
                progress_callback,
                {
                    "event": "file_skipped",
                    "source": self.name,
                    "document_index": document_index,
                    "documents_total": documents_total,
                    "url": document.url,
                    "file_path": str(file_path),
                    "reason": "already_exists",
                },
            )
            self._extract_document_archive(
                document=document,
                file_path=file_path,
                document_index=document_index,
                documents_total=documents_total,
                extracted_dir=extracted_dir,
                extract_archives=extract_archives,
                overwrite=False,
                extracted_accumulator=state.extracted,
                progress_callback=progress_callback,
            )
            return

        try:
            self._emit_progress(
                progress_callback,
                {
                    "event": "file_start",
                    "source": self.name,
                    "document_index": document_index,
                    "documents_total": documents_total,
                    "url": document.url,
                    "file_path": str(file_path),
                },
            )
            self._download_file(
                document.url,
                file_path,
                timeout=timeout,
                progress_callback=progress_callback,
                document_index=document_index,
                documents_total=documents_total,
            )
            state.downloaded.append(str(file_path))
            file_size = file_path.stat().st_size if file_path.exists() else None
            self._emit_progress(
                progress_callback,
                {
                    "event": "file_completed",
                    "source": self.name,
                    "document_index": document_index,
                    "documents_total": documents_total,
                    "url": document.url,
                    "file_path": str(file_path),
                    "file_bytes_downloaded": file_size,
                    "file_total_bytes": file_size,
                },
            )
            self._extract_document_archive(
                document=document,
                file_path=file_path,
                document_index=document_index,
                documents_total=documents_total,
                extracted_dir=extracted_dir,
                extract_archives=extract_archives,
                overwrite=overwrite,
                extracted_accumulator=state.extracted,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.error("Failed to download {}: {}", document.url, exc)
            state.failed.append(document.url)
            self._emit_progress(
                progress_callback,
                {
                    "event": "file_failed",
                    "source": self.name,
                    "document_index": document_index,
                    "documents_total": documents_total,
                    "url": document.url,
                    "file_path": str(file_path),
                    "error": str(exc),
                },
            )

    def _extract_document_archive(
        self,
        document: SinisaDocumentLink,
        file_path: Path,
        document_index: int,
        documents_total: int,
        extracted_dir: Optional[Path],
        extract_archives: bool,
        overwrite: bool,
        extracted_accumulator: List[str],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        if not extract_archives or extracted_dir is None:
            return
        if file_path.suffix.lower() != ".zip":
            return

        maybe_extracted = self._extract_zip(
            zip_path=file_path,
            extracted_dir=extracted_dir,
            overwrite=overwrite,
            allowed_extensions=self._allowed_archive_extensions(document),
        )
        if maybe_extracted:
            extracted_accumulator.append(str(maybe_extracted))
            self._emit_progress(
                progress_callback,
                {
                    "event": "file_extracted",
                    "source": self.name,
                    "document_index": document_index,
                    "documents_total": documents_total,
                    "file_path": str(file_path),
                    "extracted_dir": str(maybe_extracted),
                },
            )

    def _allowed_archive_extensions(self, document: SinisaDocumentLink) -> Optional[Set[str]]:
        if document.kind != "planilhas":
            return None
        return set(self.PLANILHA_FINAL_EXTENSIONS)

    def _build_manifest(
        self,
        source_url: str,
        file_kinds: Sequence[str],
        modules: Optional[Sequence[str]],
        extract_archives: bool,
        overwrite: bool,
        documents_found: int,
        state: _SinisaDownloadState,
    ) -> Dict[str, object]:
        manifest = DownloadManifest(
            source=self.name,
            results_url=source_url,
            filters={
                "file_kinds": list(file_kinds),
                "modules": list(modules) if modules else None,
                "extract_archives": extract_archives,
                "overwrite": overwrite,
            },
            documents_found=documents_found,
            downloaded_files=list(state.downloaded),
            skipped_files=list(state.skipped),
            extracted_dirs=list(state.extracted),
            failed_urls=list(state.failed),
        )
        return manifest.to_dict(include_legacy_fields=True)

    def _write_manifest(self, base_dir: Path, manifest: Dict[str, object]) -> Path:
        manifest_path = base_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        logger.info("{} manifest saved to {}", self.name.upper(), manifest_path)
        return manifest_path

    def _resolve_results_urls(self, results_url: Optional[str], timeout: int) -> List[str]:
        if results_url:
            return [results_url]
        return self._discover_results_pages(timeout=timeout)

    def _collect_documents(
        self,
        page_urls: Sequence[str],
        timeout: int,
    ) -> List[SinisaDocumentLink]:
        links: List[SinisaDocumentLink] = []
        seen_doc_urls: Set[str] = set()
        for page_url in page_urls:
            try:
                html = self._fetch_text(page_url, timeout=timeout)
            except Exception as exc:
                logger.warning("Could not read SINISA page {}: {}", page_url, exc)
                continue

            for document in self._extract_links(html, page_url):
                if document.url in seen_doc_urls:
                    continue
                seen_doc_urls.add(document.url)
                links.append(document)
        return links

    @staticmethod
    def _filter_documents(
        links: Sequence[SinisaDocumentLink],
        selected_kinds: Sequence[str],
        normalized_modules: Optional[Sequence[str]],
    ) -> List[SinisaDocumentLink]:
        filtered: List[SinisaDocumentLink] = []
        for link in links:
            if "all" not in selected_kinds and link.kind not in selected_kinds:
                continue
            if normalized_modules and link.module not in normalized_modules:
                continue
            if link.kind == "planilhas" and not SinisaDataSource._is_planilha_source(link.url):
                continue
            filtered.append(link)
        return filtered

    def load_dataframe(self, file_path: str, sheet_name: Optional[str] = None) -> pl.DataFrame:
        """Load a downloaded raw SINISA file into Polars."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pl.read_csv(path)
        if suffix in {".xlsx", ".xls", ".ods"}:
            pandas_df = pd.read_excel(path, sheet_name=sheet_name or 0)
            return pl.from_pandas(pandas_df)
        raise ValueError(f"Unsupported file extension for DataFrame loading: {suffix}")

    @classmethod
    def _normalize_file_kinds(cls, file_kinds: Sequence[str]) -> List[str]:
        normalized = [kind.strip().lower() for kind in file_kinds]
        cls._validate_file_kinds(normalized)

        seen: Set[str] = set()
        deduplicated: List[str] = []
        for kind in normalized:
            if kind not in seen:
                seen.add(kind)
                deduplicated.append(kind)
        return deduplicated

    @classmethod
    def _validate_file_kinds(cls, file_kinds: Sequence[str]) -> None:
        normalized = {kind.strip().lower() for kind in file_kinds}
        invalid = sorted(normalized - set(cls.VALID_FILE_KINDS))
        if invalid:
            valid = ", ".join(cls.VALID_FILE_KINDS)
            raise ValueError(f"Invalid file_kinds: {', '.join(invalid)}. Valid values: {valid}")

    @classmethod
    def _normalize_modules(cls, modules: Optional[Sequence[str]]) -> Optional[List[str]]:
        if not modules:
            return None
        normalized = [module.strip().lower() for module in modules]
        invalid = sorted(set(normalized) - set(cls.VALID_MODULES))
        if invalid:
            valid = ", ".join(cls.VALID_MODULES)
            raise ValueError(f"Invalid modules: {', '.join(invalid)}. Valid values: {valid}")
        # Keep order while removing duplicates
        seen: Set[str] = set()
        deduplicated: List[str] = []
        for module in normalized:
            if module not in seen:
                seen.add(module)
                deduplicated.append(module)
        return deduplicated

    @classmethod
    def _extract_links(cls, html: str, base_url: str) -> List[SinisaDocumentLink]:
        anchors = cls._extract_anchors(html, base_url)
        seen_urls: Set[str] = set()
        documents: List[SinisaDocumentLink] = []
        for cleaned, text in anchors:
            if cleaned in seen_urls:
                continue
            if not cls._is_downloadable(cleaned):
                continue
            seen_urls.add(cleaned)
            kind = cls._infer_kind(text=text, url=cleaned)
            module = cls._infer_module(text=text, url=cleaned)
            documents.append(
                SinisaDocumentLink(
                    url=cleaned,
                    text=text.strip(),
                    kind=kind,
                    module=module,
                )
            )
        return documents

    @classmethod
    def _extract_anchors(cls, html: str, base_url: str) -> List[Tuple[str, str]]:
        parser = _AnchorParser()
        parser.feed(html)
        anchors: List[Tuple[str, str]] = []
        for href, text in parser.links:
            cleaned = cls._normalize_url(href, base_url)
            if cleaned:
                anchors.append((cleaned, text.strip()))
        return anchors

    def _discover_results_pages(self, timeout: int) -> List[str]:
        candidates: Set[str] = {self.DEFAULT_RESULTS_URL}
        seeds = [self.SINISA_HOME_URL, self.DEFAULT_RESULTS_URL]

        for seed_url in seeds:
            try:
                html = self._fetch_text(seed_url, timeout=timeout)
            except Exception as exc:
                logger.warning("Could not inspect SINISA seed page {}: {}", seed_url, exc)
                continue
            for href, _text in self._extract_anchors(html, seed_url):
                if self._is_downloadable(href):
                    continue
                if "/resultados-sinisa/" not in href:
                    continue
                if "/arquivos/" in href:
                    continue
                candidates.add(href.rstrip("/"))

        def sort_key(url: str) -> Tuple[int, str]:
            # Prefer URLs containing explicit year in the slug.
            match = re.search(r"resultados-sinisa-(\d{4})", url)
            year = int(match.group(1)) if match else 0
            return (year, url)

        ordered = sorted(candidates, key=sort_key, reverse=True)
        return ordered

    @classmethod
    def _normalize_url(cls, href: str, base_url: str) -> Optional[str]:
        href = href.strip()
        if not href or href.startswith("#"):
            return None
        if href.startswith(("mailto:", "javascript:")):
            return None

        absolute = urljoin(base_url, href)
        if absolute.endswith("/view"):
            absolute = absolute[:-5]
        return absolute

    @classmethod
    def _is_downloadable(cls, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith(cls.DOWNLOADABLE_EXTENSIONS)

    @classmethod
    def _is_planilha_source(cls, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith(cls.PLANILHA_SOURCE_EXTENSIONS)

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        lowered = text.lower()
        normalized = unicodedata.normalize("NFD", lowered)
        no_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        compact = re.sub(r"[^a-z0-9]+", " ", no_accents)
        return compact.strip()

    @classmethod
    def _infer_kind(cls, text: str, url: str) -> str:
        haystack = cls._normalize_text(f"{text} {Path(urlparse(url).path).name}")
        for kind, patterns in cls.KIND_PATTERNS.items():
            if any(pattern in haystack for pattern in patterns):
                return kind
        return "other"

    @classmethod
    def _infer_module(cls, text: str, url: str) -> Optional[str]:
        haystack = cls._normalize_text(f"{text} {Path(urlparse(url).path).name}")
        for module, patterns in cls.MODULE_PATTERNS.items():
            if any(pattern in haystack for pattern in patterns):
                return module
        return None

    def _build_filename(self, document: SinisaDocumentLink) -> str:
        url_path = Path(urlparse(document.url).path)
        name = url_path.name
        if name:
            return name

        normalized_text = self._normalize_text(document.text).replace(" ", "_")
        if not normalized_text:
            normalized_text = "sinisa_document"
        return f"{normalized_text}.bin"

    def _build_request(self, url: str) -> Request:
        return Request(url=url, headers={"User-Agent": self.USER_AGENT})

    def _fetch_text(self, url: str, timeout: int) -> str:
        request = self._build_request(url)
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()

        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload.decode("latin-1", errors="replace")

    def _download_file(
        self,
        url: str,
        destination: Path,
        timeout: int,
        progress_callback: Optional[ProgressCallback] = None,
        document_index: Optional[int] = None,
        documents_total: Optional[int] = None,
    ) -> None:
        last_exc: Optional[Exception] = None
        for attempt in range(1, config.retry_attempts + 1):
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                request = self._build_request(url)
                with urlopen(request, timeout=timeout) as response:
                    content_length_raw = response.headers.get("Content-Length")
                    file_total_bytes: Optional[int] = None
                    if content_length_raw and content_length_raw.isdigit():
                        file_total_bytes = int(content_length_raw)

                    bytes_downloaded = 0
                    last_emit = monotonic()
                    with destination.open("wb") as fp:
                        while True:
                            chunk = response.read(1024 * 256)
                            if not chunk:
                                break
                            fp.write(chunk)
                            bytes_downloaded += len(chunk)
                            now = monotonic()
                            should_emit = (now - last_emit) >= 0.15
                            if file_total_bytes and bytes_downloaded >= file_total_bytes:
                                should_emit = True
                            if should_emit:
                                self._emit_progress(
                                    progress_callback,
                                    {
                                        "event": "file_progress",
                                        "source": self.name,
                                        "document_index": document_index,
                                        "documents_total": documents_total,
                                        "url": url,
                                        "file_path": str(destination),
                                        "file_bytes_downloaded": bytes_downloaded,
                                        "file_total_bytes": file_total_bytes,
                                    },
                                )
                                last_emit = now

                    self._emit_progress(
                        progress_callback,
                        {
                            "event": "file_progress",
                            "source": self.name,
                            "document_index": document_index,
                            "documents_total": documents_total,
                            "url": url,
                            "file_path": str(destination),
                            "file_bytes_downloaded": bytes_downloaded,
                            "file_total_bytes": file_total_bytes or bytes_downloaded,
                        },
                    )
                logger.info("Downloaded {}", destination)
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Download failed (attempt {}/{}): {}",
                    attempt,
                    config.retry_attempts,
                    url,
                )
        if last_exc is None:
            raise RuntimeError(f"Download failed for {url}")
        raise last_exc

    @staticmethod
    def _emit_progress(
        progress_callback: Optional[ProgressCallback],
        payload: Dict[str, object],
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(payload)

    def _extract_zip(
        self,
        zip_path: Path,
        extracted_dir: Path,
        overwrite: bool,
        allowed_extensions: Optional[Set[str]] = None,
    ) -> Optional[Path]:
        destination = extracted_dir / zip_path.stem
        if destination.exists() and not overwrite:
            logger.info("Skipping extraction (exists): {}", destination)
            return destination

        if destination.exists() and overwrite:
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)

        extracted_count = 0
        destination_root = destination.resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                suffix = Path(member.filename).suffix.lower()
                if allowed_extensions and suffix not in allowed_extensions:
                    continue

                target = (destination / member.filename).resolve()
                if not self._is_within_directory(destination_root, target):
                    logger.warning("Skipping suspicious zip member path: {}", member.filename)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted_count += 1

        if extracted_count == 0:
            logger.warning("No files extracted from {} with current filters.", zip_path)
        logger.info("Extracted {} -> {}", zip_path, destination)
        return destination

    @staticmethod
    def _is_within_directory(directory: Path, target: Path) -> bool:
        try:
            target.relative_to(directory)
        except ValueError:
            return False
        return True
