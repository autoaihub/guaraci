"""Testes offline da fonte MI Social (MDS/SAGI), com cliente falso."""

from __future__ import annotations

import csv
import io
from datetime import date
from urllib.parse import parse_qs

import polars as pl
import pytest

from guaraci.mds import CAMPOS_CHAVE, GRUPOS, MisocialClient, MisocialDataSource, campos_dos_grupos
from guaraci.mds import misocial as misocial_mod
from guaraci.mds.misocial import MisocialClientError

BPC = GRUPOS["bpc"]


def _csv(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


class FakeClient:
    """Responde por mês; ``months`` mapeia AAAAMM -> lista de dicts por município."""

    base_url = "https://fake/misocial/"

    def __init__(self, months, *, extra_column=None):
        self.months = months
        self.calls = []
        self.extra_column = extra_column

    def select_csv(self, *, fq, fields, start=0, rows=misocial_mod.PAGE_ROWS):
        anomes = fq.split(":", 1)[1]
        self.calls.append((anomes, start, rows))
        # O Solr devolve as colunas em outra ordem; o leitor remapeia pelo nome.
        header = list(reversed(fields))
        if self.extra_column:
            header.append(self.extra_column)
        docs = self.months.get(anomes, [])[start:start + rows]
        return _csv(header, [[doc.get(name, "") for name in header] for doc in docs])


def _doc(anomes, ibge, **values):
    doc = {"anomes_s": anomes, "codigo_ibge": ibge, "sigla_uf": "SP", "municipio": "X"}
    doc.update(values)
    return doc


def _rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_campos_dos_grupos_ordem_e_validacao():
    assert campos_dos_grupos(None) == tuple(c for campos in GRUPOS.values() for c in campos)
    assert campos_dos_grupos(["condicionalidades", "bpc"]) == (
        *GRUPOS["bpc"], *GRUPOS["condicionalidades"]
    )
    with pytest.raises(ValueError, match="desconhecido"):
        campos_dos_grupos(["saude"])
    todos = [c for campos in GRUPOS.values() for c in campos]
    assert len(todos) == len(set(todos))
    assert not set(todos) & set(CAMPOS_CHAVE)
    assert "sicon_qtde_gestantes_prenatal_em_dia_apartir_2023_l" in GRUPOS["condicionalidades"]
    assert "bpc_ben_i" in GRUPOS["bpc"]


def test_download_meses_vazios_parciais_e_futuros(tmp_path):
    cheio = {name: "7" for name in BPC}
    months = {
        "202607": [_doc("202607", "110001", **cheio), _doc("202607", "355030", **cheio)],
        # Mês recém-aberto: só três campos preenchidos.
        "202608": [_doc("202608", "110001", bpc_residencia_total_i="5",
                        bpc_residencia_quantidade_idosos_i="1",
                        bpc_residencia_quantidade_deficientes_i="4", bpc_ben_i="0")],
        # Documento-esqueleto: tudo zerado.
        "202609": [_doc("202609", "110001", bpc_ben_i="0", bpc_val_f="0.0")],
    }
    client = FakeClient(months)
    events = []
    payload = MisocialDataSource(output_path=str(tmp_path), client=client).download(
        start_year=2026, grupos=["bpc"], today=date(2026, 9, 20),
        progress_callback=events.append,
    )
    # Meses depois de 202609 nem são pedidos.
    assert [call[0] for call in client.calls] == [f"2026{m:02d}" for m in range(1, 10)]
    assert payload["documents_found"] == 9
    assert payload["downloaded_count"] == 2
    assert payload["empty_months"] == [f"2026{m:02d}" for m in range(1, 7)] + ["202609"]
    assert payload["partial_months"] == ["202608"]
    assert payload["columns"] == len(CAMPOS_CHAVE) + len(BPC)
    warning = payload["export_warning"]
    assert "202609" in warning and "202608 (3 de 29)" in warning
    assert "3 mês(es) posteriores a 202609" in warning
    rows = _rows(payload["exported_files"][0])
    assert list(rows[0]) == [*CAMPOS_CHAVE, *BPC]
    assert [(r["anomes_s"], r["codigo_ibge"]) for r in rows] == [
        ("202607", "110001"), ("202607", "355030"), ("202608", "110001"),
    ]
    assert rows[0]["bpc_ben_i"] == "7" and rows[0]["uf"] == ""
    assert events[0]["event"] == "download_start" and events[-1]["files_completed"] == 9


def test_mes_magro_antigo_nao_e_avisado(tmp_path):
    # Periodicidade do campo (saúde semestral), não carga pendente.
    cheio = {name: "7" for name in BPC}
    months = {
        "202405": [_doc("202405", "110001", **cheio)],
        "202406": [_doc("202406", "110001", bpc_ben_i="3")],
    }
    payload = MisocialDataSource(output_path=str(tmp_path), client=FakeClient(months)).download(
        start_year=2024, grupos=["bpc"], today=date(2026, 10, 20)
    )
    assert payload["partial_months"] == []
    assert payload["downloaded_count"] == 2


def test_download_pagina_por_start(tmp_path, monkeypatch):
    monkeypatch.setattr(misocial_mod, "PAGE_ROWS", 2)
    docs = [_doc("200301", f"1100{i:02d}", bpc_ben_i=str(i + 1)) for i in range(5)]
    client = FakeClient({"200301": docs})
    payload = MisocialDataSource(output_path=str(tmp_path), client=client).download(
        start_year=2003, grupos=["bpc"], today=date(2003, 1, 31)
    )
    assert client.calls == [("200301", 0, 2), ("200301", 2, 2), ("200301", 4, 2)]
    assert payload["rows"] == 5
    assert [r["bpc_ben_i"] for r in _rows(payload["exported_files"][0])] == list("12345")


def test_download_coluna_fora_da_lista_falha_o_mes(tmp_path):
    client = FakeClient({"202401": [_doc("202401", "1", bpc_ben_i="1")]}, extra_column="intruso_i")
    payload = MisocialDataSource(output_path=str(tmp_path), client=client).download(
        start_year=2024, grupos=["bpc"], today=date(2024, 1, 5)
    )
    assert payload["failed_count"] == 1
    assert payload["exported_files"] == []
    assert "intruso_i" in payload["export_warning"]


def test_download_parquet_tudo_texto(tmp_path):
    client = FakeClient({"202401": [_doc("202401", "110001", bpc_ben_i="12", bpc_val_f="3.5")]})
    payload = MisocialDataSource(output_path=str(tmp_path), client=client).download(
        start_year=2024, grupos=["bpc"], output_format="parquet", today=date(2024, 1, 5)
    )
    frame = pl.read_parquet(payload["exported_files"][0])
    assert frame.height == 1
    assert all(dtype == pl.String for dtype in frame.dtypes)
    assert frame["codigo_ibge"][0] == "110001" and frame["bpc_val_f"][0] == "3.5"
    assert not (tmp_path / "mds_misocial.csv").exists()


def test_download_rejeita_ano_antes_do_piso(tmp_path):
    with pytest.raises(ValueError, match="2003"):
        MisocialDataSource(output_path=str(tmp_path), client=FakeClient({})).download(
            start_year=2002
        )


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_client_faz_post_com_lista_de_campos(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["body"] = parse_qs(request.data.decode("ascii"))
        return _Response("anomes_s,codigo_ibge\n202401,110001\n".encode("utf-8"))

    monkeypatch.setattr(misocial_mod, "urlopen", fake_urlopen)
    text = MisocialClient().select_csv(fq="anomes_s:202401", fields=["anomes_s", "codigo_ibge"])
    assert text.startswith("anomes_s,codigo_ibge")
    assert seen["method"] == "POST"
    assert seen["body"]["fl"] == ["anomes_s,codigo_ibge"]
    assert seen["body"]["wt"] == ["csv"] and seen["body"]["start"] == ["0"]


def test_client_html_vira_erro(monkeypatch):
    monkeypatch.setattr(
        misocial_mod, "urlopen", lambda request, timeout: _Response(b"<html>manutencao</html>")
    )
    with pytest.raises(MisocialClientError, match="HTML"):
        MisocialClient(max_attempts=1).select_csv(fq="anomes_s:202401", fields=["anomes_s"])


def test_fonte_registrada_no_servico():
    from guaraci.services.downloads import DownloadService

    schema = DownloadService().get_source_schema("mds_misocial")
    params = {p["name"]: p for p in schema["params"]}
    assert params["start_year"]["minimum"] == 2003
    assert params["grupos"]["allowed_values"] == list(GRUPOS)
    assert params["grupos"]["type"] == "string_list"
