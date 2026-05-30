"""Tests for the NASA POWER HTTP client."""

from __future__ import annotations

import io
import socket
from urllib.error import HTTPError, URLError

import pytest

from guaraci.nasa import client as client_mod
from guaraci.nasa.client import NasaPowerClient, NasaPowerClientError


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_default_base_url_and_timeout() -> None:
    client = NasaPowerClient()
    assert client.base_url == "https://power.larc.nasa.gov"
    assert client.timeout_seconds == 120


def test_custom_base_url_is_trimmed() -> None:
    client = NasaPowerClient(base_url="https://example.org/power/ ")
    assert client.base_url == "https://example.org/power"


def test_empty_base_url_raises() -> None:
    with pytest.raises(ValueError):
        NasaPowerClient(base_url="   ")


def test_temporal_point_rejects_unknown_temporal() -> None:
    client = NasaPowerClient()
    with pytest.raises(NasaPowerClientError) as excinfo:
        client.temporal_point(
            temporal="weekly",
            parameters=["T2M"],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )
    assert excinfo.value.category == "configuration"


def test_temporal_point_rejects_empty_parameters() -> None:
    client = NasaPowerClient()
    with pytest.raises(NasaPowerClientError):
        client.temporal_point(
            temporal="daily",
            parameters=[],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )


def test_temporal_point_builds_url_and_returns_json(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse(b'{"properties": {"parameter": {}}}')

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaPowerClient(timeout_seconds=30)
    result = client.temporal_point(
        temporal="DAILY",
        parameters=["T2M", "PRECTOTCORR"],
        latitude=-23.55,
        longitude=-46.63,
        start="20240101",
        end="20240103",
        community="AG",
    )

    assert result == {"properties": {"parameter": {}}}
    url = str(captured["url"])
    assert "/api/temporal/daily/point" in url
    assert "parameters=T2M%2CPRECTOTCORR" in url
    assert "latitude=-23.55" in url
    assert "format=JSON" in url
    assert captured["timeout"] == 30


def test_request_json_classifies_http_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(
            request.full_url,
            422,
            "Unprocessable",
            {},
            io.BytesIO(b'{"messages": ["bad parameter"]}'),
        )

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaPowerClient()
    with pytest.raises(NasaPowerClientError) as excinfo:
        client.temporal_point(
            temporal="daily",
            parameters=["T2M"],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )
    assert excinfo.value.category == "configuration"
    assert "bad parameter" in str(excinfo.value)


def test_request_json_classifies_server_error_as_retryable(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 503, "Unavailable", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaPowerClient()
    with pytest.raises(NasaPowerClientError) as excinfo:
        client.temporal_point(
            temporal="daily",
            parameters=["T2M"],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )
    assert excinfo.value.retryable is True
    assert excinfo.value.category == "http_error"


def test_request_json_classifies_connectivity_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise URLError("name resolution failed")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaPowerClient()
    with pytest.raises(NasaPowerClientError) as excinfo:
        client.temporal_point(
            temporal="daily",
            parameters=["T2M"],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )
    assert excinfo.value.category == "connectivity"
    assert excinfo.value.retryable is True


def test_request_json_classifies_timeout(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise socket.timeout("timed out")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaPowerClient(timeout_seconds=5)
    with pytest.raises(NasaPowerClientError) as excinfo:
        client.temporal_point(
            temporal="daily",
            parameters=["T2M"],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )
    assert excinfo.value.category == "timeout"


def test_request_json_rejects_non_json_body(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        return _FakeResponse(b"<html>error</html>", content_type="text/html")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaPowerClient()
    with pytest.raises(NasaPowerClientError) as excinfo:
        client.temporal_point(
            temporal="daily",
            parameters=["T2M"],
            latitude=0.0,
            longitude=0.0,
            start="20240101",
            end="20240102",
        )
    assert excinfo.value.category == "response_format"


def test_error_with_context_prefixes_message() -> None:
    base = NasaPowerClientError("boom", category="timeout", retryable=True, hint="h")
    wrapped = base.with_context("while fetching point")
    assert str(wrapped).startswith("while fetching point. boom")
    assert wrapped.category == "timeout"
    assert wrapped.retryable is True
