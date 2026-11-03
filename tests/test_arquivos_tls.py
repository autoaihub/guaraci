"""Cadeia TLS do INEP: o servidor omite o intermediário, que vem embutido no pacote."""

from __future__ import annotations

import ssl
from pathlib import Path
from urllib.error import URLError

import pytest

from guaraci.arquivos import tls
from guaraci.arquivos.http_files import HttpFileClient, HttpFileClientError

INEP_URL = "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2023.zip"


def _subjects(context: ssl.SSLContext) -> list:
    return [dict(item[0] for item in cert["subject"]) for cert in context.get_ca_certs()]


def test_intermediate_is_bundled_and_parseable():
    assert tls.INTERMEDIATES_CRT.is_file()
    text = tls.INTERMEDIATES_CRT.read_text(encoding="ascii")
    assert text.count("BEGIN CERTIFICATE") == 1
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(tls.INTERMEDIATES_CRT))
    assert _subjects(context)[0]["commonName"] == "RNP ICPEdu GR46 OV TLS CA 2025"


def test_context_for_inep_adds_intermediate_and_keeps_verification():
    context = tls.ssl_context_for(INEP_URL)
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert "RNP ICPEdu GR46 OV TLS CA 2025" in {s.get("commonName") for s in _subjects(context)}


def test_other_hosts_and_schemes_use_the_default_context():
    assert tls.ssl_context_for("https://www.gov.br/inca/x.zip") is None
    assert tls.ssl_context_for("https://naoinep.gov.br/x.zip") is None
    assert tls.ssl_context_for("http://download.inep.gov.br/x.zip") is None
    assert tls.ssl_context_for("ftp://ftp.datasus.gov.br/x.dbc") is None


def test_client_head_passes_inep_context_to_urlopen(monkeypatch):
    seen = {}

    class Response:
        headers = {"Content-Length": "10"}

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def fake_urlopen(request, timeout=None, context=None):
        seen["context"] = context
        return Response()

    monkeypatch.setattr("guaraci.arquivos.http_files.urlopen", fake_urlopen)
    assert HttpFileClient().head(INEP_URL).size == 10
    assert seen["context"] is tls.ssl_context_for(INEP_URL)
    HttpFileClient().head("https://exemplo.gov.br/a.csv")
    assert seen["context"] is None


def test_certificate_failure_explains_the_missing_intermediate(monkeypatch):
    def fake_urlopen(*_a, **_k):
        raise URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))

    monkeypatch.setattr("guaraci.arquivos.http_files.urlopen", fake_urlopen)
    with pytest.raises(HttpFileClientError) as info:
        HttpFileClient(max_attempts=1).head("https://exemplo.gov.br/a.csv")
    assert "ca_intermediarios.crt" in (info.value.hint or "")


def test_pem_is_included_in_package_data():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert "data/*.crt" in pyproject.read_text(encoding="utf-8")
