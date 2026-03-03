"""
Guaraci SNIS Integration (gov.br)
=================================

Primary SNIS datasource implemented via direct downloads from gov.br
(SNIS historical pages and files).
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

from guaraci.core.config import config
from guaraci.core.datasource import DataSource
from guaraci.core.results import JobResult
from loguru import logger
from guaraci.snis.sinisa import ProgressCallback, SinisaDataSource, SinisaDocumentLink


class SnisDataSource(SinisaDataSource):
    """Primary SNIS datasource backed by direct gov.br downloads."""

    SINISA_HOME_URL = (
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/"
        "acoes-e-programas/saneamento/snis/diagnosticos-anteriores-do-snis"
    )
    DEFAULT_RESULTS_URL = SINISA_HOME_URL
    MAX_DISCOVERY_DEPTH = 3
    SNIS_PLANILHA_FINAL_EXTENSIONS = (".csv", ".xlsx", ".xls")

    def __init__(self, output_path: Optional[str] = None):
        base_output = output_path or str(config.data_root / "snis")
        DataSource.__init__(self, name="snis", output_path=base_output)

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
    ) -> JobResult:
        """Download SNIS raw files from gov.br historical pages."""
        file_kinds = self._normalize_file_kinds(file_kinds or ["planilhas"])
        normalized_modules = self._normalize_modules(modules)

        documents = self.list_documents(
            results_url=results_url,
            file_kinds=file_kinds,
            modules=normalized_modules,
            timeout=timeout,
        )
        if not documents:
            raise RuntimeError("No SNIS files matched the requested filters.")

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
            source_url=results_url or self.DEFAULT_RESULTS_URL,
            file_kinds=file_kinds,
            modules=normalized_modules,
            extract_archives=extract_archives,
            overwrite=overwrite,
            documents_found=len(documents),
            state=state,
        )
        manifest_path = self._write_manifest(base_dir=base_dir, manifest=manifest)

        return JobResult(
            source=self.name,
            documents_found=len(documents),
            downloaded_count=len(state.downloaded),
            skipped_count=len(state.skipped),
            failed_count=len(state.failed),
            manifest_path=str(manifest_path),
        )

    @classmethod
    def _infer_kind(cls, text: str, url: str) -> str:
        kind = super()._infer_kind(text=text, url=url)
        if kind == "other" and cls._is_planilha_source(url):
            return "planilhas"
        return kind

    def _discover_results_pages(self, timeout: int) -> List[str]:
        root = self.DEFAULT_RESULTS_URL.rstrip("/")
        pages: Set[str] = {root}
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(root, 0)]

        while queue:
            page_url, depth = queue.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)

            try:
                html = self._fetch_text(page_url, timeout=timeout)
            except Exception as exc:
                logger.warning("Could not inspect SNIS page {}: {}", page_url, exc)
                continue

            if depth >= self.MAX_DISCOVERY_DEPTH:
                continue

            for href, _text in self._extract_anchors(html, page_url):
                cleaned = href.rstrip("/")
                if self._is_downloadable(cleaned):
                    continue
                if "/arquivos/" in cleaned:
                    continue
                if not cleaned.startswith(root):
                    continue
                if cleaned in pages:
                    continue
                pages.add(cleaned)
                queue.append((cleaned, depth + 1))

        return sorted(pages, key=self._snis_page_sort_key, reverse=True)

    @staticmethod
    def _snis_page_sort_key(url: str) -> Tuple[int, str]:
        parts = [part for part in urlparse(url).path.split("/") if part]
        year = 0
        for part in reversed(parts):
            if len(part) == 4 and part.isdigit():
                year = int(part)
                break
        return year, url

    def _allowed_archive_extensions(self, document: SinisaDocumentLink) -> Optional[Set[str]]:
        if document.kind != "planilhas":
            return None
        return set(self.SNIS_PLANILHA_FINAL_EXTENSIONS)


__all__ = ["SnisDataSource", "SinisaDocumentLink"]
