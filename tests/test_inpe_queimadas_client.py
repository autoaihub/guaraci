"""Tests for the INPE Queimadas HTTP client."""

from __future__ import annotations

import io
import socket
from urllib.error import HTTPError, URLError

import pytest

from guaraci.inpe import client as client_mod
from guaraci.inpe.client import InpeQueimadasClient, InpeQueimadasClientError

_INDEX_HTML = """
<html><body>
<table>
<tr><td><a href="?C=N;O=D">Name</a></td></tr>
<tr><td><a href="/queimadas/queimadas/focos/csv/anual/">Parent Directory</a></td></tr>
<tr><td><a href="focos_br_ref_2003.zip">focos_br_ref_2003.zip</a></td></tr>
<tr><td><a href="focos_br_ref_2004.zip">focos_br_ref_2004.zip</a></td></tr>
</table>
</body></html>
"""


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_list_directory_parses_filenames_only(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        return _FakeResponse(_INDEX_HTML.encode("utf-8"))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InpeQueimadasClient()
    names = client.list_directory("anual/Brasil_sat_ref")
    assert names == ["focos_br_ref_2003.zip", "focos_br_ref_2004.zip"]
    assert str(captured["url"]).endswith("anual/Brasil_sat_ref/")


def test_fetch_bytes_returns_raw_body(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        return _FakeResponse(b"PK\x03\x04binary-zip-content")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InpeQueimadasClient()
    raw = client.fetch_bytes("anual/Brasil_sat_ref/focos_br_ref_2003.zip")
    assert raw.startswith(b"PK\x03\x04")


def test_404_is_configuration_not_retryable(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InpeQueimadasClient()
    with pytest.raises(InpeQueimadasClientError) as excinfo:
        client.fetch_bytes("anual/Brasil_sat_ref/focos_br_ref_1999.zip")
    assert excinfo.value.category == "configuration"
    assert excinfo.value.retryable is False


def test_server_error_is_retryable(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 503, "Unavailable", {}, io.BytesIO(b""))

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InpeQueimadasClient()
    with pytest.raises(InpeQueimadasClientError) as excinfo:
        client.fetch_bytes("anual/Brasil_sat_ref/focos_br_ref_2003.zip")
    assert excinfo.value.retryable is True


def test_url_error_is_connectivity(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise URLError("network unreachable")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InpeQueimadasClient()
    with pytest.raises(InpeQueimadasClientError) as excinfo:
        client.fetch_bytes("anual/Brasil_sat_ref/focos_br_ref_2003.zip")
    assert excinfo.value.category == "connectivity"


def test_timeout_classified(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise socket.timeout("timed out")

    monkeypatch.setattr(client_mod, "urlopen", fake_urlopen)
    client = InpeQueimadasClient(timeout_seconds=3)
    with pytest.raises(InpeQueimadasClientError) as excinfo:
        client.fetch_bytes("anual/Brasil_sat_ref/focos_br_ref_2003.zip")
    assert excinfo.value.category == "timeout"


def test_empty_base_url_rejected() -> None:
    with pytest.raises(ValueError):
        InpeQueimadasClient(base_url="   ")
