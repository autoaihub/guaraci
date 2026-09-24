"""Offline tests for the authenticated CETESB QUALAR connector (concentration).

This is the path that requires a login, so none of it can be exercised against
the live system here. What these tests do cover is everything that does not
depend on the network: the HTML table parser, the Brazilian number format, the
date handling, the code tables, and the failure modes that would otherwise be
silent.

Three of these guard mistakes that produce *plausible wrong answers* rather
than errors, which is the class of bug worth spending tests on:

- a wrong credential returns HTTP 200 with the login page, which would read as
  "no data in this period";
- ``1.234,56`` parsed by only swapping the comma becomes ``1.23456``;
- the QUALAR station code is not the ArcGIS ``ID``, so mixing them up returns
  a different station's data with no error at all.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from guaraci.cetesb import codes
from guaraci.cetesb.horario import CetesbQualarHorarioDataSource
from guaraci.cetesb.qualar_client import (
    REGISTRATION_URL,
    CetesbAuthError,
    QualarClient,
    parse_brazilian_number,
    parse_qualar_html,
)

_ROW = [
    "CETESB", "A", "Automatica", "P", "01/01/2024", "01:00", "99", "Pinheiros",
    "MP10", "ug/m3", "1.234,56", "N", "Sim", "", "", "", "", "", "X",
]


def _row_html(row=None) -> str:
    cells = row if row is not None else _ROW
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _page(*rows: str) -> str:
    """A data table nested inside a layout table, as QUALAR actually serves it."""
    inner = "<table><tr><th>cabecalho</th></tr>" + "".join(rows) + "</table>"
    return f"<html><body><table><tr><td>{inner}</td></tr></table></body></html>"


LOGIN_PAGE = (
    '<html><form id="segurancaForm" action="/qualar/autenticador" method="post">'
    '<input name="cetesb_login" type="text">'
    '<input name="cetesb_password" type="password"></form></html>'
)


class _ScriptedClient(QualarClient):
    """A QualarClient whose HTTP layer replays a scripted list of responses."""

    def __init__(self, responses, **kwargs):
        kwargs.setdefault("login", "user")
        kwargs.setdefault("password", "pass")
        kwargs.setdefault("pause_seconds", 0)
        super().__init__(**kwargs)
        self._responses = list(responses)
        self.posted = []

    def _post(self, url, body):  # type: ignore[override]
        self.posted.append((url, body.decode("latin-1")))
        if not self._responses:
            raise AssertionError("more requests than scripted responses")
        return self._responses.pop(0)


# --- Number format ----------------------------------------------------------


def test_thousands_separator_is_removed_before_the_decimal_comma():
    """Swapping only the comma would turn 1.234,56 into 1.23456."""
    assert parse_brazilian_number("1.234,56") == 1234.56


@pytest.mark.parametrize(
    "raw,expected",
    [("12,5", 12.5), ("1234", 1234.0), ("0,0", 0.0), ("-", None), ("", None),
     ("  ", None), ("abc", None), (None, None)],
)
def test_number_parsing_edge_cases(raw, expected):
    assert parse_brazilian_number(raw) == expected


# --- HTML table parsing -----------------------------------------------------


def test_finds_the_data_table_nested_inside_a_layout_table():
    rows = parse_qualar_html(_page(_row_html(), _row_html()))
    assert len(rows) == 2
    assert rows[0][7] == "Pinheiros"


def test_finds_the_data_table_when_it_is_the_outer_one():
    html = (
        "<html><table><tr><td><table><tr><td>layout</td></tr></table></td></tr></table>"
        f"<table>{_row_html()}</table></html>"
    )
    assert len(parse_qualar_html(html)) == 1


def test_tolerates_unclosed_cells():
    cells = "".join(f"<td>{c}" for c in _ROW)
    assert len(parse_qualar_html(f"<table><tr>{cells}</tr></table>")) == 1


def test_page_without_a_19_column_table_yields_nothing():
    assert parse_qualar_html("<html><table><tr><td>a</td></tr></table></html>") == []


def test_header_row_is_not_mistaken_for_data():
    rows = parse_qualar_html(_page(_row_html()))
    assert all(len(row) == 19 for row in rows)
    assert len(rows) == 1


# --- Authentication ---------------------------------------------------------


def test_wrong_credentials_raise_instead_of_looking_like_empty_data():
    """QUALAR answers 200 with the login form; that must not read as 'no data'."""
    client = _ScriptedClient([LOGIN_PAGE])
    with pytest.raises(CetesbAuthError, match="rejected the credentials"):
        client.authenticate()


def test_auth_error_points_at_the_registration_page():
    client = _ScriptedClient([LOGIN_PAGE])
    with pytest.raises(CetesbAuthError) as excinfo:
        client.authenticate()
    assert REGISTRATION_URL in str(excinfo.value)


def test_login_posts_the_form_fields_the_system_expects():
    client = _ScriptedClient(["<html>bem-vindo</html>"])
    client.authenticate()
    url, body = client.posted[0]
    assert url.endswith("/autenticador")
    assert "cetesb_login=user" in body
    assert "cetesb_password=pass" in body


def test_session_expiry_mid_sweep_triggers_one_reauth():
    """A long sweep must not die because the session timed out halfway."""
    client = _ScriptedClient(
        [
            "<html>ok</html>",        # login inicial
            LOGIN_PAGE,               # sessão caiu
            "<html>ok</html>",        # reautenticação
            _page(_row_html()),       # repetição da consulta
        ]
    )
    readings = client.fetch_readings(
        station="Pinheiros", parameter="MP10", start=date(2024, 1, 1), end=date(2024, 1, 1)
    )
    assert len(readings) == 1
    assert len(client.posted) == 4


def test_empty_credentials_are_refused_up_front():
    with pytest.raises(ValueError, match="login cannot be empty"):
        QualarClient(login="  ", password="x")
    with pytest.raises(ValueError, match="password cannot be empty"):
        QualarClient(login="x", password="")


# --- Query construction and reading shape -----------------------------------


def test_query_sends_the_documented_form_parameters():
    client = _ScriptedClient(["<html>ok</html>", _page(_row_html())])
    client.fetch_readings(
        station="Pinheiros", parameter="MP10", start=date(2024, 1, 1), end=date(2024, 1, 31)
    )
    url, body = client.posted[1]
    assert "exportaDados.do?method=pesquisar" in url
    assert "irede=A" in body
    assert "iTipoDado=P" in body
    assert "dataInicialStr=01%2F01%2F2024" in body
    assert "dataFinalStr=31%2F01%2F2024" in body
    assert "nestcaMonto=99" in body      # Pinheiros no QUALAR
    assert "nparmt=12" in body           # MP10


def test_reading_carries_station_metadata_and_parsed_value():
    client = _ScriptedClient(["<html>ok</html>", _page(_row_html())])
    reading = client.fetch_readings(
        station="Pinheiros", parameter="MP10", start=date(2024, 1, 1), end=date(2024, 1, 1)
    )[0]

    assert reading["estacao"] == "Pinheiros"
    assert reading["codigo_estacao"] == 99
    assert reading["parametro"] == "MP10"
    assert reading["valor"] == 1234.56
    assert reading["unidade"] == "ug/m3"
    assert reading["datahora"] == datetime(2024, 1, 1, 1, 0)
    assert reading["validado"] is True
    assert reading["latitude"] is not None


def test_unvalidated_rows_are_dropped_by_default():
    row = list(_ROW)
    row[12] = "Não"
    client = _ScriptedClient(["<html>ok</html>", _page(_row_html(row))])
    assert client.fetch_readings(
        station="Pinheiros", parameter="MP10", start=date(2024, 1, 1), end=date(2024, 1, 1)
    ) == []


def test_unvalidated_rows_can_be_kept_explicitly():
    row = list(_ROW)
    row[12] = "Não"
    client = _ScriptedClient(["<html>ok</html>", _page(_row_html(row))])
    readings = client.fetch_readings(
        station="Pinheiros",
        parameter="MP10",
        start=date(2024, 1, 1),
        end=date(2024, 1, 1),
        only_validated=False,
    )
    assert len(readings) == 1 and readings[0]["validado"] is False


def test_hour_24_rolls_over_to_midnight_of_the_next_day():
    """CETESB writes midnight as 24:00; strptime refuses it."""
    row = list(_ROW)
    row[5] = "24:00"
    client = _ScriptedClient(["<html>ok</html>", _page(_row_html(row))])
    reading = client.fetch_readings(
        station="Pinheiros", parameter="MP10", start=date(2024, 1, 1), end=date(2024, 1, 2)
    )[0]
    assert reading["datahora"] == datetime(2024, 1, 2, 0, 0)


def test_inverted_date_range_is_refused():
    client = _ScriptedClient([])
    with pytest.raises(ValueError, match="cannot be before"):
        client.fetch_readings(
            station="Pinheiros", parameter="MP10",
            start=date(2024, 2, 1), end=date(2024, 1, 1),
        )


# --- Code tables ------------------------------------------------------------


def test_qualar_station_code_is_not_the_arcgis_id():
    """Two independent numberings for the same stations: Pinheiros is 99 here, 42 there."""
    assert codes.resolve_station("Pinheiros").code == 99  # QUALAR
    assert codes.resolve_station(99).name == "Pinheiros"
    with pytest.raises(ValueError, match="Unknown QUALAR station code"):
        codes.resolve_station(42)  # o ID de Pinheiros no ArcGIS


def test_the_two_numberings_do_not_overlap():
    """Why the mix-up is survivable: it always errors instead of silently
    returning another station.

    Checked live on 2026-09-15: the ArcGIS station layer uses ids 1-62 and
    QUALAR uses 66-290, with no value in common. That is a property of the
    current data, not a guarantee from CETESB, so it is pinned here: if a
    renumbering ever makes the ranges overlap, passing the wrong id starts
    returning a different station's data with no error at all, and this test
    is what says so.
    """
    arcgis_id_range = range(1, 63)
    assert not set(arcgis_id_range) & set(codes.STATIONS)
    assert min(codes.STATIONS) > 62


def test_station_and_parameter_tables_are_populated():
    assert len(codes.STATIONS) == 75
    assert len(codes.PARAMETERS) == 20
    assert len(codes.POLLUTANT_CODES) + len(codes.METEOROLOGY_CODES) == 20


def test_meteorological_parameters_are_flagged():
    assert codes.resolve_parameter("TEMP").meteorological is True
    assert codes.resolve_parameter("MP10").meteorological is False


@pytest.mark.parametrize("alias", ["pm25", "PM2.5", "mp25", "MP2_5"])
def test_parameter_aliases(alias):
    assert codes.resolve_parameter(alias).code == 57


def test_unknown_station_and_parameter_raise_with_guidance():
    with pytest.raises(ValueError, match="Unknown QUALAR station"):
        codes.resolve_station("Estacao Inexistente")
    with pytest.raises(ValueError, match="Unknown QUALAR parameter"):
        codes.resolve_parameter("CHUMBO")
    with pytest.raises(ValueError, match="Unknown QUALAR station code"):
        codes.resolve_station(999999)


# --- Datasource -------------------------------------------------------------


class _FakeQualarClient:
    DEFAULT_TIMEOUT = 180
    DEFAULT_PAUSE_SECONDS = 0

    def __init__(self, readings_by_pair=None, fail_pairs=()):
        self._by_pair = readings_by_pair or {}
        self._fail = set(fail_pairs)
        self.calls = []

    def fetch_readings(self, *, station, parameter, start, end, only_validated=True):
        key = (station.name, parameter.abbreviation)
        self.calls.append(key)
        if key in self._fail:
            from guaraci.cetesb.client import CetesbClientError

            raise CetesbClientError("boom", category="http_error")
        return self._by_pair.get(key, [])


def _reading(station="Pinheiros", parameter="MP10", value=10.0, hour=1):
    return {
        "estacao": station, "codigo_estacao": 99,
        "latitude": -23.56, "longitude": -46.70,
        "parametro": parameter, "codigo_parametro": 12, "unidade": "ug/m3",
        "datahora": datetime(2024, 1, 1, hour), "valor": value, "validado": True,
    }


def test_datasource_collects_every_station_parameter_pair(tmp_path):
    fake = _FakeQualarClient({("Pinheiros", "MP10"): [_reading()]})
    source = CetesbQualarHorarioDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(
        stations=["Pinheiros", "Ibirapuera"], parameters=["MP10", "O3"],
        start_date="2024-01-01", end_date="2024-01-02", output_dir=str(tmp_path),
    )
    assert payload["documents_found"] == 4
    assert len(fake.calls) == 4
    assert payload["measure"] == "concentracao"
    assert source.load_dataframe().height == 1


def test_datasource_reports_pairs_without_readings_as_a_warning_not_a_failure(tmp_path):
    """Not every station carries every sensor; that is normal, not an error."""
    fake = _FakeQualarClient({})
    source = CetesbQualarHorarioDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(
        stations=["Pinheiros"], parameters=["MP10"],
        start_date="2024-01-01", end_date="2024-01-02", output_dir=str(tmp_path),
    )
    assert payload["failed_count"] == 0
    assert "sem leitura" in str(payload.get("export_warning"))


def test_datasource_survives_one_failing_pair(tmp_path):
    fake = _FakeQualarClient(
        {("Pinheiros", "O3"): [_reading(parameter="O3")]},
        fail_pairs={("Pinheiros", "MP10")},
    )
    source = CetesbQualarHorarioDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(
        stations=["Pinheiros"], parameters=["MP10", "O3"],
        start_date="2024-01-01", end_date="2024-01-02", output_dir=str(tmp_path),
    )
    assert payload["failed_count"] == 1
    assert source.load_dataframe().height == 1


@pytest.mark.parametrize("value", ["2024-01-05", "05/01/2024"])
def test_datasource_accepts_iso_and_brazilian_dates(tmp_path, value):
    fake = _FakeQualarClient({})
    source = CetesbQualarHorarioDataSource(output_path=str(tmp_path), client=fake)
    payload = source.download(
        stations=["Pinheiros"], start_date=value, end_date=value,
        parameters=["MP10"], output_dir=str(tmp_path),
    )
    assert payload["start_date"] == "2024-01-05"


def test_datasource_rejects_a_bad_date(tmp_path):
    source = CetesbQualarHorarioDataSource(
        output_path=str(tmp_path), client=_FakeQualarClient()
    )
    with pytest.raises(ValueError, match="must be YYYY-MM-DD or DD/MM/YYYY"):
        source.download(
            stations=["Pinheiros"], start_date="janeiro", end_date="2024-01-02",
            output_dir=str(tmp_path),
        )


def test_datasource_requires_stations(tmp_path):
    """One request per station means there is no sane default."""
    source = CetesbQualarHorarioDataSource(
        output_path=str(tmp_path), client=_FakeQualarClient()
    )
    with pytest.raises(ValueError, match="'stations' is required"):
        source.download(
            stations=[], start_date="2024-01-01", end_date="2024-01-02",
            output_dir=str(tmp_path),
        )


def test_duplicate_stations_are_collapsed(tmp_path):
    fake = _FakeQualarClient({})
    source = CetesbQualarHorarioDataSource(output_path=str(tmp_path), client=fake)
    source.download(
        stations=["Pinheiros", "pinheiros", 99], parameters=["MP10"],
        start_date="2024-01-01", end_date="2024-01-02", output_dir=str(tmp_path),
    )
    assert len(fake.calls) == 1


# --- Credentials ------------------------------------------------------------


def test_missing_credentials_name_the_variable_and_the_registration_page(tmp_path, monkeypatch):
    monkeypatch.delenv("GUARACI_QUALAR_LOGIN", raising=False)
    monkeypatch.delenv("GUARACI_QUALAR_SENHA", raising=False)
    source = CetesbQualarHorarioDataSource(output_path=str(tmp_path))
    with pytest.raises(ValueError) as excinfo:
        source.download(
            stations=["Pinheiros"], start_date="2024-01-01", end_date="2024-01-02",
            output_dir=str(tmp_path),
        )
    message = str(excinfo.value)
    assert "GUARACI_QUALAR_LOGIN" in message
    assert REGISTRATION_URL in message


def test_credentials_are_never_exposed_as_job_parameters():
    """A job parameter is persisted to the manifest and the job history."""
    from guaraci.services.downloads import DownloadService

    names = {
        p["name"]
        for p in DownloadService().get_source_schema("cetesb_qualar_horario")["params"]
    }
    for forbidden in ("login", "senha", "password", "usuario", "credential"):
        assert not any(forbidden in name.lower() for name in names)


# --- Registration -----------------------------------------------------------


def test_source_is_registered_with_its_own_mode_and_theme():
    from guaraci.services.downloads import DownloadService

    descriptors = {d.source: d for d in DownloadService().list_sources()}
    entry = descriptors["cetesb_qualar_horario"]
    assert entry.mode == "cetesb qualar auth"
    assert "qualidade_ar" in entry.themes


def test_schema_says_concentration_and_offers_the_meteorological_parameters():
    from guaraci.services.downloads import DownloadService

    schema = DownloadService().get_source_schema("cetesb_qualar_horario")
    params = {p["name"]: p for p in schema["params"]}
    assert "CONCENTRAÇÃO" in params["parameters"]["description"]
    assert {"TEMP", "UR", "VV"} <= set(params["parameters"]["allowed_values"])
    assert params["stations"]["required"] is True
