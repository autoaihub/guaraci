"""HTTP client for INMET's historical automatic-station ZIP archives.

INMET (https://portal.inmet.gov.br) publishes one ZIP per year with every
automatic weather station's raw hourly series:
``https://portal.inmet.gov.br/uploads/dadoshistoricos/<AAAA>.zip``. There is
no JSON API and no authentication. Verified live on 2026-08-17/18:

- Years 2000-2026 exist; 2026 (the current year) is a partial, growing
  archive that gets republished with more months over time.
- ``HEAD`` works and returns ``Content-Length`` + ``Accept-Ranges: bytes``
  when a normal ``User-Agent`` header is sent (a bare ``curl`` request with no
  ``User-Agent`` at all was reset by the portal's edge, so this client always
  sends one).
- File sizes range from ~530 KB (2000, 5 stations) to ~90 MB (a full recent
  year, ~594 stations) — well within what an agent loop can download for a
  smoke test, but still large enough that the datasource caches the ZIP on
  disk and only re-fetches the current year when ``Content-Length`` changes.

This client streams the ZIP straight to disk (never loads the whole archive
into memory) and shares the request/error-taxonomy conventions from
``guaraci.core.http`` (category / retryable / hint) even though the actual
transfer is a manual chunked read+write, not the JSON-oriented helpers there.
"""

from __future__ import annotations

import time
from pathlib import Path
from time import monotonic
from typing import Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    backoff_delay,
    classify_http_status,
    is_timeout_reason,
    read_http_error_body,
)

ProgressCallback = Callable[[Dict[str, object]], None]


class InmetClientError(ApiClientError):
    """Raised when INMET portal ZIP operations fail."""


class InmetClient:
    """Minimal client for INMET's per-year historical-data ZIP archives."""

    DEFAULT_BASE_URL = "https://portal.inmet.gov.br/uploads/dadoshistoricos"
    USER_AGENT = "guaraci/0.6.0"
    CHUNK_SIZE = 1024 * 256

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: int = 180,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected:
            raise ValueError("INMET base URL cannot be empty.")
        self.base_url = selected
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

    def zip_url(self, year: int) -> str:
        return f"{self.base_url}/{int(year)}.zip"

    def head_content_length(self, year: int) -> Optional[int]:
        """Probe the remote ZIP size via HTTP HEAD.

        Used to reconcile the still-growing current-year archive against a
        cached copy. Returns ``None`` when the upstream omits
        ``Content-Length`` (never fails the caller just for that).
        """
        url = self.zip_url(year)
        request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.headers.get("Content-Length")
        except HTTPError as exc:
            raise self._http_error(exc, year=year) from exc
        except URLError as exc:
            raise self._url_error(exc, year=year) from exc
        except TimeoutError as exc:
            raise self._timeout_error(year=year) from exc
        if raw is None or not str(raw).isdigit():
            return None
        return int(raw)

    def download_zip(
        self,
        year: int,
        destination: Path,
        *,
        source_name: str = "inmet_estacoes",
        progress_callback: Optional[ProgressCallback] = None,
    ) -> int:
        """Stream one year's ZIP to ``destination``; returns bytes written.

        Retries the whole transfer (not partial ranges) up to
        ``max_attempts`` times on retryable errors, writing to a ``.part``
        sidecar first so a crash mid-download never leaves a corrupt file at
        the final path.
        """
        url = self.zip_url(year)
        destination.parent.mkdir(parents=True, exist_ok=True)
        last_error: Optional[InmetClientError] = None
        for attempt in range(self.max_attempts):
            try:
                return self._stream_once(
                    url,
                    destination,
                    year=year,
                    source_name=source_name,
                    progress_callback=progress_callback,
                )
            except InmetClientError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.max_attempts - 1:
                    raise
                time.sleep(backoff_delay(attempt))
        assert last_error is not None  # pragma: no cover - loop always returns/raises
        raise last_error

    def _stream_once(
        self,
        url: str,
        destination: Path,
        *,
        year: int,
        source_name: str,
        progress_callback: Optional[ProgressCallback],
    ) -> int:
        request = Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                total_raw = response.headers.get("Content-Length")
                total = int(total_raw) if total_raw and str(total_raw).isdigit() else None
                written = 0
                last_emit = monotonic()
                tmp_path = destination.with_name(destination.name + ".part")
                with tmp_path.open("wb") as handle:
                    while True:
                        chunk = response.read(self.CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                        written += len(chunk)
                        now = monotonic()
                        done = bool(total) and written >= total
                        if progress_callback and (now - last_emit >= 0.2 or done):
                            progress_callback(
                                {
                                    "event": "file_progress",
                                    "source": source_name,
                                    "url": url,
                                    "file_path": str(destination),
                                    "file_bytes_downloaded": written,
                                    "file_total_bytes": total,
                                }
                            )
                            last_emit = now
                tmp_path.replace(destination)
                return written
        except HTTPError as exc:
            raise self._http_error(exc, year=year) from exc
        except URLError as exc:
            raise self._url_error(exc, year=year) from exc
        except TimeoutError as exc:
            raise self._timeout_error(year=year) from exc

    def _http_error(self, exc: HTTPError, *, year: int) -> InmetClientError:
        category, retryable = classify_http_status(
            exc.code, configuration_codes=frozenset({400, 404})
        )
        if exc.code == 404:
            hint = f"ZIP not published for year {year}; check the year range (2000+)."
        elif retryable:
            hint = "Retry later; the INMET portal may be busy."
        else:
            hint = "Check the base URL and year."
        message = read_http_error_body(exc) or f"HTTP {exc.code}"
        return InmetClientError(
            f"INMET request failed ({exc.code}) for year {year}: {message}",
            category=category,
            retryable=retryable,
            hint=hint,
        )

    def _url_error(self, exc: URLError, *, year: int) -> InmetClientError:
        if is_timeout_reason(exc.reason):
            return InmetClientError(
                f"INMET request timed out for year {year}.",
                category="timeout",
                retryable=True,
                hint="Retry with a longer timeout if the portal remains slow.",
            )
        return InmetClientError(
            f"Could not connect to INMET portal for year {year}: {exc.reason}",
            category="connectivity",
            retryable=True,
            hint="Check internet access, DNS resolution, and firewall/proxy rules.",
        )

    def _timeout_error(self, *, year: int) -> InmetClientError:
        return InmetClientError(
            f"INMET request timed out for year {year} after {self.timeout_seconds}s.",
            category="timeout",
            retryable=True,
            hint="Retry with a longer timeout if the portal remains slow.",
        )
