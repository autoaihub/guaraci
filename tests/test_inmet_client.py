"""Tests for the INMET ZIP-transport HTTP client (offline, fake urlopen)."""
from __future__ import annotations

import io
import socket
from urllib.error import HTTPError, URLError

import pytest

from guaraci.inmet import client as client_mod
from guaraci.inmet.client import InmetClient, InmetClientError


class _FakeHeadResponse:
    def __init__(self, headers: dict) -> None:
        self.headers = headers

    def __enter__(self) -> "_FakeHeadResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeStreamResponse:
    def __init__(self, body: bytes, content_length: str | None = None) -> None:
        self._buf = io.BytesIO(body)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_default_base_url_and_zip_url() -> None:
    client = InmetClient()
    assert client.base_url == "https://portal.inmet.gov.br/uploads/dadoshistoricos"
    assert client.zip_url(2025) == "https://portal.inmet.gov.br/uploads/dadoshistoricos/2025.zip"


def test_empty_base_url_raises() -> None:
    with pytest.raises(ValueError):
        InmetClient(base_url="   ")


def test_head_content_length_parses_header(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        assert request.get_method() == "HEAD"
        assert request.headers.get("User-agent") == InmetClient.USER_AGENT
        return _FakeHeadResponse({"Content-Length": "90898634"})

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient()
    assert client.head_content_length(2025) == 90898634


def test_head_content_length_returns_none_when_missing(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        return _FakeHeadResponse({})

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient()
    assert client.head_content_length(2025) is None


def test_head_content_length_classifies_404(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient()
    with pytest.raises(InmetClientError) as excinfo:
        client.head_content_length(1999)
    assert excinfo.value.category == "configuration"
    assert excinfo.value.retryable is False


def test_head_content_length_classifies_server_error_as_retryable(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 503, "Unavailable", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient()
    with pytest.raises(InmetClientError) as excinfo:
        client.head_content_length(2025)
    assert excinfo.value.retryable is True


def test_head_content_length_classifies_connectivity_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise URLError("name resolution failed")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient()
    with pytest.raises(InmetClientError) as excinfo:
        client.head_content_length(2025)
    assert excinfo.value.category == "connectivity"
    assert excinfo.value.retryable is True


def test_download_zip_streams_to_destination(tmp_path, monkeypatch) -> None:
    body = b"PK\x03\x04fake-zip-bytes"

    def fake_urlopen(request, timeout):  # noqa: ANN001
        assert request.get_method() == "GET"
        return _FakeStreamResponse(body, content_length=str(len(body)))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient()
    destination = tmp_path / "2025.zip"
    events = []
    written = client.download_zip(2025, destination, progress_callback=events.append)

    assert written == len(body)
    assert destination.read_bytes() == body
    assert not destination.with_name("2025.zip.part").exists()
    assert events[-1]["file_bytes_downloaded"] == len(body)


def test_download_zip_retries_on_retryable_error_then_succeeds(tmp_path, monkeypatch) -> None:
    body = b"zip-bytes"
    attempts = {"count": 0}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(request.full_url, 503, "Unavailable", {}, io.BytesIO(b""))
        return _FakeStreamResponse(body)

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)
    client = InmetClient(max_attempts=3)
    destination = tmp_path / "2025.zip"
    written = client.download_zip(2025, destination)

    assert attempts["count"] == 2
    assert written == len(body)
    assert destination.read_bytes() == body


def test_download_zip_raises_after_exhausting_attempts(tmp_path, monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 503, "Unavailable", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)
    client = InmetClient(max_attempts=2)
    destination = tmp_path / "2025.zip"
    with pytest.raises(InmetClientError):
        client.download_zip(2025, destination)


def test_download_zip_classifies_timeout(monkeypatch, tmp_path) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise socket.timeout("timed out")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InmetClient(max_attempts=1)
    with pytest.raises(InmetClientError) as excinfo:
        client.download_zip(2025, tmp_path / "2025.zip")
    assert excinfo.value.category == "timeout"
