"""Smoke opt-in do WFS TerraBrasilis (rede real). Ative com GUARACI_TERRABRASILIS_SMOKE=1."""

from __future__ import annotations

import os

import pytest

from guaraci.inpe.terrabrasilis import (
    DETER_LAYERS,
    PRODES_LAYERS,
    TerraBrasilisClient,
    TerraBrasilisDataSource,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_TERRABRASILIS_SMOKE") != "1",
        reason="Set GUARACI_TERRABRASILIS_SMOKE=1 to enable the live TerraBrasilis smoke test",
    ),
]

_LAYERS = [*DETER_LAYERS.values(), *PRODES_LAYERS.values()]


@pytest.mark.parametrize("spec", _LAYERS, ids=lambda s: s.key)
def test_live_count_5_sem_geometria(spec):
    client = TerraBrasilisClient(timeout_seconds=120)
    props = client.describe(spec.typename)
    assert "geom" not in props and "st_multi" not in props
    text = client.get_page(spec.typename, props, count=5, start_index=0,
                           sort_field=spec.sort_field, cql=None)
    lines = text.strip().splitlines()
    assert 1 < len(lines) <= 6
    # Pampa declara geom como obrigatorio (minOccurs=1): o GeoServer a envia mesmo
    # sem constar em propertyName. O download descarta a coluna na gravacao.
    assert "FID" in lines[0]


def test_live_deter_recorte_anual(tmp_path):
    ds = TerraBrasilisDataSource("inpe_deter_amazonia", output_path=str(tmp_path))
    payload = ds.download(start_year=2020, end_year=2020, page_size=50)
    assert payload["rows"] > 0
