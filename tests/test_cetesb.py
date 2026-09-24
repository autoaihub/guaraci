"""Offline tests for the CETESB QUALAR connector.

The shape asserted here was captured from the live ArcGIS service on
2026-09-15. Two of these tests guard findings that are easy to get wrong and
silent when wrong:

- ``TM`` is local time encoded as epoch milliseconds. Reading it as UTC gives
  the right answer; "correcting" the timezone shifts the whole series by three
  hours, and nothing crashes.
- ``M`` is the air quality index, not a concentration. Nothing in the payload
  says so, and the magnitudes are plausible either way.

The live counterpart is ``tests/test_cetesb_smoke.py`` (opt-in).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from guaraci.cetesb.client import (
    HOURS_PER_WINDOW,
    POLLUTANT_LAYERS,
    STATION_LAYER,
    CetesbClientError,
    CetesbQualarClient,
    epoch_ms_to_local_naive,
)
from guaraci.cetesb.qualar import CetesbEstacoesDataSource, CetesbQualarDataSource

# 2026-09-15 10:00 local, exactly as the service returned it for Americana.
_TM_AMERICANA = 1789466400000


def _station_feature(
    name: str = "Americana",
    municipio: str = "AMERICANA",
    *,
    lon: float = -47.347456,
    lat: float = -22.724507,
):
    return {
        "attributes": {
            "ID": 1,
            "Nome": name,
            "Municipio": municipio,
            "Endereco": "R TAILANDIA, 364",
            "Tipo_Rede": "A",
            "Situacao_Rede": "A",
            "DATA": "2026-09-15 10:00:00.000",
            "Indice": 10,
            "Qualidade": "N1 - BOA",
            "POLUENTE": "MP10",
            "MsgSaude": "--",
            "Efeito": "--",
        },
        "geometry": {"x": lon, "y": lat},
    }


def _pollutant_feature(name: str = "Americana", values=None):
    """One station row with ``M1..M48``/``TM1..TM48``, hours descending from TM1."""
    values = values if values is not None else [10] * HOURS_PER_WINDOW
    attributes = {"STATNM": name}
    for slot in range(1, HOURS_PER_WINDOW + 1):
        attributes[f"M{slot}"] = values[slot - 1]
        attributes[f"TM{slot}"] = _TM_AMERICANA - (slot - 1) * 3_600_000
    return {"attributes": attributes, "geometry": {"x": -47.347456, "y": -22.724507}}


class _FakeClient:
    """Stands in for the ArcGIS service, recording the layers asked for."""

    DEFAULT_TIMEOUT = 120

    def __init__(self, *, stations=None, pollutants=None, fail_layers=()):
        self.base_url = "https://fake.invalid/MapServer"
        self._stations = stations if stations is not None else [_station_feature()]
        self._pollutants = pollutants if pollutants is not None else [_pollutant_feature()]
        self._fail_layers = set(fail_layers)
        self.queried: list[int] = []

    def query_layer(self, layer, *, out_fields="*", where="1=1", return_geometry=False):
        self.queried.append(layer)
        if layer in self._fail_layers:
            raise CetesbClientError(f"layer {layer} unavailable", category="http_error")
        if layer == STATION_LAYER:
            return list(self._stations)
        return list(self._pollutants)


# --- Timestamp handling -----------------------------------------------------


def test_epoch_ms_is_read_as_local_time_without_shifting():
    """The decisive check: TM read as UTC equals the DATA field the service publishes."""
    assert epoch_ms_to_local_naive(_TM_AMERICANA) == datetime(2026, 9, 15, 10, 0, 0)


def test_epoch_ms_handles_missing_and_garbage():
    assert epoch_ms_to_local_naive(None) is None
    assert epoch_ms_to_local_naive("nao e numero") is None


def test_consecutive_slots_are_one_hour_apart():
    a = epoch_ms_to_local_naive(_TM_AMERICANA)
    b = epoch_ms_to_local_naive(_TM_AMERICANA - 3_600_000)
    assert (a - b).total_seconds() == 3600


# --- Unpivoting the 48-hour window -----------------------------------------


def test_window_unpivots_to_one_row_per_hour(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert frame.height == HOURS_PER_WINDOW
    assert list(frame.columns) == [
        "estacao", "municipio", "latitude", "longitude", "poluente", "datahora", "indice",
    ]
    assert payload["record_count"] == HOURS_PER_WINDOW
    assert payload["station_count"] == 1


def test_null_hours_are_dropped_rather_than_carried_as_blank_rows(tmp_path):
    values = [None] * HOURS_PER_WINDOW
    values[0] = 12
    values[1] = 13
    client = _FakeClient(pollutants=[_pollutant_feature(values=values)])
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=client)
    source.download(pollutants=["MP10"], output_dir=str(tmp_path))

    assert source.load_dataframe().height == 2


def test_measure_is_reported_as_index_not_concentration(tmp_path):
    """The payload must name what it carries, since the numbers alone do not."""
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    assert payload["measure"] == "indice"


def test_window_bounds_span_the_48_hours(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    assert payload["window_end"] == "2026-09-15 10:00:00"
    assert payload["window_start"] == "2026-09-13 11:00:00"


# --- The registry join ------------------------------------------------------


def test_municipality_is_joined_from_the_station_registry(tmp_path):
    """Without município there is no link to health data; the join is the point."""
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert frame["municipio"].unique().to_list() == ["AMERICANA"]
    assert frame["latitude"].unique().to_list() == [pytest.approx(-22.724507)]


def test_registry_failure_degrades_instead_of_losing_the_series(tmp_path):
    """The registry enriches; it must not be able to abort the collection."""
    client = _FakeClient(fail_layers={STATION_LAYER})
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert frame.height == HOURS_PER_WINDOW
    assert frame["municipio"].null_count() == HOURS_PER_WINDOW
    assert "Cadastro de estações" in str(payload.get("export_warning"))


def test_station_absent_from_registry_keeps_its_own_geometry(tmp_path):
    client = _FakeClient(pollutants=[_pollutant_feature(name="Estação Nova")])
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=client)
    source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert frame["municipio"].null_count() == frame.height
    assert frame["latitude"].unique().to_list() == [pytest.approx(-22.724507)]


# --- Parameters -------------------------------------------------------------


def test_default_collects_every_pollutant(tmp_path):
    client = _FakeClient()
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(output_dir=str(tmp_path))

    assert set(payload["pollutants"]) == set(POLLUTANT_LAYERS)
    assert set(client.queried) >= set(POLLUTANT_LAYERS.values())


@pytest.mark.parametrize("alias", ["MP25", "PM2.5", "pm25", "mp2_5"])
def test_pollutant_aliases_resolve_to_the_cetesb_spelling(tmp_path, alias):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(pollutants=[alias], output_dir=str(tmp_path))
    assert payload["pollutants"] == ["MP2.5"]


def test_unknown_pollutant_is_rejected(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    with pytest.raises(ValueError, match="Unknown CETESB pollutant"):
        source.download(pollutants=["CHUMBO"], output_dir=str(tmp_path))


def test_station_filter_ignores_case_and_accents_are_preserved(tmp_path):
    client = _FakeClient(
        pollutants=[_pollutant_feature(name="Americana"), _pollutant_feature(name="Bauru")]
    )
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=client)
    source.download(pollutants=["MP10"], stations=["aMeRiCaNa"], output_dir=str(tmp_path))
    assert source.load_dataframe()["estacao"].unique().to_list() == ["Americana"]


def test_municipality_filter(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    source.download(pollutants=["MP10"], municipios=["sao paulo"], output_dir=str(tmp_path))
    assert source.load_dataframe().is_empty()


def test_pollutant_layer_failure_is_reported_without_aborting_the_rest(tmp_path):
    client = _FakeClient(fail_layers={POLLUTANT_LAYERS["CO"]})
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(pollutants=["CO", "MP10"], output_dir=str(tmp_path))

    assert payload["failed_count"] == 1
    assert payload["pollutants"] == ["MP10"]
    assert source.load_dataframe().height == HOURS_PER_WINDOW


# --- Export -----------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_export_writes_the_artifact(tmp_path, fmt):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(pollutants=["MP10"], output_format=fmt, output_dir=str(tmp_path))
    exported = payload["exported_files"]
    assert len(exported) == 1 and exported[0].endswith(f".{fmt}")


def test_unsupported_export_format_is_rejected(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    with pytest.raises(ValueError, match="Unsupported CETESB export format"):
        source.download(pollutants=["MP10"], output_format="xlsx", output_dir=str(tmp_path))


def test_manifest_is_written(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(pollutants=["MP10"], output_dir=str(tmp_path))
    assert Path(str(payload["manifest_path"])).is_file()


def test_keep_raw_persists_the_arcgis_payload(tmp_path):
    source = CetesbQualarDataSource(output_path=str(tmp_path), client=_FakeClient())
    source.download(pollutants=["MP10"], keep_raw=True, output_dir=str(tmp_path))
    assert (tmp_path / "raw" / "cetesb_qualar_raw.json").is_file()


# --- Station registry source ------------------------------------------------


def test_station_source_returns_the_registry_columns(tmp_path):
    source = CetesbEstacoesDataSource(output_path=str(tmp_path), client=_FakeClient())
    payload = source.download(output_dir=str(tmp_path))
    frame = source.load_dataframe()

    assert payload["record_count"] == 1
    assert {"estacao", "municipio", "latitude", "longitude", "qualidade"} <= set(frame.columns)
    assert frame["estacao"].to_list() == ["Americana"]


def test_station_source_municipality_filter(tmp_path):
    source = CetesbEstacoesDataSource(output_path=str(tmp_path), client=_FakeClient())
    source.download(municipios=["campinas"], output_dir=str(tmp_path))
    assert source.load_dataframe().is_empty()


def test_empty_station_registry_yields_typed_empty_frame(tmp_path):
    source = CetesbEstacoesDataSource(
        output_path=str(tmp_path), client=_FakeClient(stations=[])
    )
    source.download(output_dir=str(tmp_path))
    frame = source.load_dataframe()
    assert frame.is_empty()
    assert "estacao" in frame.columns


# --- Client error handling --------------------------------------------------


class _StubClient(CetesbQualarClient):
    def __init__(self, payload):
        super().__init__(base_url="https://fake.invalid/MapServer")
        self._payload = payload

    def _request_json(self, url):  # type: ignore[override]
        return self._payload


def test_arcgis_error_payload_becomes_an_exception():
    client = _StubClient({"error": {"message": "Invalid or missing input parameters."}})
    with pytest.raises(CetesbClientError, match="Invalid or missing input"):
        client.query_layer(1)


def test_truncated_response_is_refused_rather_than_silently_short():
    """A partial window would look like a real series. It must not pass."""
    client = _StubClient({"features": [], "exceededTransferLimit": True})
    with pytest.raises(CetesbClientError, match="exceededTransferLimit"):
        client.query_layer(1)


def test_non_object_payload_is_refused():
    client = _StubClient(["unexpected"])
    with pytest.raises(CetesbClientError, match="expected a JSON object"):
        client.query_layer(1)


def test_missing_features_key_returns_empty_list():
    assert _StubClient({}).query_layer(1) == []


def test_empty_base_url_is_rejected():
    with pytest.raises(ValueError, match="base URL cannot be empty"):
        CetesbQualarClient(base_url="   ")


# --- Registration in the platform -------------------------------------------


def test_both_sources_are_registered_with_themes():
    from guaraci.services.downloads import DownloadService

    service = DownloadService()
    descriptors = {d.source: d for d in service.list_sources()}

    for name in ("cetesb_qualar", "cetesb_estacoes"):
        assert name in descriptors
        assert descriptors[name].mode == "cetesb qualar api"
        assert "qualidade_ar" in descriptors[name].themes


def test_qualar_schema_exposes_the_pollutant_choices():
    from guaraci.services.downloads import DownloadService

    schema = DownloadService().get_source_schema("cetesb_qualar")
    params = {p["name"]: p for p in schema["params"]}
    assert set(params["pollutants"]["allowed_values"]) == set(POLLUTANT_LAYERS)
    assert {"municipios", "stations", "output_format", "keep_raw"} <= set(params)


def test_schema_description_warns_that_values_are_an_index():
    """Documentation that only lives in a docstring does not reach the user."""
    from guaraci.services.downloads import DownloadService

    schema = DownloadService().get_source_schema("cetesb_qualar")
    description = next(p for p in schema["params"] if p["name"] == "pollutants")["description"]
    assert "ÍNDICE" in description
    assert "µg/m³" in description
