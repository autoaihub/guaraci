"""HTTP client helpers for OpenDataSUS APIs (CKAN and DEMAS)."""

from __future__ import annotations

import json
from typing import Any
from typing import Dict, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    decode_json_mapping,
    is_timeout_reason,
    open_response,
    read_http_error_body,
    request_with_retry,
)


class OpenDataSUSClientError(ApiClientError):
    """Raised when OpenDataSUS API operations fail."""


class OpenDataSUSClient:
    """Minimal client for OpenDataSUS endpoints (CKAN or DEMAS)."""

    DEFAULT_BASE_URL = "https://apidadosabertos.saude.gov.br"
    DEFAULT_CKAN_BASE_URL = "https://ckan-dadosabertos.saude.gov.br/api/3/action"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 60,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected_url:
            raise ValueError("OpenDataSUS base URL cannot be empty.")
        self.mode = "ckan" if "/api/3/action" in selected_url.lower() else "demas"
        parsed = urlparse(selected_url)
        if self.mode == "demas" and parsed.scheme and parsed.netloc:
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self.base_url = selected_url
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

    def package_show(self, package_id: str) -> Dict[str, object]:
        """Fetch one package metadata payload."""
        if self.mode != "ckan":
            raise OpenDataSUSClientError(
                "package_show is only supported for CKAN endpoints "
                "(use api_base_url ending with /api/3/action).",
                category="configuration",
                hint="Use api_base_url='https://ckan-dadosabertos.saude.gov.br/api/3/action'.",
            )
        return self._call("package_show", {"id": package_id})

    def datastore_search_sql(self, sql: str) -> Dict[str, object]:
        """Run SQL queries against datastore resources."""
        if self.mode != "ckan":
            raise OpenDataSUSClientError(
                "datastore_search_sql is only supported for CKAN endpoints "
                "(use api_base_url ending with /api/3/action).",
                category="configuration",
                hint="Use api_base_url='https://ckan-dadosabertos.saude.gov.br/api/3/action'.",
            )
        return self._call("datastore_search_sql", {"sql": sql})

    def demas_get(self, path: str, params: Mapping[str, object] | None = None) -> Dict[str, object]:
        """Run GET requests against apiDadosAbertos (DEMAS) JSON endpoints."""
        if self.mode != "demas":
            raise OpenDataSUSClientError(
                "DEMAS API calls require api_base_url without /api/3/action.",
                category="configuration",
                hint="Use api_base_url='https://apidadosabertos.saude.gov.br'.",
            )
        query = urlencode(
            {key: str(value) for key, value in (params or {}).items() if value is not None},
            doseq=True,
        )
        normalized_path = "/" + path.lstrip("/")
        url = f"{self.base_url}{normalized_path}"
        if query:
            url = f"{url}?{query}"
        return self._request_json(
            url,
            connection_error_prefix=(
                f"Could not connect to OpenDataSUS endpoint '{self.base_url}'"
            ),
        )

    def _call(self, action: str, params: Mapping[str, object]) -> Dict[str, object]:
        encoded = urlencode({key: str(value) for key, value in params.items()}, doseq=True)
        url = f"{self.base_url}/{action}?{encoded}"
        payload = self._request_json(
            url,
            connection_error_prefix=(
                f"Could not connect to OpenDataSUS endpoint '{self.base_url}'"
            ),
        )

        if not isinstance(payload, Mapping):
            raise OpenDataSUSClientError(
                "Unexpected OpenDataSUS response format.",
                category="response_format",
                hint="The upstream endpoint should return a JSON object payload.",
            )

        success = bool(payload.get("success"))
        if not success:
            error_message = self._extract_api_error(payload)
            raise OpenDataSUSClientError(
                error_message,
                category="upstream_api",
                hint=(
                    "Check whether the selected endpoint, filters, and API mode "
                    "(CKAN or DEMAS) are compatible."
                ),
            )

        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise OpenDataSUSClientError(
                "OpenDataSUS response missing result payload.",
                category="response_format",
                hint="The CKAN action succeeded flag was true, but no result object was returned.",
            )
        return dict(result)

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

        def on_http_error(exc: HTTPError) -> OpenDataSUSClientError:
            message = self._extract_http_error_message(exc)
            category, retryable, hint = self._classify_http_error(exc.code)
            return OpenDataSUSClientError(
                f"OpenDataSUS request failed ({exc.code}): {message}",
                category=category,
                retryable=retryable,
                hint=hint,
            )

        def on_url_error(exc: URLError) -> OpenDataSUSClientError:
            category, hint = self._classify_url_error_reason(exc.reason)
            return OpenDataSUSClientError(
                f"{connection_error_prefix}: {exc.reason}",
                category=category,
                retryable=True,
                hint=hint,
            )

        def on_timeout(exc: Exception) -> OpenDataSUSClientError:
            return OpenDataSUSClientError(
                f"{connection_error_prefix}: request timed out after {self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint=(
                    "Retry with a narrower date window or a lower volume request if the "
                    "upstream service remains slow."
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
    def _decode_json_payload(raw_bytes: bytes, *, content_type: str) -> Dict[str, Any]:
        return decode_json_mapping(
            raw_bytes,
            content_type=content_type,
            error_cls=OpenDataSUSClientError,
            service_label="OpenDataSUS",
            non_json_trailer=" Check api_base_url and endpoint family.",
            non_json_hint=(
                "Valid endpoints are CKAN: "
                "https://ckan-dadosabertos.saude.gov.br/api/3/action ; "
                "DEMAS: https://apidadosabertos.saude.gov.br"
            ),
        )

    @staticmethod
    def _extract_api_error(payload: Mapping[str, object]) -> str:
        error = payload.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if message:
                return f"OpenDataSUS API error: {message}"
            error_type = error.get("__type")
            if error_type:
                return f"OpenDataSUS API error: {error_type}"
        if isinstance(error, list):
            normalized = ", ".join(str(item) for item in error if item)
            if normalized:
                return f"OpenDataSUS API error: {normalized}"
        if error:
            return f"OpenDataSUS API error: {error}"
        return "OpenDataSUS API returned an unsuccessful response."

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        category, retryable = classify_http_status(code)
        if code == 404:
            hint = (
                "Check api_base_url, dataset path, resource_id, and whether "
                "CKAN/DEMAS mode matches the request."
            )
        elif retryable:
            hint = (
                "Retry later, reduce the query window, or lower request volume "
                "if the upstream service is unstable."
            )
        elif code in {401, 403}:
            hint = (
                "Check upstream access rules, corporate network restrictions, "
                "or endpoint availability."
            )
        else:
            hint = "Check request parameters and endpoint compatibility before retrying."
        return category, retryable, hint

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if is_timeout_reason(reason):
            return (
                "timeout",
                "Retry with a narrower date window or a lower volume request if the upstream service remains slow.",
            )
        return (
            "connectivity",
            "Check internet access, DNS resolution, firewall/proxy rules, and the upstream endpoint status before retrying.",
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
            error = payload.get("error")
            if isinstance(error, Mapping):
                message = error.get("message")
                if message:
                    return str(message)
        return raw
