"""HTTP clients for NASA APIs (POWER, FIRMS, GES DISC).

NASA POWER (https://power.larc.nasa.gov) is an open, keyless REST service;
FIRMS uses a MAP_KEY embedded in the path; GES DISC uses an Earthdata Login
bearer token. All three share the request/decode/classify/retry
infrastructure from :mod:`guaraci.core.http` and the error taxonomy
(category / retryable / hint) used by the jobs layer.
"""

from __future__ import annotations

import http.cookiejar
import json
from http.client import HTTPMessage
from typing import IO, Dict, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
    urlopen,
)

from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    decode_json_mapping,
    decode_text,
    is_timeout_reason,
    open_response,
    read_http_error_body,
    request_with_retry,
)


class NasaPowerClientError(ApiClientError):
    """Raised when NASA POWER API operations fail."""


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
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("NASA POWER base URL cannot be empty.")
        self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

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
                "User-Agent": "guaraci/0.6.0",
            },
        )

        def on_http_error(exc: HTTPError) -> NasaPowerClientError:
            message = self._extract_http_error_message(exc)
            category, retryable, hint = self._classify_http_error(exc.code)
            return NasaPowerClientError(
                f"NASA POWER request failed ({exc.code}): {message}",
                category=category,
                retryable=retryable,
                hint=hint,
            )

        def on_url_error(exc: URLError) -> NasaPowerClientError:
            category, hint = self._classify_url_error_reason(exc.reason)
            return NasaPowerClientError(
                f"{connection_error_prefix}: {exc.reason}",
                category=category,
                retryable=True,
                hint=hint,
            )

        def on_timeout(exc: Exception) -> NasaPowerClientError:
            return NasaPowerClientError(
                f"{connection_error_prefix}: request timed out after "
                f"{self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint=(
                    "Retry with a narrower date window if the upstream service "
                    "remains slow."
                ),
            )

        def send() -> Dict[str, object]:
            raw_bytes, headers = open_response(
                lambda req, timeout: urlopen(req, timeout=timeout),
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            content_type = ""
            if headers is not None:
                content_type = str(headers.get("Content-Type", "")).lower()
            return self._decode_json_payload(raw_bytes, content_type=content_type)

        return request_with_retry(send, max_attempts=self.max_attempts)

    @staticmethod
    def _decode_json_payload(raw_bytes: bytes, *, content_type: str) -> Dict[str, object]:
        return decode_json_mapping(
            raw_bytes,
            content_type=content_type,
            error_cls=NasaPowerClientError,
            service_label="NASA POWER",
            non_json_hint=(
                "Check the base URL; valid endpoint is "
                "https://power.larc.nasa.gov/api/temporal/."
            ),
        )

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        category, retryable = classify_http_status(
            code, configuration_codes=frozenset({400, 404, 422})
        )
        if code in {400, 422}:
            hint = (
                "Check parameters, latitude/longitude ranges, the date window, "
                "and the temporal resolution."
            )
        elif code == 404:
            hint = "Check the base URL and temporal path (daily or monthly)."
        elif retryable:
            hint = "Retry later or reduce the query window if NASA POWER is busy."
        else:
            hint = "Check request parameters and endpoint compatibility before retrying."
        return category, retryable, hint

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if is_timeout_reason(reason):
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
        raw = read_http_error_body(exc)
        if raw == "unknown error":
            return raw
        try:
            payload = json.loads(raw)
        except Exception:
            return raw
        if isinstance(payload, Mapping):
            messages = payload.get("messages")
            if isinstance(messages, list) and messages:
                return "; ".join(str(item) for item in messages if item)
            detail = payload.get("detail") or payload.get("error")
            if detail:
                return str(detail)
        return raw


class NasaFirmsClientError(ApiClientError):
    """Raised when NASA FIRMS API operations fail."""


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
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("NASA FIRMS base URL cannot be empty.")
        self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

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
                "User-Agent": "guaraci/0.6.0",
            },
        )

        def on_http_error(exc: HTTPError) -> NasaFirmsClientError:
            message = self._redact(self._extract_http_error_message(exc), secret)
            category, retryable, hint = self._classify_http_error(exc.code)
            return NasaFirmsClientError(
                f"NASA FIRMS request failed ({exc.code}): {message}",
                category=category,
                retryable=retryable,
                hint=hint,
            )

        def on_url_error(exc: URLError) -> NasaFirmsClientError:
            category, hint = self._classify_url_error_reason(exc.reason)
            return NasaFirmsClientError(
                f"Could not connect to NASA FIRMS endpoint '{self.base_url}': "
                f"{self._redact(str(exc.reason), secret)}",
                category=category,
                retryable=True,
                hint=hint,
            )

        def on_timeout(exc: Exception) -> NasaFirmsClientError:
            return NasaFirmsClientError(
                f"NASA FIRMS request timed out after {self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint="Retry with a narrower date window if the service is slow.",
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

    @staticmethod
    def _redact(text: str, secret: str) -> str:
        if secret and secret in text:
            return text.replace(secret, "***")
        return text

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        category, retryable = classify_http_status(
            code, configuration_codes=frozenset({400, 401, 403, 404})
        )
        if code in {400, 401, 403}:
            hint = (
                "Check the MAP_KEY (GUARACI_FIRMS_MAP_KEY), source, and area or "
                "country code."
            )
        elif code == 404:
            hint = "Check the base URL, source product, and endpoint family."
        elif retryable:
            hint = "Retry later; FIRMS rate-limits MAP_KEYs and may be busy."
        else:
            hint = "Check request parameters and endpoint compatibility before retrying."
        return category, retryable, hint

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if is_timeout_reason(reason):
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
        return read_http_error_body(exc)


class NasaGesDiscClientError(ApiClientError):
    """Raised when NASA GES DISC OPeNDAP operations fail."""


class _KeepAuthRedirectHandler(HTTPRedirectHandler):
    """Redirect handler that re-attaches the EDL bearer token.

    urllib drops the ``Authorization`` header on cross-host redirects, which
    breaks the Earthdata URS OAuth handoff. Re-adding it on each redirect lets
    the bearer token survive the GES DISC -> URS -> GES DISC chain.

    The token is only re-attached for trusted NASA Earthdata hosts; redirects
    to any other host are followed without the ``Authorization`` header so
    the secret never leaks to third parties.
    """

    _TRUSTED_HOST = "urs.earthdata.nasa.gov"
    _TRUSTED_SUFFIXES = (".earthdata.nasa.gov", ".gesdisc.eosdis.nasa.gov")

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    @classmethod
    def _is_trusted_host(cls, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if host == cls._TRUSTED_HOST:
            return True
        return host.endswith(cls._TRUSTED_SUFFIXES)

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and self._is_trusted_host(newurl):
            new.add_header("Authorization", f"Bearer {self._token}")
        return new


class NasaGesDiscClient:
    """Client for GES DISC OPeNDAP point subsetting (NASA POWER-style series).

    Uses an Earthdata Login bearer token (a secret), an OPeNDAP ``.ascii``
    constraint to extract a single grid cell (no HDF5/NetCDF parsing, no heavy
    dependency), and a redirect-preserving opener for the URS OAuth handoff.
    """

    DEFAULT_BASE_URL = "https://gpm1.gesdisc.eosdis.nasa.gov"

    def __init__(
        self,
        *,
        token: str,
        base_url: str | None = None,
        timeout_seconds: int = 120,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        clean = str(token).strip()
        if not clean:
            raise ValueError("NASA GES DISC bearer token cannot be empty.")
        self._token = clean
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("NASA GES DISC base URL cannot be empty.")
        self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self._opener = build_opener(
            _KeepAuthRedirectHandler(self._token),
            HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def fetch_ascii(self, dataset_path: str, constraint: str) -> str:
        """Fetch an OPeNDAP ``.ascii`` subset for one dataset granule.

        ``dataset_path`` is the OPeNDAP path of the granule (without the
        response suffix); ``constraint`` is the projection such as
        ``precipitation[0][1333][664]``.
        """
        path = "/" + dataset_path.lstrip("/")
        url = f"{self.base_url}{path}.ascii?{constraint}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "text/plain",
                "User-Agent": "guaraci/0.6.0",
            },
        )

        def on_http_error(exc: HTTPError) -> NasaGesDiscClientError:
            category, retryable, hint = self._classify_http_error(exc.code)
            return NasaGesDiscClientError(
                f"NASA GES DISC request failed ({exc.code}).",
                category=category,
                retryable=retryable,
                hint=hint,
            )

        def on_url_error(exc: URLError) -> NasaGesDiscClientError:
            return NasaGesDiscClientError(
                f"Could not connect to NASA GES DISC endpoint '{self.base_url}': "
                f"{self._redact(str(exc.reason))}",
                category="connectivity",
                retryable=True,
                hint="Check internet access, DNS, and firewall/proxy rules.",
            )

        def on_timeout(exc: Exception) -> NasaGesDiscClientError:
            return NasaGesDiscClientError(
                f"NASA GES DISC request timed out after {self.timeout_seconds}s",
                category="timeout",
                retryable=True,
                hint="Retry with a narrower date window if the service is slow.",
            )

        def send() -> bytes:
            raw_bytes, _headers = open_response(
                self._opener.open,
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            return raw_bytes

        raw = request_with_retry(send, max_attempts=self.max_attempts)

        text = raw.decode("utf-8", errors="replace")
        if not text.lstrip().lower().startswith("dataset:"):
            snippet = self._redact(text.strip().replace("\n", " ")[:200])
            raise NasaGesDiscClientError(
                f"NASA GES DISC returned an unexpected (non-OPeNDAP) response: "
                f"'{snippet}'.",
                category="response_format",
                hint=(
                    "If this is an authorization page, authorize the 'NASA GESDISC "
                    "DATA ARCHIVE' application in your Earthdata profile."
                ),
            )
        return text

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        category, retryable = classify_http_status(
            code, configuration_codes=frozenset({401, 403, 404})
        )
        if code in {401, 403}:
            hint = (
                "Authorize the 'NASA GESDISC DATA ARCHIVE' application in your "
                "Earthdata profile (urs.earthdata.nasa.gov -> Applications -> "
                "Authorized Apps) and verify GUARACI_EARTHDATA_TOKEN is valid."
            )
        elif code == 404:
            hint = (
                "Check the product, date, and granule path (the granule may not "
                "exist for that date or version)."
            )
        elif retryable:
            hint = "Retry later; GES DISC may be busy."
        else:
            hint = "Check request parameters and endpoint compatibility before retrying."
        return category, retryable, hint
