"""HTTP client for the IBGE SIDRA v3 aggregates API.

SIDRA (https://servicodados.ibge.gov.br/api/v3/agregados) is an open, keyless
JSON service. This client needs only the standard library and shares the error
taxonomy (category / retryable / hint) and retry infrastructure of
:mod:`guaraci.core.http` with the NASA and OpenDataSUS clients so the jobs
layer classifies failures consistently.
"""
from __future__ import annotations

import gzip
import json
from typing import Any, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    open_response,
    request_with_retry,
)


class IbgeClientError(ApiClientError):
    """Raised when IBGE SIDRA API operations fail."""


class IbgeSidraClient:
    """Minimal client for the IBGE SIDRA v3 aggregates endpoint."""

    DEFAULT_BASE_URL = "https://servicodados.ibge.gov.br"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 120,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected:
            raise ValueError("IBGE base URL cannot be empty.")
        self.base_url = selected
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

    def aggregate(
        self,
        *,
        table: str,
        variable: str,
        period: str,
        localities: str,
        classificacao: Optional[str] = None,
    ) -> List[Any]:
        """Fetch one aggregate table/variable for a period and locality filter.

        ``period`` is a SIDRA period token (``"2021"`` or ``"2019|2020"``);
        ``localities`` is a level filter such as ``"N6[all]"`` (all municipalities);
        ``classificacao`` is an optional SIDRA classification filter such as
        ``"2[4,5]|287[93070,93084]"`` (sex Homens/Mulheres by 5-year age groups).
        Returns the raw JSON array SIDRA responds with.
        """
        url = (
            f"{self.base_url}/api/v3/agregados/{quote(str(table), safe='')}"
            f"/periodos/{quote(str(period), safe='|')}"
            f"/variaveis/{quote(str(variable), safe='')}"
            f"?localidades={quote(str(localities), safe='[]|')}"
        )
        if classificacao:
            url += f"&classificacao={quote(str(classificacao), safe='[],|')}"
        payload = self._request_json(url)
        if not isinstance(payload, list):
            raise IbgeClientError(
                "Unexpected IBGE response (expected a JSON array).",
                category="response_format",
                hint="Check the table, variable, period, and locality filter.",
            )
        return payload

    def _request_json(self, url: str) -> Any:
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "guaraci/0.6.0"},
        )

        def on_http_error(exc: HTTPError) -> IbgeClientError:
            category, retryable = classify_http_status(exc.code)
            return IbgeClientError(
                f"IBGE request failed ({exc.code}).",
                category="http_error" if retryable else "configuration",
                retryable=retryable,
                hint="Check the table, variable, period, and locality filter.",
            )

        def on_url_error(exc: URLError) -> IbgeClientError:
            return IbgeClientError(
                f"Could not connect to IBGE endpoint '{self.base_url}': {exc.reason}",
                category="connectivity",
                retryable=True,
                hint="Check internet access, DNS, and firewall/proxy rules.",
            )

        def on_timeout(exc: Exception) -> IbgeClientError:
            return IbgeClientError(
                f"IBGE request timed out after {self.timeout_seconds} seconds.",
                category="timeout",
                retryable=True,
                hint="Retry later or narrow the request if the service is slow.",
            )

        def send() -> Any:
            raw, headers = open_response(
                lambda req, timeout: urlopen(req, timeout=timeout),
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            encoding = ""
            if headers is not None:
                encoding = str(headers.get("Content-Encoding") or "").lower()

            # The IBGE CDN intermittently gzips responses (even unsolicited),
            # so decompress by header or by magic bytes before decoding.
            if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass

            try:
                return json.loads(raw.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise IbgeClientError(
                    "IBGE returned a non-JSON response.",
                    category="response_format",
                    hint="Check the base URL and the aggregates endpoint path.",
                ) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)
