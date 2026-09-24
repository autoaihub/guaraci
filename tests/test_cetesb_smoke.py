"""Opt-in live smoke test for the CETESB QUALAR connector (real ArcGIS service).

Disabled by default; set ``GUARACI_CETESB_SMOKE=1`` to run.

Beyond the usual "does it still answer", this file re-checks the one claim the
offline tests can only assume: that ``M`` is the air quality index and not a
concentration. It does so the same way the finding was made, by cross-checking
a pollutant layer against the station layer, which publishes ``Indice`` and
``POLUENTE`` for the same station and hour. If the CETESB ever switches those
columns to concentration, this is where we find out, instead of finding out
through a study built on the wrong unit.
"""

from __future__ import annotations

import os

import pytest

from guaraci.cetesb.client import (
    HOURS_PER_WINDOW,
    POLLUTANT_LAYERS,
    STATION_LAYER,
    CetesbQualarClient,
)
from guaraci.cetesb.qualar import CetesbEstacoesDataSource, CetesbQualarDataSource

SMOKE = os.environ.get("GUARACI_CETESB_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_CETESB_SMOKE=1 to enable the live CETESB smoke test"
    ),
]


def test_live_service_still_has_the_eight_expected_layers():
    info = CetesbQualarClient().service_info()
    names = {layer["name"] for layer in info.get("layers", [])}
    for pollutant in POLLUTANT_LAYERS:
        expected = f"QUALAR_DADOSHORARIOS_48H_{pollutant}"
        assert expected in names, f"camada ausente: {expected}"
    assert "QUALAR_DADOSHORARIOS_PTO" in names


def test_live_values_are_the_index_not_a_concentration():
    """Cross-check a pollutant layer against the station layer's own index."""
    client = CetesbQualarClient()
    stations = client.query_layer(STATION_LAYER, out_fields="*")

    compared = 0
    for feature in stations:
        attributes = feature.get("attributes") or {}
        pollutant = attributes.get("POLUENTE")
        index = attributes.get("Indice")
        name = attributes.get("Nome")
        if pollutant not in POLLUTANT_LAYERS or index is None or not name:
            continue
        escaped = str(name).replace("'", "''")
        rows = client.query_layer(
            POLLUTANT_LAYERS[pollutant],
            out_fields="STATNM,M1",
            where=f"STATNM='{escaped}'",
        )
        if not rows:
            continue
        assert rows[0]["attributes"]["M1"] == index, (
            f"{name}/{pollutant}: a camada do poluente divergiu do índice da "
            "camada de estações. Se a CETESB passou a publicar concentração, o "
            "conector e a documentação precisam ser revistos."
        )
        compared += 1
        if compared >= 5:
            break
    assert compared >= 3, "não houve estações suficientes para a verificação"


def test_live_download_shapes_a_48_hour_window(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path))
    payload = source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert payload["measure"] == "indice"
    assert payload["station_count"] > 20
    assert not frame.is_empty()
    assert frame["municipio"].null_count() < frame.height  # o join funcionou

    span = frame["datahora"].max() - frame["datahora"].min()
    assert span.total_seconds() <= (HOURS_PER_WINDOW - 1) * 3600


def test_live_station_registry_is_geolocated(tmp_path):
    source = CetesbEstacoesDataSource(output_path=str(tmp_path))
    payload = source.download(output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert payload["record_count"] > 50
    assert frame["latitude"].null_count() == 0
    assert frame["longitude"].null_count() == 0
    # Estado de São Paulo, com folga generosa nas bordas.
    assert frame["latitude"].min() > -26 and frame["latitude"].max() < -19
    assert frame["longitude"].min() > -54 and frame["longitude"].max() < -43
