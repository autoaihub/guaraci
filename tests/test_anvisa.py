"""Fontes de arquivos abertos da ANVISA, sem rede.

Os casos que valem teste são os que produziriam dado plausível e errado:
o preâmbulo do CMED lido como linha de dado, acento cp1252 corrompido, zero
à esquerda perdido por inferência de tipo, e ``;`` dentro de campo entre
aspas partindo a coluna.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from guaraci.anvisa import ANVISA_FILES, AnvisaFileDataSource, datasource_for
from guaraci.anvisa.client import RemoteFile
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.model import Cadence, Kind
from guaraci.services.downloads import DownloadService


class _Client:
    """Serve bytes fixos no lugar de dados.anvisa.gov.br."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.downloads = 0

    def head(self, filename: str) -> RemoteFile:
        return RemoteFile(url=f"https://x/{filename}", size=len(self.payload), last_modified="Wed")

    def download(self, filename: str, destination: Path, **_kwargs) -> int:
        self.downloads += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)
        return len(self.payload)


_VIGIMED = (
    "UF;TIPO_ENTRADA_VIGIMED;DATA_NOTIFICACAO;PESO_KG\r\n"
    "SP;Empresas Farmacêuticas;09/28/2023 00:00:00.000000;068.0\r\n"
    "PA;Cidadão;None;\r\n"
).encode("cp1252")

_CMED = (
    "﻿Secretaria Executiva - CMED;;;\r\n"
    "LISTA DE PREÇOS DE MEDICAMENTOS;;;\r\n"
    "Publicada em 21/07/2026 17h30min.;;;\r\n"
    ";;;\r\n"
    "SUBSTÂNCIA;CNPJ;EAN 1;PF 0%\r\n"
    '"21-ACETATO DE DEXAMETASONA;CLOTRIMAZOL";18.459.628/0001-15;0789;12,34\r\n'
).encode("utf-8")


def _run(tmp_path: Path, key: str, payload: bytes, **kwargs) -> dict:
    source = AnvisaFileDataSource(output_path=str(tmp_path), dataset=key, client=_Client(payload))
    return source.download(output_dir=str(tmp_path), **kwargs)


def test_cp1252_file_exports_utf8_with_every_column_as_text(tmp_path):
    result = _run(tmp_path, "anvisa_vigimed_notificacoes", _VIGIMED, output_format="parquet")
    frame = pl.read_parquet(result["exported_files"][0])
    assert frame["TIPO_ENTRADA_VIGIMED"].to_list() == ["Empresas Farmacêuticas", "Cidadão"]
    assert frame["PESO_KG"][0] == "068.0"  # texto: nada de 68.0
    assert frame["DATA_NOTIFICACAO"][1] == "None"  # nulo literal da fonte, preservado
    assert all(dtype == pl.String for dtype in frame.dtypes)


def test_cmed_preamble_is_skipped_and_quoted_semicolon_survives(tmp_path):
    result = _run(tmp_path, "anvisa_cmed_precos", _CMED, output_format="csv")
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.columns == ["SUBSTÂNCIA", "CNPJ", "EAN 1", "PF 0%"]
    assert frame.height == 1
    assert frame["SUBSTÂNCIA"][0] == "21-ACETATO DE DEXAMETASONA;CLOTRIMAZOL"
    assert frame["EAN 1"][0] == "0789"


def test_missing_cmed_header_is_an_explicit_error(tmp_path):
    with pytest.raises(ValueError, match="SUBST"):
        _run(tmp_path, "anvisa_cmed_precos", b"so preambulo;;\r\n", output_format="csv")


def test_raw_file_is_dropped_after_export_unless_kept(tmp_path):
    _run(tmp_path, "anvisa_vigimed_notificacoes", _VIGIMED, output_format="csv")
    assert not (tmp_path / "VigiMed_Notificacoes.csv").exists()
    assert not list(tmp_path.glob("*.tmp.csv"))
    kept = tmp_path / "kept"
    _run(kept, "anvisa_vigimed_notificacoes", _VIGIMED, output_format="csv", keep_raw=True)
    assert (kept / "VigiMed_Notificacoes.csv").read_bytes() == _VIGIMED  # intacto, cp1252


