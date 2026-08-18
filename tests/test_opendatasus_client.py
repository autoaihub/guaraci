"""Tests for OpenDataSUS HTTP client error classification."""

from __future__ import annotations

import io
from urllib.error import HTTPError, URLError

import pytest

from guaraci.opendatasus.client import OpenDataSUSClient, OpenDataSUSClientError


def test_ckan_mode_is_deactivated_with_a_clear_error() -> None:
    """CKAN host ('ckan-dadosabertos.saude.gov.br') is confirmed dead (DNS
    failure, verified live 2026-08-17/2026-08-18) and has no replacement.
    Constructing a client with a CKAN-shaped base_url must fail fast and
    explain why, instead of the caller hitting an opaque DNS error later.
    """
    with pytest.raises(OpenDataSUSClientError) as excinfo:
        OpenDataSUSClient(base_url=OpenDataSUSClient.DEFAULT_CKAN_BASE_URL)

    error = excinfo.value
    assert error.category == "configuration"
    assert error.retryable is False
    assert "deactivated" in str(error).lower()
    assert "demas" in (error.hint or "").lower()
    # ApiClientError subclasses RuntimeError — a caller catching plain
    # RuntimeError (not knowing about the OpenDataSUS-specific subclass)
    # still gets a real explanation, not a bare DNS traceback.
    assert isinstance(error, RuntimeError)


def test_decode_json_payload_non_json_is_classified_with_hint() -> None:
    with pytest.raises(OpenDataSUSClientError) as excinfo:
        OpenDataSUSClient._decode_json_payload(
            b"<html>temporary upstream page</html>",
            content_type="text/html",
        )

    error = excinfo.value
    assert error.category == "response_format"
    assert error.retryable is False
    assert "non-json response" in str(error).lower()
    assert "valid endpoints are ckan" in str(error).lower()


def test_request_json_http_503_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenDataSUSClient()

    def fake_urlopen(request, timeout):  # noqa: ANN001, ARG001
        raise HTTPError(
            url=request.full_url,
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(b'{"error": {"message": "temporarily unavailable"}}'),
        )

    monkeypatch.setattr("guaraci.opendatasus.client.urlopen", fake_urlopen)

    with pytest.raises(OpenDataSUSClientError) as excinfo:
        client._request_json(
            "https://apidadosabertos.saude.gov.br/test",
            connection_error_prefix="Could not connect",
        )

    error = excinfo.value
    assert error.category == "http_error"
    assert error.retryable is True
    assert "503" in str(error)
    assert "retry later" in str(error).lower()


def test_request_json_urlerror_is_retryable_connectivity_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OpenDataSUSClient()

    def fake_urlopen(request, timeout):  # noqa: ANN001, ARG001
        raise URLError("temporary dns failure")

    monkeypatch.setattr("guaraci.opendatasus.client.urlopen", fake_urlopen)

    with pytest.raises(OpenDataSUSClientError) as excinfo:
        client._request_json(
            "https://apidadosabertos.saude.gov.br/test",
            connection_error_prefix="Could not connect",
        )

    error = excinfo.value
    assert error.category == "connectivity"
    assert error.retryable is True
    assert "dns" in str(error).lower()

