"""Bulk file transport for dadosabertos.saude.gov.br (SRAG, SISAGUA, SIOPS).

The legacy OpenDataSUS adapter (``guaraci.opendatasus.datasource``) is
record-oriented: it queries a CKAN datastore or a paginated DEMAS JSON API.
SRAG bulk, SISAGUA and SIOPS are not exposed that way — each dataset
("package") is a handful of whole-file resources (CSV/Parquet/JSON/XML)
hosted on a public S3 bucket, and the CKAN API on the current portal host is
unavailable (see module docstring in ``client.py`` and
``docs/PLANO_NOVAS_FONTES.md`` Fase A for the live verification notes).

Discovery works by scraping two stable HTML pages (stdlib-only, no new
dependency):

1. ``GET /dataset/<slug>`` — lists resource links
   (``/dataset/<slug>/resource/<uuid>``) with the resource's display name.
2. ``GET /dataset/<slug>/resource/<uuid>`` — the resource page embeds the
   actual S3 file URL
   (``https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/...``).

Downloaded files are cached by basename under the source's output directory;
a second run with the same params is a no-op for files that already exist
(the S3 basenames for frozen years are stable; the current "banco vivo" year
changes basename on every extraction, so it naturally re-downloads).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    decode_text,
    is_timeout_reason,
    open_response,
    read_http_error_body,
    request_with_retry,
)

_KNOWN_FORMATS: Tuple[str, ...] = ("parquet", "csv", "json", "xml")
# Container formats whose *inner* data format is worth surfacing separately
# for ranking (SISAGUA ships CSV/JSON/XML each wrapped in its own .zip, e.g.
# ".../cadastro_populacao_abastecida_csv.zip" - verified live 2026-08-17).
_CONTAINER_FORMATS: Tuple[str, ...] = ("zip",)
_S3_URL_RE = re.compile(
    r"https://s3\.sa-east-1\.amazonaws\.com/ckan\.saude\.gov\.br/[^\"'<>\s]+"
)


class PortalFilesClientError(ApiClientError):
    """Raised when the dadosabertos.saude.gov.br scrape/download fails."""


# ---------------------------------------------------------------------------
# HTML parsing helpers (stdlib only — no BeautifulSoup)
# ---------------------------------------------------------------------------


class _ResourceLinkParser(HTMLParser):
    """Extracts ``(resource_id, visible_name)`` pairs from a dataset page.

    Live markup (verified 2026-08-17) renders each resource as a card whose
    NAME lives in a sibling ``<div class="text-weight-bold">...</div>``
    *before* the ``<a href="/dataset/<slug>/resource/<uuid>">Explorar</a>``
    button — the anchor's own text is just "Explorar" (desktop) or an icon
    (mobile), never the resource name. This parser tracks the most recently
    seen "text-weight-bold" text and attaches it to the next matching anchor,
    which is robust to that card layout without depending on exact class
    nesting/ordering beyond "name div comes before its card's anchor(s)".
    """

    _NAME_CLASS_HINT = "text-weight-bold"

    def __init__(self, slug: str) -> None:
        super().__init__(convert_charrefs=True)
        self._pattern = re.compile(
            rf"^/dataset/{re.escape(slug)}/resource/([0-9a-fA-F-]{{36}})/?$"
        )
        self.resources: List[Tuple[str, str]] = []
        self._pending_name = ""
        self._capturing_name = False
        self._name_depth = 0
        self._name_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        css_class = attrs_dict.get("class") or ""

        if self._capturing_name:
            self._name_depth += 1

        if self._NAME_CLASS_HINT in css_class:
            self._capturing_name = True
            self._name_depth = 1
            self._name_parts = []
            return

        if tag != "a":
            return
        href = attrs_dict.get("href") or ""
        path = urlparse(href).path if href.startswith("http") else href
        match = self._pattern.match(path)
        if match:
            resource_id = match.group(1)
            name = " ".join(self._pending_name.split())
            if name:
                self.resources.append((resource_id, name))

    def handle_data(self, data: str) -> None:
        if self._capturing_name:
            self._name_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capturing_name:
            return
        self._name_depth -= 1
        if self._name_depth <= 0:
            self._capturing_name = False
            self._pending_name = "".join(self._name_parts)
            self._name_parts = []


def parse_dataset_resources(html: str, slug: str) -> List[Tuple[str, str]]:
    """Parse a ``/dataset/<slug>`` page into ``(resource_id, name)`` pairs.

    Deduplicates by ``resource_id``, keeping the first occurrence, and
    preserves document order (which matches publication order on the
    portal).
    """
    parser = _ResourceLinkParser(slug)
    parser.feed(html)
    seen: Dict[str, str] = {}
    ordered: List[Tuple[str, str]] = []
    for resource_id, name in parser.resources:
        if resource_id in seen:
            continue
        seen[resource_id] = name
        ordered.append((resource_id, name))
    return ordered


def parse_resource_s3_url(html: str) -> Optional[str]:
    """Extract the public S3 file URL embedded in a resource page."""
    match = _S3_URL_RE.search(html)
    return match.group(0) if match else None


def _extract_year(name: str, year_regex: str) -> Optional[int]:
    match = re.search(year_regex, name)
    if not match:
        return None
    candidate = match.group(1) if match.groups() else match.group(0)
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def _extract_format(name: str, url: str) -> str:
    """Infer the resource's data format from its URL (and, as a fallback,
    its display name).

    When the URL points at a known data format (``.parquet``/``.csv``/...)
    that suffix is returned directly. When it points at a container format
    (currently just ``.zip``), the inner format is inferred from a token in
    the URL's filename stem (e.g. ``..._csv.zip`` -> ``"csv"``) so format
    ranking still works for SISAGUA, which ships one zip per format with no
    parquet alternative.
    """
    path = Path(urlparse(url).path)
    suffix = path.suffix.lower().lstrip(".")
    if suffix in _KNOWN_FORMATS:
        return suffix

    stem_lower = path.stem.lower()
    if suffix in _CONTAINER_FORMATS:
        for fmt in _KNOWN_FORMATS:
            if re.search(rf"(?:^|[_.\-]){fmt}(?:[_.\-]|$)", stem_lower):
                return fmt

    lowered_name = name.lower()
    for fmt in _KNOWN_FORMATS:
        if fmt in lowered_name:
            return fmt
    return suffix or "unknown"


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class PortalFilesClient:
    """Thin urllib client for the dadosabertos.saude.gov.br HTML portal.

    No CKAN/JSON API is available on this host (verified 2026-08-17 — both
    ``/api/3/action`` and ``/api/action`` return 404). Discovery is 2-hop
    HTML scraping; downloads stream the discovered S3 URLs straight to disk.
    """

    DEFAULT_BASE_URL = "https://dadosabertos.saude.gov.br"
    USER_AGENT = "guaraci/0.6.0"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: int = 60,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self.base_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not self.base_url:
            raise ValueError("Portal base URL cannot be empty.")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

    def get_dataset_page(self, slug: str) -> str:
        url = f"{self.base_url}/dataset/{slug}"
        return self._get_text(url, context=f"portal dataset page '{url}'")

    def get_resource_page(self, slug: str, resource_id: str) -> str:
        url = f"{self.base_url}/dataset/{slug}/resource/{resource_id}"
        return self._get_text(url, context=f"portal resource page '{url}'")

    def head_content_length(self, url: str) -> Optional[int]:
        """Best-effort ``Content-Length`` lookup; ``None`` on any failure."""
        request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                value = response.headers.get("Content-Length")
                return int(value) if value is not None else None
        except Exception:  # noqa: BLE001 - discovery sizing is best-effort
            return None

    def download_file(
        self,
        url: str,
        destination: Path,
        *,
        chunk_size: int = 1024 * 1024,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> int:
        """Stream ``url`` to ``destination`` (via a ``.part`` temp file)."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_name(destination.name + ".part")
        request = Request(url, headers={"User-Agent": self.USER_AGENT})

        def on_http_error(exc: HTTPError) -> PortalFilesClientError:
            category, retryable = classify_http_status(exc.code)
            return PortalFilesClientError(
                f"Portal file download failed ({exc.code}) for '{url}'.",
                category=category,
                retryable=retryable,
                hint="Check the discovered S3 URL is still valid; re-run discover().",
            )

        def on_url_error(exc: URLError) -> PortalFilesClientError:
            category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
            return PortalFilesClientError(
                f"Could not download portal file '{url}': {exc.reason}",
                category=category,
                retryable=True,
                hint="Check internet access and retry.",
            )

        def on_timeout(exc: Exception) -> PortalFilesClientError:
            return PortalFilesClientError(
                f"Timed out downloading portal file '{url}' after "
                f"{self.timeout_seconds} seconds.",
                category="timeout",
                retryable=True,
                hint="Retry, or increase timeout for large SISAGUA/SRAG files.",
            )

        def send() -> int:
            written = 0
            try:
                with open_fn_context(request, self.timeout_seconds) as response:
                    with tmp_path.open("wb") as handle:
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            handle.write(chunk)
                            written += len(chunk)
                            if progress_callback is not None:
                                progress_callback(written)
            except HTTPError as exc:
                error = on_http_error(exc)
                raise error from exc
            except URLError as exc:
                raise on_url_error(exc) from exc
            except (TimeoutError,) as exc:
                raise on_timeout(exc) from exc
            return written

        def open_fn_context(req: Request, timeout: float):
            return urlopen(req, timeout=timeout)

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
        tmp_path.replace(destination)
        return written

    def _get_text(self, url: str, *, context: str) -> str:
        request = Request(
            url,
            headers={"Accept": "text/html", "User-Agent": self.USER_AGENT},
        )

        def on_http_error(exc: HTTPError) -> PortalFilesClientError:
            category, retryable = classify_http_status(exc.code)
            message = read_http_error_body(exc)
            return PortalFilesClientError(
                f"Request failed ({exc.code}) for {context}: {message}",
                category=category,
                retryable=retryable,
                hint="Check the dataset slug and the portal's current URL layout.",
            )

        def on_url_error(exc: URLError) -> PortalFilesClientError:
            category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
            return PortalFilesClientError(
                f"Could not connect to {context}: {exc.reason}",
                category=category,
                retryable=True,
                hint="Check internet access, DNS, and the portal host status.",
            )

        def on_timeout(exc: Exception) -> PortalFilesClientError:
            return PortalFilesClientError(
                f"Request to {context} timed out after {self.timeout_seconds} seconds.",
                category="timeout",
                retryable=True,
                hint="Retry with a longer timeout.",
            )

        def send() -> str:
            raw_bytes, _headers = open_response(
                lambda req, timeout: urlopen(req, timeout=timeout),
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            return decode_text(raw_bytes)

        return request_with_retry(send, max_attempts=self.max_attempts)


# ---------------------------------------------------------------------------
# Package specs (one per registered "opendatasus files" source)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortalFilePackageSpec:
    """Static metadata describing how to discover/filter one portal package."""

    slug: str
    include_terms: Tuple[str, ...] = ()
    exclude_terms: Tuple[str, ...] = ()
    year_regex: str = r"(20\d{2})"
    format_priority: Tuple[str, ...] = ("parquet", "csv")
    large_dataset_note: Optional[str] = None


# SISAGUA resource pages (verified live 2026-08-17) always ship one .zip per
# inner format (csv/json/xml — no parquet), so ranking prefers csv first.
_SISAGUA_FORMAT_PRIORITY: Tuple[str, ...] = ("csv", "json", "xml")
# Every SISAGUA dataset page also lists a data-dictionary resource, and some
# list a top-level "API Sisagua - ..." teaser resource; neither is tabular
# data. Matched defensively by a short accent-insensitive stem.
_SISAGUA_EXCLUDE_TERMS: Tuple[str, ...] = ("dicion", "api sisagua")

PACKAGE_SPECS: Dict[str, PortalFilePackageSpec] = {
    "srag_arquivos": PortalFilePackageSpec(
        slug="srag-2019-a-2026",
        include_terms=("banco vivo",),
        format_priority=("parquet", "csv", "json", "xml"),
    ),
    "sisagua_controle_mensal_parametros_basicos": PortalFilePackageSpec(
        slug="sisagua-controle-mensal-parametros-basicos",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "SISAGUA controle mensal e um dataset GRANDE (potencialmente "
            "milhoes de linhas). Prefira start_year/end_year restritos."
        ),
    ),
    "sisagua_controle_semestral": PortalFilePackageSpec(
        slug="sisagua-controle-semestral",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
    "sisagua_vigilancia_parametros_basicos": PortalFilePackageSpec(
        slug="sisagua-vigilancia-parametros-basicos",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
    "sisagua_tratamento_agua": PortalFilePackageSpec(
        slug="sisagua-tratamento-de-agua",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
    "sisagua_populacao_abastecida": PortalFilePackageSpec(
        slug="sisagua-populacao-abastecida",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
    # Remaining 9 SISAGUA packages (verified live 2026-08-18). Every one of
    # them ships a single cumulative file per format (no year segmentation
    # in the resource name) EXCEPT "plano de amostragem", which is
    # year-segmented 2014-2026 like the other "controle mensal" packages
    # registered above.
    "sisagua_controle_mensal_demais_parametros": PortalFilePackageSpec(
        slug="sisagua-controle-mensal-demais-parametros",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "SISAGUA controle mensal e um dataset GRANDE (potencialmente "
            "milhoes de linhas; ~138MB comprimido, verificado ao vivo "
            "2026-08-18). Prefira baixar em um output_dir dedicado."
        ),
    ),
    "sisagua_controle_mensal_amostras_fora_do_padrao": PortalFilePackageSpec(
        slug="sisagua-controle-mensal-amostras-fora-do-padrao",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "SISAGUA controle mensal e um dataset GRANDE (potencialmente "
            "milhoes de linhas; ~43MB comprimido, verificado ao vivo "
            "2026-08-18)."
        ),
    ),
    "sisagua_controle_mensal_plano_amostragem": PortalFilePackageSpec(
        slug="sisagua-controle-mensal-plano-amostragem",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "SISAGUA controle mensal e um dataset GRANDE (potencialmente "
            "milhoes de linhas por ano, ano-segmentado desde 2014 - "
            "verificado ao vivo 2026-08-18). Prefira um recorte de ano por vez."
        ),
    ),
    "sisagua_controle_mensal_infraestrutura_operacional": PortalFilePackageSpec(
        slug="sisagua-controle-mensal-infraestrutura-operacional",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "SISAGUA controle mensal e um dataset GRANDE (potencialmente "
            "milhoes de linhas; ~39MB comprimido, verificado ao vivo "
            "2026-08-18)."
        ),
    ),
    "sisagua_vigilancia_demais_parametros": PortalFilePackageSpec(
        slug="sisagua-vigilancia-demais-parametros",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "Dataset GRANDE (potencialmente milhoes de linhas; ~98MB "
            "comprimido, verificado ao vivo 2026-08-18)."
        ),
    ),
    "sisagua_vigilancia_cianobacterias_e_cianotoxinas": PortalFilePackageSpec(
        slug="sisagua-vigilancia-cianobacterias-e-cianotoxinas",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
    "sisagua_pontos_de_captacao": PortalFilePackageSpec(
        slug="sisagua-pontos-de-captacao",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
        large_dataset_note=(
            "~53MB comprimido (verificado ao vivo 2026-08-18) - considere "
            "um output_dir dedicado."
        ),
    ),
    "sisagua_cadastro_carro_pipa_procedencia": PortalFilePackageSpec(
        slug="sisagua-cadastro-carro-pipa-procedencia",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
    "sisagua_cadastro_carro_pipa_populacao": PortalFilePackageSpec(
        slug="sisagua-cadastro-carro-pipa-populacao",
        exclude_terms=_SISAGUA_EXCLUDE_TERMS,
        format_priority=_SISAGUA_FORMAT_PRIORITY,
    ),
}


@dataclass(frozen=True)
class PortalFileResourceInfo:
    """One discovered file resource (name/format/year/URL/size)."""

    resource_id: str
    name: str
    format: str
    year: Optional[int]
    url: str
    size_bytes: Optional[int] = None

    @property
    def basename(self) -> str:
        name = Path(urlparse(self.url).path).name
        return name or f"{self.resource_id}.bin"

    def to_dict(self) -> Dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "format": self.format,
            "year": self.year,
            "url": self.url,
            "basename": self.basename,
            "size_bytes": self.size_bytes,
        }


