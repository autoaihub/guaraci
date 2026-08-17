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


def test_chunked_read_concatenates_all_records(fake_decoders, tmp_path, monkeypatch) -> None:
    """Com _CHUNK_ROWS pequeno, múltiplos chunks devem concatenar sem perda."""
    import sys
    import types

    fake_dbfread = types.ModuleType("dbfread")
    records = [{"COD": str(i), "VAL": i} for i in range(7)]

    def _DBF(path, **kwargs):  # noqa: N802
        return iter(records)

    fake_dbfread.DBF = _DBF
    monkeypatch.setitem(sys.modules, "dbfread", fake_dbfread)

    from guaraci.datasus.ftp import dbc

    monkeypatch.setattr(dbc, "_CHUNK_ROWS", 3)
    src = tmp_path / "BIG.DBF"
    src.write_bytes(b"\x00")

    df = dbc.read(src)

    assert df.height == 7
    assert df["COD"].to_list() == [str(i) for i in range(7)]


def test_mixed_types_across_chunks(fake_decoders, tmp_path, monkeypatch) -> None:
    """Coluna nula no 1º chunk e texto no 2º não pode quebrar a concatenação."""
    import sys
    import types

    fake_dbfread = types.ModuleType("dbfread")
    records = [{"A": None}, {"A": None}, {"A": "x"}, {"A": "y"}]

    def _DBF(path, **kwargs):  # noqa: N802
        return iter(records)

    fake_dbfread.DBF = _DBF
    monkeypatch.setitem(sys.modules, "dbfread", fake_dbfread)

    from guaraci.datasus.ftp import dbc

    monkeypatch.setattr(dbc, "_CHUNK_ROWS", 2)
    src = tmp_path / "MIX.DBF"
    src.write_bytes(b"\x00")

    df = dbc.read(src)

    assert df.height == 4
    assert df["A"].to_list() == [None, None, "x", "y"]
