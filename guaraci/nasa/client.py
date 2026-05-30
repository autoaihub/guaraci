"""HTTP client for the NASA POWER API.

NASA POWER (https://power.larc.nasa.gov) is an open, keyless REST service.
This client only needs the standard library; it mirrors the error taxonomy
used by :class:`guaraci.opendatasus.client.OpenDataSUSClient` (category /
retryable / hint) so the jobs layer can classify failures consistently.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Dict, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class NasaPowerClientError(RuntimeError):
    """Raised when NASA POWER API operations fail."""

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
        super().__init__(self._compose_message())

    def _compose_message(self) -> str:
        if not self.hint:
            return self.message
        return f"{self.message} Hint: {self.hint}"

    def with_context(self, context: str) -> "NasaPowerClientError":
        context_text = str(context).strip()
        if not context_text:
            return self
        return NasaPowerClientError(
            f"{context_text}. {self.message}",
            category=self.category,
            retryable=self.retryable,
            hint=self.hint,
        )


class NasaPowerClient:
    """Minimal client for the NASA POWER temporal endpoints."""

    DEFAULT_BASE_URL = "https://power.larc.nasa.gov"
    VALID_TEMPORAL = ("daily", "monthly")
    VALID_COMMUNITIES = ("AG", "RE", "SB")

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("NASA POWER base URL cannot be empty.")
        self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))

    def temporal_point(
        self,
        *,
        temporal: str,
        parameters: Sequence[str],
        latitude: float,
        longitude: float,
        start: str,
        end: str,
        community: str = "AG",
    ) -> Dict[str, object]:
        """Fetch a single-point temporal series from NASA POWER.

        ``start``/``end`` follow the API's per-temporal convention: ``YYYYMMDD``
        for daily and ``YYYY`` for monthly. ``parameters`` is the list of POWER
        variable codes (for example ``T2M`` or ``PRECTOTCORR``).
        """

        temporal_clean = temporal.strip().lower()
        if temporal_clean not in self.VALID_TEMPORAL:
            raise NasaPowerClientError(
                f"Unsupported NASA POWER temporal '{temporal}'.",
                category="configuration",
                hint=f"Allowed: {', '.join(self.VALID_TEMPORAL)}.",
            )
        if not parameters:
            raise NasaPowerClientError(
                "At least one NASA POWER parameter is required.",
                category="configuration",
                hint="Provide POWER variable codes such as T2M or PRECTOTCORR.",
            )

        query = urlencode(
            {
                "parameters": ",".join(parameters),
                "community": community,
                "longitude": longitude,
                "latitude": latitude,
                "start": start,
                "end": end,
                "format": "JSON",
            }
        )
        url = f"{self.base_url}/api/temporal/{temporal_clean}/point?{query}"
        return self._request_json(
            url,
            connection_error_prefix=(
                f"Could not connect to NASA POWER endpoint '{self.base_url}'"
            ),
        )

    def _request_json(
        self,
        url: str,
        *,
        connection_error_prefix: str,
    ) -> Dict[str, object]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "guaraci/0.5.2",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_bytes = response.read()
                content_type = str(response.headers.get("Content-Type", "")).lower()
                payload = self._decode_json_payload(
                    raw_bytes, content_type=content_type
                )
        except HTTPError as exc:
            message = self._extract_http_error_message(exc)
            category, retryable, hint = self._classify_http_error(exc.code)
            raise NasaPowerClientError(
                f"NASA POWER request failed ({exc.code}): {message}",
                category=category,
                retryable=retryable,
                hint=hint,
            ) from exc
        except URLError as exc:
            category, hint = self._classify_url_error_reason(exc.reason)
            raise NasaPowerClientError(
                f"{connection_error_prefix}: {exc.reason}",
                category=category,
                retryable=True,
                hint=hint,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NasaPowerClientError(
                f"{connection_error_prefix}: request timed out after "
                f"{self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint=(
                    "Retry with a narrower date window if the upstream service "
                    "remains slow."
                ),
            ) from exc

        if not isinstance(payload, dict):
            raise NasaPowerClientError(
                "Unexpected NASA POWER response format.",
                category="response_format",
                hint="The upstream endpoint should return a JSON object payload.",
            )
        return payload

    @staticmethod
    def _decode_json_payload(
        raw_bytes: bytes, *, content_type: str
    ) -> Dict[str, Any]:
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw_bytes.decode("utf-8", errors="replace")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            sample = text.strip().replace("\n", " ")[:220]
            message = (
                "NASA POWER returned a non-JSON response. "
                f"Content-Type: '{content_type or 'unknown'}'. "
                f"Body snippet: '{sample}'."
                if sample
                else (
                    "NASA POWER returned an empty or non-JSON response. "
                    f"Content-Type: '{content_type or 'unknown'}'."
                )
            )
            raise NasaPowerClientError(
                message,
                category="response_format",
                hint=(
                    "Check the base URL; valid endpoint is "
                    "https://power.larc.nasa.gov/api/temporal/."
                ),
            ) from exc

        if not isinstance(payload, Mapping):
            raise NasaPowerClientError(
                "Unexpected NASA POWER response format.",
                category="response_format",
                hint="The upstream endpoint should return a JSON object payload.",
            )
        return dict(payload)

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        if code in {400, 422}:
            return (
                "configuration",
                False,
                "Check parameters, latitude/longitude ranges, the date window, "
                "and the temporal resolution.",
            )
        if code == 404:
            return (
                "configuration",
                False,
                "Check the base URL and temporal path (daily or monthly).",
            )
        if code in {408, 429} or 500 <= code <= 599:
            return (
                "http_error",
                True,
                "Retry later or reduce the query window if NASA POWER is busy.",
            )
        return (
            "http_error",
            False,
            "Check request parameters and endpoint compatibility before retrying.",
        )

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return (
                "timeout",
                "Retry with a narrower date window if the service remains slow.",
            )
        return (
            "connectivity",
            "Check internet access, DNS resolution, and firewall/proxy rules "
            "before retrying.",
        )

    @staticmethod
    def _extract_http_error_message(exc: HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            return "unknown error"
        if not raw.strip():
            return "unknown error"
        try:
            payload = json.loads(raw)
        except Exception:
            return raw.strip()
        if isinstance(payload, Mapping):
            messages = payload.get("messages")
            if isinstance(messages, list) and messages:
                return "; ".join(str(item) for item in messages if item)
            detail = payload.get("detail") or payload.get("error")
            if detail:
                return str(detail)
        return raw.strip()


class NasaFirmsClientError(RuntimeError):
    """Raised when NASA FIRMS API operations fail."""

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
        super().__init__(self._compose_message())

    def _compose_message(self) -> str:
        if not self.hint:
            return self.message
        return f"{self.message} Hint: {self.hint}"

    def with_context(self, context: str) -> "NasaFirmsClientError":
        context_text = str(context).strip()
        if not context_text:
            return self
        return NasaFirmsClientError(
            f"{context_text}. {self.message}",
            category=self.category,
            retryable=self.retryable,
            hint=self.hint,
        )


class NasaFirmsClient:
    """Minimal client for the NASA FIRMS active-fire CSV endpoints.

    FIRMS requires a free ``MAP_KEY`` that is embedded in the request path. The
    key is treated as a secret: it is never logged or echoed, and any error
    message derived from the request URL has the key redacted.
    """

    DEFAULT_BASE_URL = "https://firms.modaps.eosdis.nasa.gov"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("NASA FIRMS base URL cannot be empty.")
        self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))

    def fetch_area_csv(
        self,
        *,
        map_key: str,
        source: str,
        area: str,
        day_range: int,
        date: str,
    ) -> str:
        """Fetch an area (bounding-box or ``world``) CSV extract."""
        url = (
            f"{self.base_url}/api/area/csv/{quote(map_key, safe='')}/"
            f"{quote(source, safe='')}/{quote(area, safe='')}/"
            f"{int(day_range)}/{quote(date, safe='')}"
        )
        return self._request_text(url, secret=map_key)

    def fetch_country_csv(
        self,
        *,
        map_key: str,
        source: str,
        country: str,
        day_range: int,
        date: str,
    ) -> str:
        """Fetch a country-code CSV extract (for example ``BRA``)."""
        url = (
            f"{self.base_url}/api/country/csv/{quote(map_key, safe='')}/"
            f"{quote(source, safe='')}/{quote(country, safe='')}/"
            f"{int(day_range)}/{quote(date, safe='')}"
        )
        return self._request_text(url, secret=map_key)

    def _request_text(self, url: str, *, secret: str) -> str:
        request = Request(
            url,
            headers={
                "Accept": "text/csv",
                "User-Agent": "guaraci/0.5.2",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_bytes = response.read()
        except HTTPError as exc:
            message = self._redact(self._extract_http_error_message(exc), secret)
            category, retryable, hint = self._classify_http_error(exc.code)
            raise NasaFirmsClientError(
                f"NASA FIRMS request failed ({exc.code}): {message}",
                category=category,
                retryable=retryable,
                hint=hint,
            ) from exc
        except URLError as exc:
            category, hint = self._classify_url_error_reason(exc.reason)
            raise NasaFirmsClientError(
                f"Could not connect to NASA FIRMS endpoint '{self.base_url}': "
                f"{self._redact(str(exc.reason), secret)}",
                category=category,
                retryable=True,
                hint=hint,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NasaFirmsClientError(
                f"NASA FIRMS request timed out after {self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint="Retry with a narrower date window if the service is slow.",
            ) from exc

        try:
            return raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw_bytes.decode("utf-8", errors="replace")

    @staticmethod
    def _redact(text: str, secret: str) -> str:
        if secret and secret in text:
            return text.replace(secret, "***")
        return text

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        if code in {400, 401, 403}:
            return (
                "configuration",
                False,
                "Check the MAP_KEY (GUARACI_FIRMS_MAP_KEY), source, and area or "
                "country code.",
            )
        if code == 404:
            return (
                "configuration",
                False,
                "Check the base URL, source product, and endpoint family.",
            )
        if code in {408, 429} or 500 <= code <= 599:
            return (
                "http_error",
                True,
                "Retry later; FIRMS rate-limits MAP_KEYs and may be busy.",
            )
        return (
            "http_error",
            False,
            "Check request parameters and endpoint compatibility before retrying.",
        )

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return (
                "timeout",
                "Retry with a narrower date window if the service remains slow.",
            )
        return (
            "connectivity",
            "Check internet access, DNS resolution, and firewall/proxy rules.",
        )

    @staticmethod
    def _extract_http_error_message(exc: HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            return "unknown error"
        return raw.strip() or "unknown error"
