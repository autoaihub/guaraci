"""Smoke opt-in do MonitorAr (portal real). Defina ``GUARACI_MONITORAR_SMOKE=1``.

Só metadados: ``package_show``, HEAD do zip mais recente e os primeiros 64 KB
por Range. Não baixa o arquivo.
"""

from __future__ import annotations

import os
from urllib.request import Request, urlopen

import pytest

from guaraci.mma import MonitorArClient

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_MONITORAR_SMOKE") != "1",
        reason="Set GUARACI_MONITORAR_SMOKE=1 to enable the live MonitorAr smoke test",
    ),
]


def test_live_package_show_head_e_range():
    client = MonitorArClient()
    resources = client.list_resources()
    assert resources and resources[0].year >= 2022
    last = resources[-1]
    # O servidor não manda Content-Length no HEAD (só Content-Range) e ignora Range.
    assert (client.remote_size(last) or 0) > 1_000_000
    request = Request(last.url, headers={"User-Agent": "guaraci"})
    with urlopen(request, timeout=60) as response:
        head = response.read(65536)  # fecha sem baixar o resto
    assert head[:4] == b"PK\x03\x04"