# ---------------------------------------------------------------------------
# DataSource
# ---------------------------------------------------------------------------


class PortalFileDataSource(DataSource):
    """Bulk file transport for dadosabertos.saude.gov.br packages."""

    DEFAULT_TIMEOUT = 60
    PACKAGE_SPECS = PACKAGE_SPECS

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[PortalFilesClient] = None,
    ) -> None:
        super().__init__(name="opendatasus_portal_files", output_path=output_path)
        self._client = client

    # -- spec/client resolution -------------------------------------------------

    def _resolve_spec(self, dataset: str) -> PortalFilePackageSpec:
        key = (dataset or "").strip().lower()
        spec = self.PACKAGE_SPECS.get(key)
        if spec is None:
            supported = ", ".join(sorted(self.PACKAGE_SPECS))
            raise ValueError(
                f"Unsupported portal-files dataset '{dataset}'. Known: {supported}"
            )
        return spec

    def _resolve_client(
        self,
        *,
        api_base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> PortalFilesClient:
        if api_base_url and str(api_base_url).strip():
            return PortalFilesClient(
                base_url=str(api_base_url), timeout_seconds=timeout or self.DEFAULT_TIMEOUT
            )
        if self._client is not None:
            return self._client
        return PortalFilesClient(timeout_seconds=timeout or self.DEFAULT_TIMEOUT)

    # -- discovery ----------------------------------------------------------

    def _discover_resources(
        self,
        client: PortalFilesClient,
        spec: PortalFilePackageSpec,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        resource_filter: Optional[str] = None,
        fetch_sizes: bool = False,
    ) -> List[PortalFileResourceInfo]:
        dataset_html = client.get_dataset_page(spec.slug)
        links = parse_dataset_resources(dataset_html, spec.slug)

        include_terms = tuple(term.lower() for term in spec.include_terms)
        exclude_terms = tuple(term.lower() for term in spec.exclude_terms)
        extra_filter = resource_filter.strip().lower() if resource_filter else None

        results: List[PortalFileResourceInfo] = []
        for resource_id, name in links:
            lowered = name.lower()
            if include_terms and not any(term in lowered for term in include_terms):
                continue
            if exclude_terms and any(term in lowered for term in exclude_terms):
                continue
            if extra_filter and extra_filter not in lowered:
                continue

            year = _extract_year(name, spec.year_regex)
            if start_year is not None and year is not None and year < start_year:
                continue
            if end_year is not None and year is not None and year > end_year:
                continue

            resource_html = client.get_resource_page(spec.slug, resource_id)
            url = parse_resource_s3_url(resource_html)
            if not url:
                continue

            fmt = _extract_format(name, url)
            size_bytes = client.head_content_length(url) if fetch_sizes else None
            results.append(
                PortalFileResourceInfo(
                    resource_id=resource_id,
                    name=name,
                    format=fmt,
                    year=year,
                    url=url,
                    size_bytes=size_bytes,
                )
            )
        return results

    def discover(
        self,
        dataset: str,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        resource_filter: Optional[str] = None,
        fetch_sizes: bool = False,
        api_base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        **_ignored: object,
    ) -> Dict[str, object]:
        """List matching resources WITHOUT downloading (discovery preflight)."""
        spec = self._resolve_spec(dataset)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)
        resources = self._discover_resources(
            client,
            spec,
            start_year=start_year,
            end_year=end_year,
            resource_filter=resource_filter,
            fetch_sizes=fetch_sizes,
        )
        payload: Dict[str, object] = {
            "dataset": (dataset or "").strip().lower(),
            "slug": spec.slug,
            "documents_found": len(resources),
            "resources": [item.to_dict() for item in resources],
        }
        if spec.large_dataset_note:
            payload["note"] = spec.large_dataset_note
        if fetch_sizes:
            known_sizes = [item.size_bytes for item in resources if item.size_bytes is not None]
            if known_sizes:
                payload["total_size_bytes"] = sum(known_sizes)
        return payload

    # -- download -------------------------------------------------------------

    def download(
        self,
        dataset: str,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        resource_filter: Optional[str] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
        **_ignored: object,
    ) -> Dict[str, object]:
        dataset_key = (dataset or "").strip().lower()
        spec = self._resolve_spec(dataset_key)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)
        resources = self._discover_resources(
            client,
            spec,
            start_year=start_year,
            end_year=end_year,
            resource_filter=resource_filter,
            fetch_sizes=False,
        )

        selected = self._select_best_per_year(resources, spec)

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": dataset_key,
                    "documents_total": len(selected),
                }
            )

        materialized: List[str] = []
        skipped: List[str] = []
        failed: List[str] = []
        for index, resource in enumerate(selected, start=1):
            dest_path = self.output_path / resource.basename
            if dest_path.exists():
                skipped.append(str(dest_path))
                materialized.append(str(dest_path))
            else:
                try:
                    client.download_file(resource.url, dest_path)
                    materialized.append(str(dest_path))
                except Exception:  # noqa: BLE001 - recorded as failed, not raised
                    failed.append(resource.url)

            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": dataset_key,
                        "documents_total": len(selected),
                        "document_index": index,
                        "file_path": str(dest_path),
                    }
                )

        exported_files: List[str] = []
        warnings: List[str] = []
        if output_format:
            for index, path_str in enumerate(materialized):
                path = Path(path_str)
                if not path.exists():
                    continue
                try:
                    export_path = self._convert_to_format(path, output_format)
                    exported_files.append(str(export_path))
                    # keep_raw=False discards the originally downloaded raw
                    # file once it has been converted, since SISAGUA/SRAG
                    # bulk files can be multi-GB and users who asked for a
                    # converted export usually don't need both copies.
                    if not keep_raw and export_path != path and path.exists():
                        path.unlink(missing_ok=True)
                        materialized[index] = str(export_path)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"Failed to export '{path.name}' to {output_format}: {exc}"
                    )
        if failed:
            warnings.append(
                f"{len(failed)} resource(s) failed to download: {', '.join(failed)}"
            )
        if not keep_raw and not output_format and not failed:
            warnings.append(
                "Raw files were materialized under output_dir; set output_format "
                "to also export a converted dataset."
            )

        manifest_path = self._write_manifest(
            dataset=dataset_key,
            spec=spec,
            start_year=start_year,
            end_year=end_year,
            resource_filter=resource_filter,
            resources=selected,
            materialized=materialized,
            skipped=skipped,
            failed=failed,
            exported_files=exported_files,
            keep_raw=keep_raw,
            output_format=output_format,
            warnings=warnings,
        )

        downloaded_count = len(materialized) - len(skipped)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": dataset_key,
                    "documents_total": len(selected),
                    "downloaded_count": downloaded_count,
                    "failed_count": len(failed),
                    "skipped_count": len(skipped),
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": len(selected),
            "downloaded_count": downloaded_count,
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "dataset": dataset_key,
            "start_year": start_year,
            "end_year": end_year,
            "materialized_paths": materialized,
            "exported_files": exported_files,
            "keep_raw": keep_raw,
            "output_format": output_format,
        }
        if warnings:
            payload["export_warning"] = " ".join(warnings)
        return payload

    @staticmethod
    def _select_best_per_year(
        resources: Sequence[PortalFileResourceInfo],
        spec: PortalFilePackageSpec,
    ) -> List[PortalFileResourceInfo]:
        """Pick one resource per year, preferring ``spec.format_priority``.

        Some packages are year-segmented (SRAG, most SISAGUA "controle" /
        "vigilancia" datasets) and also list a couple of non-year resources
        on the same dataset page (a top-level "API Sisagua - ..." teaser and
        a "Dicionario - ..." data dictionary — verified live 2026-08-17).
        Those have no detectable year, so when at least one year-bearing
        resource exists, year=None resources are dropped as non-data noise.
        Cumulative packages with NO year in any resource name (e.g.
        ``sisagua_populacao_abastecida``) still work: the whole set falls
        into the ``None`` bucket and one best-format resource is picked.
        """
        by_year: Dict[object, List[PortalFileResourceInfo]] = {}
        for resource in resources:
            by_year.setdefault(resource.year, []).append(resource)

        if len(by_year) > 1 and None in by_year:
            by_year.pop(None)

        def _rank(resource: PortalFileResourceInfo) -> int:
            try:
                return spec.format_priority.index(resource.format)
            except ValueError:
                return len(spec.format_priority)

        selected: List[PortalFileResourceInfo] = []
        for year in sorted(by_year, key=lambda value: (value is None, value)):
            candidates = sorted(by_year[year], key=_rank)
            if candidates:
                selected.append(candidates[0])
        return selected

    def _convert_to_format(self, path: Path, output_format: str) -> Path:
        normalized = output_format.strip().lower()
        suffix = path.suffix.lower().lstrip(".")
        if suffix == normalized:
            return path
        if suffix == "parquet":
            frame = pl.read_parquet(path)
        elif suffix == "csv":
            frame = pl.read_csv(path, infer_schema_length=10000, ignore_errors=True)
        else:
            raise ValueError(
                f"Cannot convert resource format '{suffix}' to '{normalized}' "
                "(only parquet/csv sources are convertible)."
            )
        dest = path.with_suffix(f".{normalized}")
        if normalized == "csv":
            frame.write_csv(dest)
        elif normalized == "parquet":
            frame.write_parquet(dest)
        elif normalized == "sqlite":
            with sqlite3.connect(dest) as connection:
                frame.to_pandas().to_sql(
                    "records", connection, if_exists="replace", index=False
                )
        else:
            raise ValueError(f"Unsupported output format '{output_format}'.")
        return dest

    # -- manifest / abstract contract ---------------------------------------

    def load_dataframe(self, dataset: Optional[str] = None) -> pl.DataFrame:  # noqa: D401
        raise NotImplementedError(
            "PortalFileDataSource materializes whole files on disk; read them "
            "directly with polars (scan_parquet/read_csv) instead of load_dataframe()."
        )

    def _write_manifest(
        self,
        *,
        dataset: str,
        spec: PortalFilePackageSpec,
        start_year: Optional[int],
        end_year: Optional[int],
        resource_filter: Optional[str],
        resources: Sequence[PortalFileResourceInfo],
        materialized: List[str],
        skipped: List[str],
        failed: List[str],
        exported_files: List[str],
        keep_raw: bool,
        output_format: Optional[str],
        warnings: List[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        request_filters = {
            "dataset": dataset,
            "slug": spec.slug,
            "start_year": start_year,
            "end_year": end_year,
            "resource_filter": resource_filter,
            "keep_raw": keep_raw,
            "output_format": output_format,
            "resources": [item.to_dict() for item in resources],
        }
        manifest = DownloadManifest(
            source=dataset,
            filters=request_filters,
            documents_found=len(resources),
            downloaded_files=[],
            skipped_files=skipped,
            failed_urls=failed,
            materialized_paths=materialized,
            exported_files=list(exported_files),
            warnings=list(warnings),
        )
        manifest_path.write_text(
            _json_dumps(manifest.to_dict()), encoding="utf-8"
        )
        return manifest_path


def _json_dumps(payload: Mapping[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)
