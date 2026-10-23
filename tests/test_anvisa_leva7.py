"""Fontes ANVISA da leva 7 (Hemoprod, núcleos, produtos para saúde, irregulares), sem rede."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from guaraci.anvisa import ANVISA_FILES, AnvisaClient, AnvisaFileDataSource
from guaraci.anvisa.client import RemoteFile
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import anvisa as anvisa_sources

NOVAS = (
    "anvisa_hemoprod",
    "anvisa_nucleos_seguranca_paciente",
    "anvisa_produtos_saude_registrados",
    "anvisa_produtos_saude_modelos",
    "anvisa_produtos_irregulares",
)


class _Client:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.refs: list[str] = []

    def head(self, ref: str) -> RemoteFile:
        self.refs.append(ref)
        return RemoteFile(url=ref, size=len(self.payload), last_modified=None)

    def download(self, ref: str, destination: Path, **_kwargs) -> int:
        self.refs.append(ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)
        return len(self.payload)


def _run(tmp_path: Path, key: str, payload: bytes) -> tuple[dict, _Client]:
    client = _Client(payload)
    source = AnvisaFileDataSource(output_path=str(tmp_path), dataset=key, client=client)
    return source.download(output_dir=str(tmp_path), output_format="csv"), client


def test_hemoprod_bom_scientific_notation_and_url(tmp_path):
    payload = (
        "﻿ID da resposta;Endereço IP;CNES - Cadastro;Ano de referência\r\n"
        '1;"10.0.245.217";"4,03453E+12";2022\r\n'
    ).encode("utf-8")
    result, client = _run(tmp_path, "anvisa_hemoprod", payload)
    assert client.refs[0].startswith("https://www.gov.br/anvisa/")
    assert client.refs[0].endswith("hemoprod_nacional.csv/@@download/file")
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.columns == ["ID da resposta", "Endereço IP", "CNES - Cadastro", "Ano de referência"]
    assert frame["CNES - Cadastro"][0] == "4,03453E+12"
    assert Path(result["exported_files"][0]).name == "anvisa_hemoprod.csv"


def test_irregulares_quoted_fields_with_semicolon_and_accent(tmp_path):
    payload = (
        "CO_SEQ;NO_RAZAO_SOCIAL;DS_TIPO_PRODUTO;PRODUTOS_CONCATENADOS\r\n"
        '47381;"M.B.C. INDUSTRIA; LTDA";"Cosmético";" CREME PÓS BARBA - Processo:1."\r\n'
    ).encode("cp1252")
    result, client = _run(tmp_path, "anvisa_produtos_irregulares", payload)
    assert client.refs[0].startswith("CONSULTAS/EMPRESA_FISCALIZACAO_PRODUTO/")
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.height == 1
    assert frame["NO_RAZAO_SOCIAL"][0] == "M.B.C. INDUSTRIA; LTDA"
    assert frame["DS_TIPO_PRODUTO"][0] == "Cosmético"
    # O arquivo bruto não ganha subpasta: sai direto em output_dir.
    assert result["output_dir"] == str(tmp_path)


def test_nucleos_header_hash_and_cnes_empty_are_kept(tmp_path):
    payload = (
        "#UF;MUNICIPIO;NU_CNPJ;CNES\r\n"
        "99;NÃO INFORMADO;60259169000192;\r\n"
    ).encode("cp1252")
    result, _ = _run(tmp_path, "anvisa_nucleos_seguranca_paciente", payload)
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.columns == ["#UF", "MUNICIPIO", "NU_CNPJ", "CNES"]
    assert frame["MUNICIPIO"][0] == "NÃO INFORMADO"
    assert frame["NU_CNPJ"][0] == "60259169000192"


def test_produtos_saude_literal_quote_inside_unquoted_text(tmp_path):
    payload = (
        "NUMERO_REGISTRO_CADASTRO;NOME_TECNICO;CLASSE_RISCO\r\n"
        '10361050002;Sistema "Holter";II\r\n'
    ).encode("cp1252")
    result, _ = _run(tmp_path, "anvisa_produtos_saude_registrados", payload)
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame["NOME_TECNICO"][0] == 'Sistema "Holter"'
    assert frame["NUMERO_REGISTRO_CADASTRO"][0] == "10361050002"


def test_client_url_for_keeps_full_url_and_quotes_relative():
    client = AnvisaClient()
    assert client.url_for("https://x.gov.br/a.csv") == "https://x.gov.br/a.csv"
    assert client.url_for("CONSULTAS/A B/x.CSV") == (
        "https://dados.anvisa.gov.br/dados/CONSULTAS/A%20B/x.CSV"
    )


def test_registry_answers_schema_for_every_new_key():
    service = DownloadService(sources=anvisa_sources.build_sources())
    for key in NOVAS:
        assert key in ANVISA_FILES
        schema = service.get_source_schema(key)
        assert schema is not None
