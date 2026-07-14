"""HTTP client for the IBGE SIDRA v3 aggregates API.

SIDRA (https://servicodados.ibge.gov.br/api/v3/agregados) is an open, keyless
JSON service. This client needs only the standard library and mirrors the error
taxonomy (category / retryable / hint) used by the NASA and OpenDataSUS clients
so the jobs layer classifies failures consistently.
"""
from __future__ import annotations

import json
import socket
from typing import Any, List
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class IbgeClientError(RuntimeError):
    """Raised when IBGE SIDRA API operations fail."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "api_error",
        retryable: bool = False,
        hint: str | None = None,
    ) -> None:
        self.message = str(message).strip()
        self.category = category
        self.retryable = retryable
        self.hint = str(hint).strip() if hint else None
        super().__init__(self.message if not self.hint else f"{self.message} Hint: {self.hint}")

    def with_context(self, context: str) -> "IbgeClientError":
        text = str(context).strip()
        if not text:
            return self
        return IbgeClientError(
            f"{text}. {self.message}",
            category=self.category,
            retryable=self.retryable,
            hint=self.hint,
        )


class IbgeSidraClient:
    """Minimal client for the IBGE SIDRA v3 aggregates endpoint."""

    DEFAULT_BASE_URL = "https://servicodados.ibge.gov.br"

    def __init__(self, *, base_url: str | None = None, timeout_seconds: int = 120) -> None:
        selected = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected:
            raise ValueError("IBGE base URL cannot be empty.")
        self.base_url = selected
        self.timeout_seconds = max(1, int(timeout_seconds))

    def aggregate(
        self, *, table: str, variable: str, period: str, localities: str
    ) -> List[Any]:
        """Fetch one aggregate table/variable for a period and locality filter.

        ``period`` is a SIDRA period token (``"2021"`` or ``"2019|2020"``);
        ``localities`` is a level filter such as ``"N6[all]"`` (all municipalities).
        Returns the raw JSON array SIDRA responds with.
        """
        url = (
            f"{self.base_url}/api/v3/agregados/{quote(str(table), safe='')}"
            f"/periodos/{quote(str(period), safe='|')}"
            f"/variaveis/{quote(str(variable), safe='')}"
            f"?localidades={quote(str(localities), safe='[]|')}"
        )
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
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            retryable = exc.code in {408, 429} or 500 <= exc.code <= 599
            raise IbgeClientError(
                f"IBGE request failed ({exc.code}).",
                category="http_error" if retryable else "configuration",
                retryable=retryable,
                hint="Check the table, variable, period, and locality filter.",
            ) from exc
        except URLError as exc:
            raise IbgeClientError(
                f"Could not connect to IBGE endpoint '{self.base_url}': {exc.reason}",
                category="connectivity",
                retryable=True,
                hint="Check internet access, DNS, and firewall/proxy rules.",
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise IbgeClientError(
                f"IBGE request timed out after {self.timeout_seconds} seconds.",
                category="timeout",
                retryable=True,
                hint="Retry later or narrow the request if the service is slow.",
            ) from exc

        try:
            return json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IbgeClientError(
                "IBGE returned a non-JSON response.",
                category="response_format",
                hint="Check the base URL and the aggregates endpoint path.",
            ) from exc