def test_unchanged_file_is_not_downloaded_again(tmp_path):
    client = _Client(_VIGIMED)
    source = AnvisaFileDataSource(output_path=str(tmp_path), dataset="anvisa_vigimed_notificacoes", client=client)
    source.download(output_dir=str(tmp_path))
    second = source.download(output_dir=str(tmp_path))
    assert client.downloads == 1
    assert second["skipped_count"] == 1


def test_unknown_format_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="output_format"):
        _run(tmp_path, "anvisa_vigimed_notificacoes", _VIGIMED, output_format="xlsx")


def test_every_file_is_registered_as_a_monthly_snapshot():
    service = DownloadService()
    registered = {d.source for d in service.list_sources() if d.mode == "anvisa files"}
    assert registered == set(ANVISA_FILES)
    for key in ANVISA_FILES:
        profile = profile_for(key, "anvisa files")
        assert profile.kind is Kind.SNAPSHOT and profile.cadence is Cadence.MONTHLY


def test_notivisa_without_header_is_deliberately_absent():
    assert all("notivisa" not in spec.filename.lower() for spec in ANVISA_FILES.values())


def test_datasource_for_fixes_the_dataset(tmp_path):
    cls = datasource_for("anvisa_hemovigilancia")
    assert cls(output_path=str(tmp_path)).spec.filename == "DADOS_ABERTOS_HEMOVIGILANCIA.csv"


def test_stray_quote_in_unquoted_file_stays_inside_its_field(tmp_path):
    """VigiMed: ``"500" Dosage unit...`` engolia o resto do arquivo como um campo."""
    payload = (
        'ID;POSOLOGIA;VIA\r\n'
        'BR-1;"500" Dosage unit and frequency were not provided.;Oral\r\n'
        'BR-2;1 comprimido;Oral\r\n'
    ).encode("cp1252")
    result = _run(tmp_path, "anvisa_vigimed_medicamentos", payload, output_format="parquet")
    frame = pl.read_parquet(result["exported_files"][0])
    assert frame.height == 2
    assert frame["POSOLOGIA"][0] == '"500" Dosage unit and frequency were not provided.'
    assert frame["VIA"].to_list() == ["Oral", "Oral"]


def test_internal_list_separator_is_kept_inside_the_field(tmp_path):
    """Tecnovigilância publica listas "A ; B" sem aspas; ';;' continua separando."""
    payload = (
        "ANO;CATEGORIA;VAZIO;OCORRENCIA_NIVEL_1;OCORRENCIA_NIVEL_2;UF\r\n"
        "2018;Artigo ;;FUNÇÃO NÃO PRETENDIDA ; OUTROS;IGNORADO ; OUTROS ; MECÂNICO;SP\r\n"
        "2019;Equipamento;;SIMPLES;OUTRO;RJ\r\n"
    ).encode("cp1252")
    result = _run(tmp_path, "anvisa_tecnovigilancia", payload, output_format="parquet")
    frame = pl.read_parquet(result["exported_files"][0])
    assert frame["OCORRENCIA_NIVEL_1"][0] == "FUNÇÃO NÃO PRETENDIDA ; OUTROS"
    assert frame["OCORRENCIA_NIVEL_2"][0] == "IGNORADO ; OUTROS ; MECÂNICO"
    assert frame["CATEGORIA"][0] == "Artigo "
    assert frame["UF"].to_list() == ["SP", "RJ"]


def test_row_that_still_does_not_fit_is_set_aside_not_guessed(tmp_path):
    """Tecnovigilância, linha 84 048: ';' sem espaços no nome técnico do produto."""
    payload = "A;B;C\r\n1;2;3\r\nx;OSTEOSSINTESE;LIGAMENTO;z\r\n4;5;6\r\n".encode("cp1252")
    result = _run(tmp_path, "anvisa_hemovigilancia", payload, output_format="csv")
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame["A"].to_list() == ["1", "4"]
    assert result["rejected_rows"] == 1
    rejects = Path(result["rejected_file"]).read_text(encoding="utf-8")
    assert rejects.splitlines()[1] == "3;x;OSTEOSSINTESE;LIGAMENTO;z"
    assert "1 linha(s)" in result["export_warning"]


def test_clean_file_leaves_no_rejects_file(tmp_path):
    result = _run(tmp_path, "anvisa_vigimed_notificacoes", _VIGIMED, output_format="csv")
    assert result["rejected_rows"] == 0 and result["rejected_file"] is None
    assert not list(tmp_path.glob("*.rejeitadas.csv"))
