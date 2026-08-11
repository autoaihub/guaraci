import polars as pl
import pytest
from guaraci.datasus.sih import (
    DEFAULT_SIH_RD_COLUMN_MAP,
    SihDataSource,
    apply_sih_column_map,
)


def test_default_sih_rd_column_map_keys() -> None:
    assert "N_AIH" in DEFAULT_SIH_RD_COLUMN_MAP
    assert "DT_INTER" in DEFAULT_SIH_RD_COLUMN_MAP
    assert "DT_SAIDA" in DEFAULT_SIH_RD_COLUMN_MAP
    assert "MUNIC_RES" in DEFAULT_SIH_RD_COLUMN_MAP
    assert "DIAG_PRINC" in DEFAULT_SIH_RD_COLUMN_MAP


def test_apply_sih_column_map_default() -> None:
    raw_df = pl.DataFrame({
        "N_AIH": ["123456"],
        "DT_INTER": ["20230101"],
        "DT_SAIDA": ["20230105"],
        "MUNIC_RES": ["355030"],
        "DIAG_PRINC": ["A90"],
        "UNMAPPED_FIELD": ["test"],
    })

    mapped = apply_sih_column_map(raw_df)

    assert "numero_aih" in mapped.columns
    assert "data_internacao" in mapped.columns
    assert "data_saida" in mapped.columns
    assert "municipio_residencia" in mapped.columns
    assert "diagnostico_principal" in mapped.columns
    assert "UNMAPPED_FIELD" in mapped.columns
    assert "N_AIH" not in mapped.columns


def test_apply_sih_column_map_custom_override() -> None:
    raw_df = pl.DataFrame({
        "N_AIH": ["123456"],
        "DT_INTER": ["20230101"],
    })

    custom_map = {"N_AIH": "custom_aih_id"}
    mapped = apply_sih_column_map(raw_df, column_map=custom_map)

    assert "custom_aih_id" in mapped.columns
    assert "DT_INTER" in mapped.columns


def test_sih_datasource_instance_method() -> None:
    ds = SihDataSource()
    raw_df = pl.DataFrame({"MUNIC_RES": ["355030"], "SEXO": ["1"]})
    mapped = ds.apply_column_map(raw_df)

    assert "municipio_residencia" in mapped.columns
    assert "sexo" in mapped.columns
