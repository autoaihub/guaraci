"""Smoke opt-in do núcleo CKAN federal (portais reais). Defina ``GUARACI_CKAN_SMOKE=1``.

Só metadados: ``package_show`` de cada chave e a seleção do período mais novo.
Nenhum arquivo é baixado (os zips de mantidos e cessados passam de 700 MB).
"""

from __future__ import annotations

import os

import pytest

from guaraci.ckan import CkanClient, select_resources
from guaraci.ckan.federal import CKAN_FEDERAL

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_CKAN_SMOKE") != "1",
        reason="Set GUARACI_CKAN_SMOKE=1 to enable the live CKAN smoke test",
    ),
]


@pytest.mark.parametrize("key", sorted(CKAN_FEDERAL))
def test_live_package_show_e_selecao(key):
    spec = CKAN_FEDERAL[key]
    client = CkanClient(spec.base_url, timeout_seconds=120)
    resources = [r for pid in spec.package_ids for r in client.resources(pid)]
    assert resources
    chosen, _, _ = select_resources(spec, resources)
    assert chosen, f"{key}: nenhum recurso {spec.file_format} casou"
