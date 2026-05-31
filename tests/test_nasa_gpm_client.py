"""Tests for the NASA GES DISC OPeNDAP client."""

from __future__ import annotations

import io
from urllib.error import HTTPError, URLError

import pytest

from guaraci.nasa.client import NasaGesDiscClient, NasaGesDiscClientError


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeOpener:
    def __init__(self, *, body: bytes | None = None, exc: Exception | None = None) -> None:
        self._body = body
        self._exc = exc
        self.last_request = None

    def open(self, request, timeout=None):  # noqa: ANN001
        self.last_request = request
        if self._exc is not None:
            raise self._exc
        return _FakeResp(self._body or b"")


_OK = (
    b"Dataset: g.nc4\n"
    b"precipitation.precipitation[precipitation.time=0][precipitation.lon=-46.65], 4.72\n"
    b"precipitation.lat, -23.55\n"
)


def test_empty_token_raises() -> None:
    with pytest.raises(ValueError):
        NasaGesDiscClient(token="   ")


def test_fetch_ascii_success() -> None:
    client = NasaGesDiscClient(token="TKN")
    client._opener = _FakeOpener(body=_OK)
    text = client.fetch_ascii("/opendap/x.nc4", "precipitation[0][1][1]")
    assert text.startswith("Dataset:")
    # request carries the bearer header and builds the .ascii URL
    req = client._opener.last_request
    assert req.full_url.endswith(".ascii?precipitation[0][1][1]")
    assert req.get_header("Authorization") == "Bearer TKN"


def test_fetch_ascii_non_opendap_response_raises() -> None:
    client = NasaGesDiscClient(token="TKN")
    client._opener = _FakeOpener(body=b"<html>401 login</html>")
    with pytest.raises(NasaGesDiscClientError) as excinfo:
        client.fetch_ascii("/opendap/x.nc4", "precipitation[0][1][1]")
    assert excinfo.value.category == "response_format"


def test_fetch_ascii_401_points_to_app_authorization() -> None:
    client = NasaGesDiscClient(token="TKN")
    client._opener = _FakeOpener(
        exc=HTTPError("http://x", 401, "Unauthorized", {}, io.BytesIO(b""))
    )
    with pytest.raises(NasaGesDiscClientError) as excinfo:
        client.fetch_ascii("/opendap/x.nc4", "precipitation[0][1][1]")
    assert excinfo.value.category == "configuration"
    assert "GESDISC DATA ARCHIVE" in str(excinfo.value)


def test_fetch_ascii_server_error_retryable() -> None:
    client = NasaGesDiscClient(token="TKN")
    client._opener = _FakeOpener(
        exc=HTTPError("http://x", 503, "Unavailable", {}, io.BytesIO(b""))
    )
    with pytest.raises(NasaGesDiscClientError) as excinfo:
        client.fetch_ascii("/opendap/x.nc4", "precipitation[0][1][1]")
    assert excinfo.value.retryable is True


def test_fetch_ascii_url_error_redacts_token() -> None:
    client = NasaGesDiscClient(token="SECRETTOKEN")
    client._opener = _FakeOpener(exc=URLError("boom SECRETTOKEN"))
    with pytest.raises(NasaGesDiscClientError) as excinfo:
        client.fetch_ascii("/opendap/x.nc4", "precipitation[0][1][1]")
    assert "SECRETTOKEN" not in str(excinfo.value)
    assert excinfo.value.category == "connectivity"


def test_with_context_preserves_fields() -> None:
    base = NasaGesDiscClientError("boom", category="configuration", hint="h")
    wrapped = base.with_context("fetching point")
    assert str(wrapped).startswith("fetching point. boom")
    assert wrapped.category == "configuration"
