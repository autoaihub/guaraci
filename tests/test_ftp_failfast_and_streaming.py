"""Regressões da coleta longa do DATASUS via FTP.

Cobre os dois defeitos observados numa coleta real de dengue (SINAN,
2014-2024, 757 MB): a ausência da dependência de decodificação só era
percebida depois de baixar tudo, e o decodificador mantinha o arquivo
inteiro em memória.
"""

from __future__ import annotations

import asyncio

import polars as pl
import pytest

from guaraci.datasus.ftp import FtpEntry, dbc
from guaraci.datasus.ftp.catalog import FileRecord, System
from guaraci.datasus.ftp.orchestration import download_records


class CountingClient:
    """Cliente FTP falso que registra quantos arquivos foram transferidos."""

    def __init__(self) -> None:
        self.downloads: list[str] = []

    async def __aenter__(self) -> "CountingClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def list_dir(self, path: str) -> list[FtpEntry]:
        return []

    async def download(self, path: str, dest) -> None:
        self.downloads.append(path)
        dest.write_bytes(b"\x00")


def _records(count: int) -> list[FileRecord]:
    return [
        FileRecord(
            basename=f"DENGBR{14 + i}.dbc",
            system=System.SINAN,
            group="DENG",
            state=None,
            year=2014 + i,
            path=f"/dissemin/publicos/SINAN/DADOS/FINAIS/DENGBR{14 + i}.dbc",
        )
        for i in range(count)
    ]


def test_missing_decoder_aborts_before_downloading_everything(tmp_path, monkeypatch) -> None:
    """Sem pyreaddbc, a coleta para no início em vez de baixar tudo à toa."""

    def _no_decoder() -> None:
        raise dbc.DbcDependencyError("pyreaddbc ausente")

    monkeypatch.setattr(dbc, "ensure_available", _no_decoder)

    client = CountingClient()
    with pytest.raises(dbc.DbcDependencyError):
        asyncio.run(
            download_records(
                client,
                _records(11),
                cache_dir=tmp_path,
                dbc_reader=dbc.read,
            )
        )

    # O ponto da correção: nenhum byte transferido, não 757 MB descartados.
    assert client.downloads == []


def test_decoder_import_error_mid_run_aborts_instead_of_partial_success(tmp_path) -> None:
    """ImportError durante a decodificação encerra a coleta, sem sucesso parcial."""

    def _reader_missing_dep(_path):
        raise ImportError("dbfread is required for DBC decoding")

    client = CountingClient()
    with pytest.raises(ImportError):
        asyncio.run(
            download_records(
                client,
                _records(11),
                cache_dir=tmp_path,
                dbc_reader=_reader_missing_dep,
            )
        )

    # Falhou no primeiro arquivo; os dez seguintes não foram buscados.
    assert len(client.downloads) == 1


def test_transient_failure_still_yields_partial_success(tmp_path) -> None:
    """Erro comum de um arquivo continua sendo tolerado, como antes."""
    calls = {"n": 0}

    def _reader_flaky(_path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("conexão caiu neste arquivo")
        return pl.DataFrame({"COD": ["355030"]})

    client = CountingClient()
    result = asyncio.run(
        download_records(
            client,
            _records(3),
            cache_dir=tmp_path,
            dbc_reader=_reader_flaky,
        )
    )

    assert result["successful_downloads"] == 2
    assert len(result["failed_downloads"]) == 1
    assert len(client.downloads) == 3


def test_ensure_available_passes_when_dependencies_present() -> None:
    pytest.importorskip("pyreaddbc")
    pytest.importorskip("dbfread")
    dbc.ensure_available()  # não deve levantar


def test_decode_to_parquet_matches_read(tmp_path, monkeypatch) -> None:
    """A escrita em streaming produz o mesmo conteúdo do caminho em memória."""
    records = [{"UF": "35", "N": str(i)} for i in range(250)]

    import sys
    import types

    class FakeDBF:
        def __init__(self, filename, **kwargs) -> None:
            self.filename = filename

        def __iter__(self):
            return iter(records)

    monkeypatch.setitem(sys.modules, "dbfread", types.SimpleNamespace(DBF=FakeDBF))
    # Chunk pequeno para forçar múltiplas partes na escrita em streaming.
    monkeypatch.setattr(dbc, "_CHUNK_ROWS", 100)

    src = tmp_path / "DENGBR24.dbf"
    src.write_bytes(b"\x00")
    dest = tmp_path / "DENGBR24.parquet"

    dbc.decode_to_parquet(src, dest)

    streamed = pl.read_parquet(dest)
    eager = dbc.read(src)
    assert streamed.height == len(records)
    assert streamed.sort("N").equals(eager.sort("N"))


def test_decode_to_parquet_raises_for_missing_source(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        dbc.decode_to_parquet(tmp_path / "ausente.dbc", tmp_path / "saida.parquet")


def test_merge_stays_streaming_when_chunk_schemas_diverge(tmp_path, monkeypatch) -> None:
    """Colunas vazias num chunk e preenchidas noutro não podem forçar o fallback.

    É o caso real de ``DT_GRAV`` no SINAN: inferida como ``Null`` no primeiro
    chunk e como ``Date`` no seguinte. Com o merge exigindo schema idêntico, a
    junção caía no caminho em memória e o pico voltava a acompanhar o arquivo
    inteiro (medido: 1400 MB em streaming contra 4114 MB no fallback).
    """
    import datetime
    import sys
    import types

    # Primeiro chunk só com nulos na coluna de data; segundo chunk com datas.
    records = [{"ID": str(i), "DT_GRAV": None} for i in range(100)]
    records += [
        {"ID": str(i), "DT_GRAV": datetime.date(2023, 1, 1)} for i in range(100, 200)
    ]

    class FakeDBF:
        def __init__(self, filename, **kwargs) -> None:
            self.filename = filename

        def __iter__(self):
            return iter(records)

    monkeypatch.setitem(sys.modules, "dbfread", types.SimpleNamespace(DBF=FakeDBF))
    monkeypatch.setattr(dbc, "_CHUNK_ROWS", 100)

    def _fallback_used(*args, **kwargs):
        raise AssertionError("o merge caiu no fallback em memória")

    monkeypatch.setattr(pl, "read_parquet", _fallback_used)

    src = tmp_path / "DENGBR23.dbf"
    src.write_bytes(b"\x00")
    dest = tmp_path / "DENGBR23.parquet"

    dbc.decode_to_parquet(src, dest)

    monkeypatch.undo()
    result = pl.read_parquet(dest)
    assert result.height == 200
    assert result["DT_GRAV"].null_count() == 100
