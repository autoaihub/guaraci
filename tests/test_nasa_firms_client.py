"""Tests for the NASA FIRMS HTTP client."""

from __future__ import annotations

import io
import socket
from urllib.error import HTTPError, URLError

import pytest

from guaraci.nasa import client as client_mod
from guaraci.nasa.client import NasaFirmsClient, NasaFirmsClientError


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_country_url_embeds_key_and_params(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        return _FakeResponse(b"latitude,longitude\n-1,-2\n")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaFirmsClient()
    text = client.fetch_country_csv(
        map_key="ABC123",
        source="VIIRS_SNPP_NRT",
        country="BRA",
        day_range=5,
        date="2024-08-01",
    )
    assert "latitude" in text
    assert (
        "/api/country/csv/ABC123/VIIRS_SNPP_NRT/BRA/5/2024-08-01"
        in str(captured["url"])
    )


def test_area_url_uses_area_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        return _FakeResponse(b"latitude,longitude\n")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaFirmsClient()
    client.fetch_area_csv(
        map_key="KEY",
        source="MODIS_NRT",
        area="-74,-34,-34,6",
        day_range=3,
        date="2024-08-01",
    )
    assert "/api/area/csv/KEY/MODIS_NRT/" in str(captured["url"])


def test_http_error_redacts_map_key(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"Invalid MAP_KEY SECRETKEY"),
        )

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaFirmsClient()
    with pytest.raises(NasaFirmsClientError) as excinfo:
        client.fetch_country_csv(
            map_key="SECRETKEY",
            source="VIIRS_SNPP_NRT",
            country="BRA",
            day_range=1,
            date="2024-08-01",
        )
    assert "SECRETKEY" not in str(excinfo.value)
    assert excinfo.value.category == "configuration"


def test_server_error_is_retryable(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 503, "Unavailable", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaFirmsClient()
    with pytest.raises(NasaFirmsClientError) as excinfo:
        client.fetch_country_csv(
            map_key="K",
            source="VIIRS_SNPP_NRT",
            country="BRA",
            day_range=1,
            date="2024-08-01",
        )
    assert excinfo.value.retryable is True


def test_url_error_redacts_key(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise URLError("failed for SECRETKEY")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaFirmsClient()
    with pytest.raises(NasaFirmsClientError) as excinfo:
        client.fetch_country_csv(
            map_key="SECRETKEY",
            source="VIIRS_SNPP_NRT",
            country="BRA",
            day_range=1,
            date="2024-08-01",
        )
    assert "SECRETKEY" not in str(excinfo.value)
    assert excinfo.value.category == "connectivity"


def test_timeout_classified(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise socket.timeout("timed out")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = NasaFirmsClient(timeout_seconds=3)
    with pytest.raises(NasaFirmsClientError) as excinfo:
        client.fetch_country_csv(
            map_key="K",
            source="VIIRS_SNPP_NRT",
            country="BRA",
            day_range=1,
            date="2024-08-01",
        )
    assert excinfo.value.category == "timeout"


def test_with_context_preserves_category() -> None:
    base = NasaFirmsClientError("boom", category="configuration", hint="h")
    wrapped = base.with_context("while fetching")
    assert str(wrapped).startswith("while fetching. boom")
    assert wrapped.category == "configuration"
