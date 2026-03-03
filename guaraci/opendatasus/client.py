"""HTTP client helpers for OpenDataSUS APIs (CKAN and DEMAS)."""

from __future__ import annotations

import json
from typing import Any
from typing import Dict, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class OpenDataSUSClientError(RuntimeError):
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

    def package_show(self, package_id: str) -> Dict[str, object]:
        """Fetch one package metadata payload."""
        if self.mode != "ckan":
            raise OpenDataSUSClientError(
                "package_show is only supported for CKAN endpoints "
                "(use api_base_url ending with /api/3/action)."
            )
        return self._call("package_show", {"id": package_id})

    def datastore_search_sql(self, sql: str) -> Dict[str, object]:
        """Run SQL queries against datastore resources."""
        if self.mode != "ckan":
            raise OpenDataSUSClientError(
                "datastore_search_sql is only supported for CKAN endpoints "
                "(use api_base_url ending with /api/3/action)."
            )
        return self._call("datastore_search_sql", {"sql": sql})

    def demas_get(self, path: str, params: Mapping[str, object] | None = None) -> Dict[str, object]:
        """Run GET requests against apiDadosAbertos (DEMAS) JSON endpoints."""
        if self.mode != "demas":
            raise OpenDataSUSClientError(
                "DEMAS API calls require api_base_url without /api/3/action."
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
            raise OpenDataSUSClientError("Unexpected OpenDataSUS response format.")

        success = bool(payload.get("success"))
        if not success:
            error_message = self._extract_api_error(payload)
            raise OpenDataSUSClientError(error_message)

        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise OpenDataSUSClientError("OpenDataSUS response missing result payload.")
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
                "User-Agent": "guaraci/0.4.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_bytes = response.read()
                content_type = str(response.headers.get("Content-Type", "")).lower()
                payload = self._decode_json_payload(raw_bytes, content_type=content_type)
        except HTTPError as exc:
            message = self._extract_http_error_message(exc)
            raise OpenDataSUSClientError(
                f"OpenDataSUS request failed ({exc.code}): {message}"
            ) from exc
        except URLError as exc:
            raise OpenDataSUSClientError(
                f"{connection_error_prefix}: {exc.reason}"
            ) from exc

        if not isinstance(payload, dict):
            raise OpenDataSUSClientError("Unexpected OpenDataSUS response format.")
        return payload

    @staticmethod
    def _decode_json_payload(raw_bytes: bytes, *, content_type: str) -> Dict[str, Any]:
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw_bytes.decode("utf-8", errors="replace")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            sample = text.strip().replace("\n", " ")[:220]
            if sample:
                message = (
                    "OpenDataSUS returned a non-JSON response. "
                    f"Content-Type: '{content_type or 'unknown'}'. "
                    f"Body snippet: '{sample}'. "
                    "Check api_base_url. CKAN: "
                    "https://ckan-dadosabertos.saude.gov.br/api/3/action ; "
                    "DEMAS: https://apidadosabertos.saude.gov.br"
                )
            else:
                message = (
                    "OpenDataSUS returned an empty or non-JSON response. "
                    f"Content-Type: '{content_type or 'unknown'}'. "
                    "Check api_base_url (CKAN: "
                    "https://ckan-dadosabertos.saude.gov.br/api/3/action ; "
                    "DEMAS: https://apidadosabertos.saude.gov.br)."
                )
            raise OpenDataSUSClientError(message) from exc

        if not isinstance(payload, Mapping):
            raise OpenDataSUSClientError("Unexpected OpenDataSUS response format.")
        return dict(payload)

    @staticmethod
    def _extract_api_error(payload: Mapping[str, object]) -> str:
        error = payload.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if message:
                return f"OpenDataSUS API error: {message}"
        return "OpenDataSUS API returned an unsuccessful response."

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
            error = payload.get("error")
            if isinstance(error, Mapping):
                message = error.get("message")
                if message:
                    return str(message)
        return raw.strip()
