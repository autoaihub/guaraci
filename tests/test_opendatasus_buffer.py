"""Regressões do acumulador de páginas do OpenDataSUS e da visibilidade dos avisos.

Medido contra `/arboviroses/dengue`: cada registro custa cerca de 11 KB como
dicionário em memória, e o ano de 2024 tem mais de 4 milhões deles, o que
projeta cerca de 45 GB. A coleta morria por memória depois de horas, e o
truncamento no limite de páginas era reportado como sucesso.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from guaraci.core.results import JobResult
from guaraci.opendatasus.buffer import PagedRecordBuffer


def _rows(quantidade: int, inicio: int = 0):
    return [
        {"id": str(i), "uf": "SP" if i % 2 else "RJ", "valor": i}
        for i in range(inicio, inicio + quantidade)
    ]


# --- acumulação em memória (coletas pequenas) --------------------------------


def test_small_collection_stays_in_memory() -> None:
    buffer = PagedRecordBuffer(spill_threshold=1000)
    buffer.extend(_rows(10))

    assert len(buffer) == 10
    assert not buffer.spilled
    assert len(buffer.records) == 10
    assert isinstance(buffer.frame(), pl.DataFrame)


def test_empty_buffer_is_falsy() -> None:
    buffer = PagedRecordBuffer()
    assert not buffer
    assert len(buffer) == 0


def test_extending_with_nothing_is_a_no_op() -> None:
    buffer = PagedRecordBuffer(spill_threshold=2)
    buffer.extend([])
    assert not buffer.spilled
    assert len(buffer) == 0


# --- derramamento (coletas grandes) ------------------------------------------


def test_crossing_the_threshold_spills_to_disk(tmp_path) -> None:
    buffer = PagedRecordBuffer(spill_threshold=100, spill_dir=tmp_path)
    for pagina in range(5):
        buffer.extend(_rows(100, inicio=pagina * 100))

    assert buffer.spilled
    assert len(buffer) == 500
    # O ponto da correção: os registros não seguem residentes em memória.
    assert buffer.records == []
    assert list(tmp_path.glob("*.parquet"))


def test_spilled_buffer_returns_a_lazy_plan(tmp_path) -> None:
    buffer = PagedRecordBuffer(spill_threshold=100, spill_dir=tmp_path)
    buffer.extend(_rows(250))

    frame = buffer.frame()
    assert isinstance(frame, pl.LazyFrame)
    assert frame.collect().height == 250


def test_spilled_content_matches_what_went_in(tmp_path) -> None:
    esperado = _rows(250)
    buffer = PagedRecordBuffer(spill_threshold=100, spill_dir=tmp_path)
    buffer.extend(esperado)

    obtido = buffer.frame().collect().sort("valor")
    assert obtido.height == len(esperado)
    assert obtido["id"].to_list() == [r["id"] for r in esperado]


def test_iter_records_walks_spilled_and_pending_rows(tmp_path) -> None:
    buffer = PagedRecordBuffer(spill_threshold=100, spill_dir=tmp_path)
    buffer.extend(_rows(150))  # 100 vão para disco, 50 ficam pendentes

    percorridos = list(buffer.iter_records())
    assert len(percorridos) == 150


def test_write_jsonl_covers_every_record(tmp_path) -> None:
    buffer = PagedRecordBuffer(spill_threshold=100, spill_dir=tmp_path / "parts")
    buffer.extend(_rows(250))

    destino = buffer.write_jsonl(tmp_path / "raw" / "amostra.jsonl")
    linhas = destino.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 250
    assert json.loads(linhas[0])["id"] == "0"


def test_cleanup_removes_owned_parts() -> None:
    buffer = PagedRecordBuffer(spill_threshold=10)
    buffer.extend(_rows(50))
    assert buffer.spilled

    buffer.cleanup()
    assert not buffer.spilled


# --- avisos e status visíveis ------------------------------------------------


def test_truncated_result_is_not_reported_as_clean_success() -> None:
    result = JobResult.from_payload(
        source="dengue",
        payload={
            "documents_found": 250_000,
            "downloaded_count": 250_000,
            "truncated": True,
            "warnings": ["reached max_pages limit"],
        },
    )
    assert result.truncated is True
    assert result.status == "partial_success"
    assert result.warnings == ["reached max_pages limit"]


def test_complete_result_stays_a_success() -> None:
    result = JobResult.from_payload(
        source="dengue",
        payload={"documents_found": 10, "downloaded_count": 10, "truncated": False},
    )
    assert result.status == "success"
    assert result.warnings == []


def test_warnings_fall_back_to_the_legacy_single_field() -> None:
    result = JobResult.from_payload(
        source="sinan",
        payload={"documents_found": 1, "export_warning": "No processed file was exported."},
    )
    assert result.warnings == ["No processed file was exported."]


def test_warnings_reach_the_serialized_payload() -> None:
    result = JobResult.from_payload(
        source="dengue",
        payload={"documents_found": 0, "warnings": ["nada retornado"], "truncated": True},
    )
    payload = result.to_dict()
    assert payload["warnings"] == ["nada retornado"]
    assert payload["status"] == "partial_success"
