"""Smoke opt-in contra o portal do FNS (rede real).

Desligado por padrão; ``GUARACI_FNS_SMOKE=1`` liga. Confere a descoberta dos
links e lê 2 KB (Range) do arquivo de um ano, sem baixar nada inteiro.
"""
from __future__ import annotations

import os
from urllib.request import Request, urlopen

import pytest

from guaraci.fns import FnsClient, discover_links

SMOKE = os.environ.get("GUARACI_FNS_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not SMOKE, reason="Set GUARACI_FNS_SMOKE=1 to enable the live FNS smoke test"),
]


def test_live_discovery_and_range():
    client = FnsClient(timeout_seconds=60)
    links = discover_links(client.listing_html(), client.listing_url)
    assert {2002, 2020, 2024, 2025} <= set(links)
    remote = client.head(links[2024])  # idg_download redireciona para o arquivo
    assert "idg_download" not in remote.url and remote.size
    request = Request(remote.url, headers={"User-Agent": client.USER_AGENT, "Range": "bytes=0-2047"})
    with urlopen(request, timeout=60) as response:
        head = response.read(2048)
    assert b"BLOCO" in head and b"VL_BRUTO" in head
