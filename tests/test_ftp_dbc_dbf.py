"""Tests for plain-DBF decoding in `guaraci.datasus.ftp.dbc` (phase 5).

Some systems (PNI) ship uncompressed ``.dbf`` directly, so ``read`` must
skip the ``pyreaddbc`` decompression step for them while still using it
for ``.dbc``. Both decoders (``pyreaddbc``/``dbfread``) are faked so the
test runs without the native deps.
"""

from __future__ import annotations

import sys
import types

import polars as pl
import pytest


@pytest.fixture
def fake_decoders(monkeypatch):
    """Inject fake ``dbfread`` and ``pyreaddbc`` modules; record dbc2dbf calls."""
    calls: dict[str, list] = {"dbc2dbf": []}

    fake_dbfread = types.ModuleType("dbfread")

    def _DBF(path, **kwargs):  # noqa: N802 - mimics dbfread.DBF
        return [{"COD": "355030", "VAL": 1}, {"COD": "330455", "VAL": 2}]

    fake_dbfread.DBF = _DBF

    fake_pyreaddbc = types.ModuleType("pyreaddbc")

    def _dbc2dbf(infile, outfile):
        calls["dbc2dbf"].append((infile, outfile))

    fake_pyreaddbc.dbc2dbf = _dbc2dbf

    monkeypatch.setitem(sys.modules, "dbfread", fake_dbfread)
    monkeypatch.setitem(sys.modules, "pyreaddbc", fake_pyreaddbc)
    return calls


def test_dbf_input_skips_pyreaddbc(fake_decoders, tmp_path) -> None:
    from guaraci.datasus.ftp import dbc

    src = tmp_path / "CPNISP19.DBF"
    src.write_bytes(b"\x00")

    df = dbc.read(src)

    assert isinstance(df, pl.DataFrame)
    assert df.height == 2
    assert fake_decoders["dbc2dbf"] == []  # decompression skipped for .dbf


def test_dbc_input_uses_pyreaddbc(fake_decoders, tmp_path) -> None:
    from guaraci.datasus.ftp import dbc

    src = tmp_path / "PASP2401.dbc"
    src.write_bytes(b"\x00")

    df = dbc.read(src)

    assert df.height == 2
    assert len(fake_decoders["dbc2dbf"]) == 1  # decompression invoked for .dbc


def test_missing_file_raises(fake_decoders, tmp_path) -> None:
    from guaraci.datasus.ftp import dbc

    with pytest.raises(FileNotFoundError):
        dbc.read(tmp_path / "nope.dbf")
