"""Tests for `guaraci.datasus.ftp.dbc`.

The DBC decoder is a façade over ``pyreaddbc.dbc2dbf`` (DBC -> DBF) and
``dbfread.DBF`` (DBF -> records). To avoid carrying a binary fixture we
patch both with in-memory stand-ins.
"""

from __future__ import annotations

import sys
import types

import polars as pl
import pytest

from guaraci.datasus.ftp import dbc


@pytest.fixture
def fake_pipeline(monkeypatch, tmp_path):
    """Install fakes for ``pyreaddbc`` and ``dbfread`` for one test."""

    def _install(records, *, fail_polars_constructor: bool = False):
        # 1) pyreaddbc.dbc2dbf: pretend to convert DBC into a DBF whose path
        # we control. The DBF file is never actually parsed because we also
        # fake dbfread.DBF below.
        produced: dict[str, str] = {}

        def fake_dbc2dbf(src: str, dst: str) -> None:
            produced["src"] = src
            produced["dst"] = dst
            # Write a 1-byte placeholder so the path exists for hygiene checks.
            with open(dst, "wb") as fh:
                fh.write(b"\x00")

        fake_pyreaddbc = types.SimpleNamespace(dbc2dbf=fake_dbc2dbf)
        monkeypatch.setitem(sys.modules, "pyreaddbc", fake_pyreaddbc)

        # 2) dbfread.DBF: yield the pre-canned records.
        class FakeDBF:
            def __init__(self, filename: str, **kwargs):
                self.filename = filename
                self.kwargs = kwargs

            def __iter__(self):
                return iter(records)

            def __len__(self) -> int:
                return len(records)

        fake_dbfread = types.SimpleNamespace(DBF=FakeDBF)
        monkeypatch.setitem(sys.modules, "dbfread", fake_dbfread)

        # 3) Optionally force the pl.DataFrame(list[dict]) path to fail so we
        # exercise the pandas fallback.
        if fail_polars_constructor:
            original_ctor = pl.DataFrame

            def boom(records=None, *args, **kwargs):
                if isinstance(records, list) and records and isinstance(records[0], dict):
                    raise ValueError("forced failure for pandas fallback")
                return original_ctor(records, *args, **kwargs)

            monkeypatch.setattr(pl, "DataFrame", boom)

        # 4) The source ``.dbc`` itself must exist (we check it).
        src = tmp_path / "RDSP2401.dbc"
        src.write_bytes(b"\x00")
        return src, produced

    return _install


def test_dbc_read_returns_polars_dataframe(fake_pipeline) -> None:
    records = [
        {"UF_ZI": "35", "MUNIC_RES": "355030", "ANO_CMPT": "2024", "MES_CMPT": "01"},
        {"UF_ZI": "33", "MUNIC_RES": "330455", "ANO_CMPT": "2024", "MES_CMPT": "01"},
    ]
    src, produced = fake_pipeline(records)

    df = dbc.read(src)

    assert isinstance(df, pl.DataFrame)
    assert df.height == 2
    assert set(df.columns) == {"UF_ZI", "MUNIC_RES", "ANO_CMPT", "MES_CMPT"}
    # The temp DBF must have been the one our pyreaddbc fake was asked to produce.
    assert produced["src"] == str(src)
    assert produced["dst"].endswith("RDSP2401.dbc".replace(".dbc", ".dbf"))


def test_dbc_read_returns_empty_dataframe_when_no_records(fake_pipeline) -> None:
    src, _ = fake_pipeline([])
    df = dbc.read(src)
    assert isinstance(df, pl.DataFrame)
    assert df.height == 0


def test_dbc_read_pandas_fallback_on_constructor_failure(fake_pipeline) -> None:
    records = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    src, _ = fake_pipeline(records, fail_polars_constructor=True)
    df = dbc.read(src)
    # `pl.DataFrame` itself is monkeypatched in this test, so we cannot use
    # isinstance — duck-type the result instead.
    assert df.height == 2
    assert set(df.columns) == {"a", "b"}
    assert hasattr(df, "write_parquet")  # the polars API surface we rely on


def test_dbc_read_raises_filenotfound_for_missing_source(tmp_path) -> None:
    missing = tmp_path / "does-not-exist.dbc"
    with pytest.raises(FileNotFoundError):
        dbc.read(missing)
