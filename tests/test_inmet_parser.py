"""Tests for guaraci.inmet.parser (pure, offline).

Fixture text below is a trimmed excerpt of REAL data verified live on
2026-08-18 against https://portal.inmet.gov.br/uploads/dadoshistoricos/2025.zip
(station A701, Sao Paulo - Mirante) and .../2000.zip (station A001, Brasilia,
the earliest automatic-network year, which uses the older
``-9999``-sentinel/``YYYY-MM-DD``/``HH:MM`` format instead of the newer
``YYYY/MM/DD``/``HHMM UTC`` one).
"""
from __future__ import annotations

import pytest

from guaraci.inmet.parser import (
    InmetParseError,
    parse_date_token,
    parse_decimal,
    parse_hour_token,
    parse_station_csv,
    parse_station_filename,
    slugify,
)

# 2025-era CSV (recent format): comma decimals, empty-string missing values,
# 'Data'/'Hora UTC' header, YYYY/MM/DD dates, 'HHMM UTC' hours.
RECENT_CSV = (
    "REGIAO:;SE\r\n"
    "UF:;SP\r\n"
    "ESTACAO:;SAO PAULO - MIRANTE\r\n"
    "CODIGO (WMO):;A701\r\n"
    "LATITUDE:;-23,4962888\r\n"
    "LONGITUDE:;-46,6200666\r\n"
    "ALTITUDE:;785,64\r\n"
    "DATA DE FUNDACAO:;25/07/06\r\n"
    "Data;Hora UTC;PRECIPITACAO TOTAL, HORARIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (C);\r\n"
    "2025/01/01;0000 UTC;0;21,2;\r\n"
    "2025/01/01;0100 UTC;;21,1;\r\n"
).encode("latin-1")

# 2000-era CSV (oldest automatic-network format): -9999 sentinel, YYYY-MM-DD
# dates, HH:MM hours.
OLD_CSV = (
    "REGIAO:;CO\r\n"
    "UF:;DF\r\n"
    "ESTACAO:;BRASILIA\r\n"
    "CODIGO (WMO):;A001\r\n"
    "LATITUDE:;-15,78944444\r\n"
    "LONGITUDE:;-47,92583332\r\n"
    "ALTITUDE:;1159,54\r\n"
    "DATA DE FUNDACAO (YYYY-MM-DD):;2000-05-07\r\n"
    "DATA (YYYY-MM-DD);HORA (UTC);PRECIPITACAO TOTAL, HORARIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (C);\r\n"
    "2000-05-07;00:00;-9999;-9999;\r\n"
    "2000-05-07;01:00;0;18,4;\r\n"
).encode("latin-1")


def test_slugify_strips_accents_and_punctuation() -> None:
    assert slugify("PRECIPITAÇÃO TOTAL, HORÁRIO (mm)") == "precipitacao_total_horario_mm"
    assert slugify("Data") == "data"
    assert slugify("") == "col"


def test_parse_station_filename_matches_documented_pattern() -> None:
    info = parse_station_filename(
        "INMET_SE_SP_A701_SAO PAULO - MIRANTE_01-01-2025_A_31-12-2025.CSV"
    )
    assert info is not None
    assert info.region == "SE"
    assert info.uf == "SP"
    assert info.code == "A701"
    assert info.name == "SAO PAULO - MIRANTE"


def test_parse_station_filename_rejects_unrelated_names() -> None:
    assert parse_station_filename("readme.txt") is None
    assert parse_station_filename("2025") is None


@pytest.mark.parametrize(
    "raw,expected",
    [("925,1", 925.1), ("0", 0.0), ("", None), ("-9999", None), ("  21,2  ", 21.2)],
)
def test_parse_decimal(raw: str, expected) -> None:
    assert parse_decimal(raw) == expected


def test_parse_date_token_handles_both_eras() -> None:
    assert parse_date_token("2025/01/01") == "2025-01-01"
    assert parse_date_token("2000-05-07") == "2000-05-07"
    assert parse_date_token("") is None


def test_parse_hour_token_handles_both_eras() -> None:
    assert parse_hour_token("0000 UTC") == "00:00"
    assert parse_hour_token("00:00") == "00:00"
    assert parse_hour_token("garbage") is None


def test_parse_station_csv_recent_format() -> None:
    info = parse_station_filename(
        "INMET_SE_SP_A701_SAO PAULO - MIRANTE_01-01-2025_A_31-12-2025.CSV"
    )
    metadata, records, warnings = parse_station_csv(RECENT_CSV, year=2025, file_info=info)

    assert metadata["region"] == "SE"
    assert metadata["uf"] == "SP"
    assert metadata["station_name"] == "SAO PAULO - MIRANTE"
    assert metadata["station_code"] == "A701"
    assert warnings == []
    assert len(records) == 2

    first = records[0]
    assert first["date"] == "2025-01-01"
    assert first["hour_utc"] == "00:00"
    assert first["timestamp"] == "2025-01-01T00:00:00"
    assert first["latitude"] == pytest.approx(-23.4962888)
    assert first["precipitacao_total_horario_mm"] == 0.0
    assert first["temperatura_do_ar_bulbo_seco_horaria_c"] == pytest.approx(21.2)

    # Empty precipitation cell in the second row is null, not zero/garbage.
    assert records[1]["precipitacao_total_horario_mm"] is None


def test_parse_station_csv_old_format_with_sentinel_and_alt_dates() -> None:
    info = parse_station_filename("INMET_CO_DF_A001_BRASILIA_07-05-2000_A_31-12-2000.CSV")
    metadata, records, warnings = parse_station_csv(OLD_CSV, year=2000, file_info=info)

    assert metadata["founded_date"] == "2000-05-07"
    assert warnings == []
    assert len(records) == 2
    assert records[0]["date"] == "2000-05-07"
    assert records[0]["hour_utc"] == "00:00"
    # -9999 sentinel is treated as missing, not a real reading.
    assert records[0]["precipitacao_total_horario_mm"] is None
    assert records[0]["temperatura_do_ar_bulbo_seco_horaria_c"] is None
    assert records[1]["temperatura_do_ar_bulbo_seco_horaria_c"] == pytest.approx(18.4)


def test_parse_station_csv_rejects_too_short_file() -> None:
    info = parse_station_filename("INMET_SE_SP_A701_SAO PAULO_01-01-2025_A_31-12-2025.CSV")
    with pytest.raises(InmetParseError):
        parse_station_csv(b"one\ntwo\n", year=2025, file_info=info)
