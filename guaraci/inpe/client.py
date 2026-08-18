"""HTTP client for the INPE Queimadas (BDQueimadas) file server.

``dataserver-coids.inpe.br`` serves fire-spot ("focos de queimada") CSV
extracts as plain files behind an Apache-style autoindex (no JSON API, no
CKAN). This client does two things:

- ``list_directory``: fetch an index page and parse the ``<a href="...">``
  filenames it lists (stdlib regex, no BeautifulSoup — no new dependency).
- ``fetch_bytes``: download one file's raw bytes (the annual/monthly extracts
  are ZIP or plain CSV).

Shares the request/decode/classify/retry infrastructure from
:mod:`guaraci.core.http` (same pattern as ``guaraci/nasa/client.py`` and
``guaraci/ibge/client.py``).
"""

from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    decode_text,
    is_timeout_reason,
    open_response,
    request_with_retry,
)

# Apache autoindex file links: href="name.ext" (no leading slash, no query
# string, no trailing slash - which excludes the parent-directory link, the
# sort-order query links, and subdirectories).
_HREF_RE = re.compile(r'href="([^"/?][^"]*)"')


class InpeQueimadasClientError(ApiClientError):
    """Raised when INPE Queimadas file-server operations fail."""


class InpeQueimadasClient:
    """Minimal client for the INPE Queimadas CSV file server."""

    DEFAULT_BASE_URL = (
        "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv"
    )

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 180,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("INPE Queimadas base URL cannot be empty.")
        self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

    def list_directory(self, path: str) -> list[str]:
        """List filenames linked from an autoindex page at ``base_url/path/``."""
        url = self._url(path, trailing_slash=True)
        html = self._request_text(url)
        return self._parse_index_filenames(html)

    def fetch_bytes(self, path: str) -> bytes:
        """Download one file's raw bytes from ``base_url/path``."""
        url = self._url(path, trailing_slash=False)
        return self._request_bytes(url)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_index_filenames(html: str) -> list[str]:
        names: list[str] = []
        for match in _HREF_RE.finditer(html):
            href = match.group(1)
            if href.endswith("/"):
                continue
            if href not in names:
                names.append(href)
        return names

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    def _url(self, path: str, *, trailing_slash: bool) -> str:
        clean = path.strip("/")
        url = f"{self.base_url}/{clean}"
        if trailing_slash:
            url = f"{url}/"
        return url

    def _request_text(self, url: str) -> str:
        return decode_text(self._request_raw(url, accept="text/html"))

    def _request_bytes(self, url: str) -> bytes:
        return self._request_raw(url, accept="application/octet-stream, */*")

    def _request_raw(self, url: str, *, accept: str) -> bytes:
        request = Request(
            url,
            headers={"Accept": accept, "User-Agent": "guaraci/0.6.0"},
        )

        def on_http_error(exc: HTTPError) -> InpeQueimadasClientError:
            category, retryable, hint = self._classify_http_error(exc.code)
            return InpeQueimadasClientError(
                f"INPE Queimadas request failed ({exc.code}) for '{url}'.",
                category=category,
                retryable=retryable,
                hint=hint,
            )

        def on_url_error(exc: URLError) -> InpeQueimadasClientError:
            category, hint = self._classify_url_error_reason(exc.reason)
            return InpeQueimadasClientError(
                f"Could not connect to INPE Queimadas endpoint "
                f"'{self.base_url}': {exc.reason}",
                category=category,
                retryable=True,
                hint=hint,
            )

        def on_timeout(exc: Exception) -> InpeQueimadasClientError:
            return InpeQueimadasClientError(
                f"INPE Queimadas request timed out after "
                f"{self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint="Retry with a narrower year/month range if the service is slow.",
            )

        def send() -> bytes:
            raw_bytes, _headers = open_response(
                lambda req, timeout: urlopen(req, timeout=timeout),
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            return raw_bytes

        return request_with_retry(send, max_attempts=self.max_attempts)

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        category, retryable = classify_http_status(
            code, configuration_codes=frozenset({404})
        )
        if code == 404:
            hint = (
                "The requested year/month may not be published yet, or the "
                "dataset/directory layout changed - check "
                "https://data.inpe.br/queimadas/dados-abertos/."
            )
        elif retryable:
            hint = "Retry later; the INPE file server may be busy."
        else:
            hint = "Check request parameters and endpoint compatibility before retrying."
        return category, retryable, hint

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if is_timeout_reason(reason):
            return (
                "timeout",
                "Retry with a narrower year/month range if the service remains slow.",
            )
        return (
            "connectivity",
            "Check internet access, DNS resolution, and firewall/proxy rules.",
        )
