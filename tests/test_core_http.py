"""Tests for the shared HTTP infrastructure (guaraci.core.http)."""

from __future__ import annotations

import io
from urllib.error import HTTPError, URLError

import pytest

from guaraci.core.http import (
    ApiClientError,
    backoff_delay,
    classify_http_status,
    open_response,
    parse_retry_after,
    request_with_retry,
)


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _error(code: int, headers: dict | None = None) -> HTTPError:
    return HTTPError("http://x", code, "boom", headers, io.BytesIO(b""))


def _translate(exc: HTTPError) -> ApiClientError:
    category, retryable = classify_http_status(exc.code)
    return ApiClientError(
        f"failed ({exc.code})", category=category, retryable=retryable
    )


def _open_once(open_fn):
    return open_response(
        open_fn,
        object(),
        timeout=5,
        on_http_error=_translate,
        on_url_error=lambda exc: ApiClientError(
            "conn", category="connectivity", retryable=True
        ),
        on_timeout=lambda exc: ApiClientError(
            "slow", category="timeout", retryable=True
        ),
    )


# ---------------------------------------------------------------- retry loop


def test_retryable_error_succeeds_on_second_attempt() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def send() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ApiClientError("try again", retryable=True)
        return "ok"

    result = request_with_retry(
        send, max_attempts=3, backoff_seconds=0.25, sleep=sleeps.append
    )
    assert result == "ok"
    assert calls["n"] == 2
    assert sleeps == [0.25]  # backoff * 2**0, no second sleep after success


def test_non_retryable_error_is_not_retried() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def send() -> str:
        calls["n"] += 1
        raise ApiClientError("bad config", category="configuration", retryable=False)

    with pytest.raises(ApiClientError):
        request_with_retry(send, max_attempts=3, sleep=sleeps.append)
    assert calls["n"] == 1
    assert sleeps == []


def test_retry_exhaustion_raises_last_error_with_exponential_backoff() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def send() -> str:
        calls["n"] += 1
        raise ApiClientError("busy", retryable=True)

    with pytest.raises(ApiClientError) as excinfo:
        request_with_retry(
            send, max_attempts=3, backoff_seconds=0.5, sleep=sleeps.append
        )
    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]  # 0.5 * 2**0, 0.5 * 2**1
    assert excinfo.value.retryable is True


def test_retry_honors_retry_after_header() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def open_fn(request, timeout):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            raise _error(429, headers={"Retry-After": "7"})
        return _FakeResponse(b"payload")

    def send() -> bytes:
        raw, _headers = _open_once(open_fn)
        return raw

    result = request_with_retry(send, max_attempts=3, sleep=sleeps.append)
    assert result == b"payload"
    assert sleeps == [7.0]  # Retry-After wins over exponential backoff


def test_retry_after_is_capped() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def send() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            err = ApiClientError("throttled", retryable=True)
            err.retry_after = 9999.0
            raise err
        return "ok"

    request_with_retry(
        send, max_attempts=3, backoff_cap_seconds=30.0, sleep=sleeps.append
    )
    assert sleeps == [30.0]


def test_backoff_delay_is_capped() -> None:
    assert backoff_delay(10, backoff_seconds=1.0, backoff_cap_seconds=30.0) == 30.0


# ------------------------------------------------------------ classification


def test_404_is_configuration_and_not_retryable() -> None:
    with pytest.raises(ApiClientError) as excinfo:
        _open_once(lambda request, timeout: (_ for _ in ()).throw(_error(404)))
    assert excinfo.value.category == "configuration"
    assert excinfo.value.retryable is False


def test_429_is_retryable_http_error() -> None:
    with pytest.raises(ApiClientError) as excinfo:
        _open_once(lambda request, timeout: (_ for _ in ()).throw(_error(429)))
    assert excinfo.value.category == "http_error"
    assert excinfo.value.retryable is True


def test_500_is_retryable_http_error() -> None:
    with pytest.raises(ApiClientError) as excinfo:
        _open_once(lambda request, timeout: (_ for _ in ()).throw(_error(500)))
    assert excinfo.value.category == "http_error"
    assert excinfo.value.retryable is True


def test_url_error_maps_to_connectivity() -> None:
    def open_fn(request, timeout):  # noqa: ANN001, ARG001
        raise URLError("dns down")

    with pytest.raises(ApiClientError) as excinfo:
        _open_once(open_fn)
    assert excinfo.value.category == "connectivity"
    assert excinfo.value.retryable is True


# ---------------------------------------------------------------- retry-after


def test_parse_retry_after_variants() -> None:
    assert parse_retry_after({"Retry-After": "3"}) == 3.0
    assert parse_retry_after({"Retry-After": "0"}) == 0.0
    assert parse_retry_after({"Retry-After": "-5"}) is None
    assert parse_retry_after({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
    assert parse_retry_after({}) is None
    assert parse_retry_after(None) is None


def test_http_error_without_headers_yields_no_retry_after() -> None:
    with pytest.raises(ApiClientError) as excinfo:
        _open_once(lambda request, timeout: (_ for _ in ()).throw(_error(503, None)))
    assert excinfo.value.retry_after is None
    assert excinfo.value.retryable is True


# -------------------------------------------------------------- error contract


def test_with_context_preserves_subclass_and_fields() -> None:
    class MyError(ApiClientError):
        pass

    base = MyError("boom", category="timeout", retryable=True, hint="h")
    wrapped = base.with_context("while doing x")
    assert type(wrapped) is MyError
    assert str(wrapped).startswith("while doing x. boom")
    assert wrapped.category == "timeout"
    assert wrapped.retryable is True
    assert wrapped.hint == "h"
