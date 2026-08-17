"""Shared HTTP infrastructure for guaraci API clients.

Consolidates the request/decode/classify trio that used to be copied across
the OpenDataSUS, NASA (POWER, FIRMS, GES DISC), and IBGE clients, and adds a
real retry loop with exponential backoff so every client gains retries at
once.

Design notes:

- :class:`ApiClientError` carries the shared error contract (``category`` /
  ``retryable`` / ``hint`` / ``with_context``) used by the jobs layer to
  classify failures consistently. Client-specific exceptions subclass it.
- :func:`open_response` performs ONE attempt and translates urllib errors
  into ``ApiClientError`` instances via client-supplied callbacks (so each
  client keeps its own messages, hints, and secret redaction).
- :func:`request_with_retry` wraps an attempt callable and retries only when
  the raised error is ``retryable``, honouring ``Retry-After`` when the
  upstream provided it, with deterministic exponential backoff otherwise.
- Clients pass an ``open_fn`` callable resolved at call time (for example a
  lambda over the module-level ``urlopen``), which keeps existing
  ``monkeypatch.setattr("guaraci.<mod>.client.urlopen", ...)`` tests working.
"""

from __future__ import annotations

import json
import socket
import time
from typing import Any, Callable, Mapping, Tuple, Type, TypeVar
from urllib.error import HTTPError, URLError

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.25
DEFAULT_BACKOFF_CAP_SECONDS = 30.0

_T = TypeVar("_T")


class ApiClientError(RuntimeError):
    """Base error for guaraci HTTP API clients.

    Carries the shared taxonomy (``category`` / ``retryable`` / ``hint``)
    used by the jobs layer. ``retry_after`` is attached by the request path
    when the upstream sent a usable ``Retry-After`` header.
    """

    retry_after: float | None = None

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

    def with_context(self, context: str) -> "ApiClientError":
        context_text = str(context).strip()
        if not context_text:
            return self
        return type(self)(
            f"{context_text}. {self.message}",
            category=self.category,
            retryable=self.retryable,
            hint=self.hint,
        )


def is_retryable_status(code: int) -> bool:
    """Transient HTTP statuses: timeout, throttling, and server errors."""
    return code in {408, 429} or 500 <= code <= 599


def classify_http_status(
    code: int,
    *,
    configuration_codes: frozenset[int] = frozenset({404}),
) -> Tuple[str, bool]:
    """Map an HTTP status to the shared ``(category, retryable)`` pair.

    ``configuration_codes`` lists statuses the client considers caller
    misconfiguration (always non-retryable); 404 is one for every client.
    """
    if code in configuration_codes:
        return "configuration", False
    if is_retryable_status(code):
        return "http_error", True
    return "http_error", False


def is_timeout_reason(reason: object) -> bool:
    """True when a ``URLError`` reason is a socket-level timeout."""
    return isinstance(reason, (TimeoutError, socket.timeout))


def parse_retry_after(headers: Any) -> float | None:
    """Extract ``Retry-After`` seconds from response/error headers.

    Only the delta-seconds form is honoured; the HTTP-date form (and any
    absent or malformed value) yields ``None`` so backoff applies instead.
    """
    if headers is None:
        return None
    try:
        value = headers.get("Retry-After")
    except Exception:
        return None
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return seconds


def backoff_delay(
    attempt: int,
    *,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    backoff_cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS,
) -> float:
    """Deterministic exponential backoff: ``backoff * 2**attempt``, capped."""
    return min(backoff_cap_seconds, backoff_seconds * (2 ** max(0, attempt)))


def request_with_retry(
    send: Callable[[], _T],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    backoff_cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> _T:
    """Run ``send`` with retries for retryable :class:`ApiClientError`.

    Non-retryable errors propagate immediately (no retry, no sleep). When the
    error carries ``retry_after`` (from a ``Retry-After`` header) that delay
    is used, still capped by ``backoff_cap_seconds``.
    """
    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        try:
            return send()
        except ApiClientError as exc:
            if not exc.retryable or attempt >= attempts - 1:
                raise
            if exc.retry_after is not None:
                delay = exc.retry_after
            else:
                delay = backoff_delay(
                    attempt,
                    backoff_seconds=backoff_seconds,
                    backoff_cap_seconds=backoff_cap_seconds,
                )
            sleep(min(delay, backoff_cap_seconds))
    raise AssertionError("unreachable: retry loop always returns or raises")


def open_response(
    open_fn: Callable[..., Any],
    request: Any,
    *,
    timeout: float,
    on_http_error: Callable[[HTTPError], ApiClientError],
    on_url_error: Callable[[URLError], ApiClientError],
    on_timeout: Callable[[Exception], ApiClientError],
) -> Tuple[bytes, Any]:
    """Perform ONE request attempt and return ``(body_bytes, headers)``.

    urllib errors are translated through the client-supplied callbacks so
    each client controls messages, hints, and redaction. Retryable HTTP
    errors get ``retry_after`` attached from the ``Retry-After`` header.
    """
    try:
        with open_fn(request, timeout=timeout) as response:
            raw_bytes: bytes = response.read()
            headers = getattr(response, "headers", None)
            return raw_bytes, headers
    except HTTPError as exc:
        error = on_http_error(exc)
        if error.retryable and error.retry_after is None:
            error.retry_after = parse_retry_after(getattr(exc, "headers", None))
        raise error from exc
    except URLError as exc:
        raise on_url_error(exc) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise on_timeout(exc) from exc


def decode_text(raw_bytes: bytes) -> str:
    """Decode bytes as UTF-8 (BOM-tolerant) with a lossy fallback."""
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw_bytes.decode("utf-8", errors="replace")


def decode_json_mapping(
    raw_bytes: bytes,
    *,
    content_type: str,
    error_cls: Type[ApiClientError],
    service_label: str,
    non_json_hint: str,
    non_json_trailer: str = "",
) -> dict[str, Any]:
    """Defensively decode a JSON object payload, or raise ``error_cls``.

    Non-JSON bodies produce a ``response_format`` error quoting a short body
    snippet; JSON payloads that are not objects produce the shared
    "Unexpected ... response format." error.
    """
    text = decode_text(raw_bytes)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        sample = text.strip().replace("\n", " ")[:220]
        if sample:
            message = (
                f"{service_label} returned a non-JSON response. "
                f"Content-Type: '{content_type or 'unknown'}'. "
                f"Body snippet: '{sample}'.{non_json_trailer}"
            )
        else:
            message = (
                f"{service_label} returned an empty or non-JSON response. "
                f"Content-Type: '{content_type or 'unknown'}'."
                f"{non_json_trailer}"
            )
        raise error_cls(
            message,
            category="response_format",
            hint=non_json_hint,
        ) from exc

    if not isinstance(payload, Mapping):
        raise error_cls(
            f"Unexpected {service_label} response format.",
            category="response_format",
            hint="The upstream endpoint should return a JSON object payload.",
        )
    return dict(payload)


def read_http_error_body(exc: HTTPError) -> str:
    """Read an ``HTTPError`` body as trimmed text, never raising."""
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return "unknown error"
    return raw.strip() or "unknown error"
