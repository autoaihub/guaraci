"""Smoke opt-in das fontes CKAN estaduais: so ``package_show``/``package_search``, sem baixar arquivo.

Rodar com ``GUARACI_CKAN_ESTADUAIS_SMOKE=1``.
"""

from __future__ import annotations

import os

import pytest

from guaraci.ckan import BROWSER_USER_AGENT, CkanClient, select_resources
from guaraci.ckan.estaduais import CKAN_ESTADUAIS

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_CKAN_ESTADUAIS_SMOKE") != "1",
        reason="defina GUARACI_CKAN_ESTADUAIS_SMOKE=1 para consultar os portais",
    ),
]


@pytest.mark.parametrize("key", sorted(CKAN_ESTADUAIS))
def test_spec_casa_recursos_no_portal(key):
    spec = CKAN_ESTADUAIS[key]
    client = CkanClient(
        spec.base_url, user_agent=BROWSER_USER_AGENT if spec.browser_user_agent else None
    )
    found = []
    for package_id in spec.package_ids:
        found.extend(client.resources(package_id))
    if spec.package_query:
        from guaraci.ckan import resources_from_package

        for package in client.iter_packages(fq=spec.package_query):
            found.extend(resources_from_package(package))
    anos = [2025] if spec.period_required else None
    chosen, _, _ = select_resources(spec, found, anos=anos)
    assert chosen
