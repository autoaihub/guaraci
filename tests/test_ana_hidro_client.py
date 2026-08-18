"""Tests for the ANA HidroWebService HTTP client (offline, fake urllib opener)."""

from __future__ import annotations

import io
import json
from urllib.error import HTTPError, URLError

import pytest

from guaraci.ana.client import AnaHidroClient, AnaHidroClientError

_OAUTH_OK = json.dumps(
    {
        "status": "200 OK",
        "code": 200,
        "message": "Chamada Realizada com Sucesso",
        "items": {"tokenautenticacao": "TOKEN123"},
    }
).encode("utf-8")

_SERIE_OK = json.dumps(
    {
        "status": "200 OK",
        "code": 200,
        "message": "Chamada Realizada com Sucesso",
        "items": [
            {"Data_Hora_Medicao": "2024-01-01T00:00:00", "Chuva_Adotada": 1.2},
            {"Data_Hora_Medicao": "2024-01-01T01:00:00", "Chuva_Adotada": 0.0},
        ],
    }
).encode("utf-8")


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeUrlopen:
    """Stand-in for ``urllib.request.urlopen`` used via monkeypatch."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.requests: list = []

    def __call__(self, request, timeout=None):  # noqa: ANN001
        self.requests.append(request)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)


def test_empty_credentials_raise() -> None:
    with pytest.raises(ValueError):
        AnaHidroClient(identificador="  ", senha="x")
    with pytest.raises(ValueError):
        AnaHidroClient(identificador="x", senha="  ")


def test_authenticate_extracts_token(monkeypatch) -> None:
    fake = _FakeUrlopen([_OAUTH_OK])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="pass")
    token = client.authenticate()
    assert token == "TOKEN123"
    req = fake.requests[0]
    assert req.get_header("Identificador") == "user"
    assert req.get_header("Senha") == "pass"
    assert req.full_url.endswith("/EstacoesTelemetricas/OAUth/v1")


def test_serie_telemetrica_reuses_cached_token(monkeypatch) -> None:
    fake = _FakeUrlopen([_OAUTH_OK, _SERIE_OK, _SERIE_OK])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="pass")

    items1 = client.serie_telemetrica(
        station_id=12345678, detail="adotada", data_busca="2024-01-31"
    )
    items2 = client.serie_telemetrica(
        station_id=12345678, detail="adotada", data_busca="2024-02-29"
    )
    assert len(items1) == 2
    assert len(items2) == 2
    # 1 auth call + 2 data calls == 3 total; token was reused, not re-fetched.
    assert len(fake.requests) == 3
    data_req = fake.requests[1]
    assert data_req.get_header("Authorization") == "Bearer TOKEN123"
    assert "C%C3%B3digo" in data_req.full_url or "digo" in data_req.full_url


def test_serie_telemetrica_query_uses_locked_param_names(monkeypatch) -> None:
    fake = _FakeUrlopen([_OAUTH_OK, _SERIE_OK])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="pass")
    client.serie_telemetrica(
        station_id=12345678,
        detail="detalhada",
        data_busca="2024-01-31",
        tipo_filtro_data="DATA_LEITURA",
        range_intervalo="DIAS_30",
    )
    url = fake.requests[1].full_url
    assert "HidroinfoanaSerieTelemetricaDetalhada/v1" in url
    assert "Range" in url or "%20Intervalo" in url
    assert "DIAS_30" in url


def test_invalid_detail_rejected() -> None:
    client = AnaHidroClient(identificador="user", senha="pass")
    with pytest.raises(AnaHidroClientError):
        client.serie_telemetrica(station_id=1, detail="bogus", data_busca="2024-01-01")


def test_401_triggers_single_reauth_retry(monkeypatch) -> None:
    unauthorized = HTTPError("http://x", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
    fake = _FakeUrlopen([_OAUTH_OK, unauthorized, _OAUTH_OK, _SERIE_OK])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="pass")
    items = client.serie_telemetrica(
        station_id=1, detail="adotada", data_busca="2024-01-01"
    )
    assert len(items) == 2
    # auth, 401 data call, re-auth, retried data call == 4 requests.
    assert len(fake.requests) == 4


def test_missing_token_field_raises(monkeypatch) -> None:
    bad_payload = json.dumps({"status": "200 OK", "code": 200, "items": {}}).encode("utf-8")
    fake = _FakeUrlopen([bad_payload])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="pass")
    with pytest.raises(AnaHidroClientError) as excinfo:
        client.authenticate()
    assert excinfo.value.category == "response_format"


def test_url_error_redacts_password(monkeypatch) -> None:
    fake = _FakeUrlopen([URLError("boom SECRETPASS")])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="SECRETPASS", max_attempts=1)
    with pytest.raises(AnaHidroClientError) as excinfo:
        client.authenticate()
    assert "SECRETPASS" not in str(excinfo.value)


def test_server_error_retryable(monkeypatch) -> None:
    err = HTTPError("http://x", 503, "Unavailable", {}, io.BytesIO(b""))
    fake = _FakeUrlopen([err])
    monkeypatch.setattr("guaraci.ana.client.urlopen", fake)
    client = AnaHidroClient(identificador="user", senha="pass", max_attempts=1)
    with pytest.raises(AnaHidroClientError) as excinfo:
        client.authenticate()
    assert excinfo.value.retryable is True
