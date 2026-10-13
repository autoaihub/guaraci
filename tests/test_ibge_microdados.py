"""Fontes de microdados do IBGE (PNS, POF, PeNSE), sem rede.

Um cliente falso serve zips montados em memória com o mesmo arranjo dos
publicados: dado e programa SAS em zips separados (PNS, POF), nome do
INFILE com caixa diferente do membro (POF), pasta com nome qualquer (PeNSE
2012), CSV com ``;`` em cp1252 (PeNSE 2015) e CSV com vírgula em UTF-8.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.ibge.microdados import PESQUISAS, IbgeMicrodadosDataSource, RemoteFile
from guaraci.services.downloads import DownloadService


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class _Client:
    """Serve zips por sufixo de caminho no lugar de ftp.ibge.gov.br."""

    def __init__(self, files: Dict[str, bytes]) -> None:
        self.files = files
        self.calls: List[str] = []

    def _payload(self, path: str) -> bytes:
        for suffix, data in self.files.items():
            if path.endswith(suffix):
                return data
        raise AssertionError(f"unexpected path {path}")

    def head(self, path: str) -> RemoteFile:
        self.calls.append(f"HEAD {path}")
        return RemoteFile(url=f"https://x/{path}", size=len(self._payload(path)), last_modified=None)

    def download(self, path: str, destination: Path, **_kwargs) -> int:
        self.calls.append(f"GET {path}")
        data = self._payload(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return len(data)


_PNS_SAS = (
    "data PNS_2019;\r\n"
    "INFILE '...\\dados\\PNS_2019.txt' LRECL=12 missover;\r\n"
    "INPUT\r\n"
    "@00001\tV0001\t$2.\t/*Unidade da Federação*/\r\n"
    "@00003\tC008\t$3.\r\n"
    "@00006\tV0028\t7.2\r\n"
    ";\r\nRUN;\r\n"
).encode("cp1252")
_PNS_TXT = b"350070012.50\r\n11   085.5 \r\n"


def _pns_client() -> _Client:
    return _Client({
        "PNS_2019_20220525.zip": _zip({"PNS_2019.txt": _PNS_TXT}),
        "Dicionario_e_input_20220530.zip": _zip({"input_PNS_2019.sas": _PNS_SAS}),
    })


def _run(tmp_path: Path, key: str, client: _Client, **kwargs) -> dict:
    source = IbgeMicrodadosDataSource(output_path=str(tmp_path), dataset=key, client=client)
    return source.download(output_dir=str(tmp_path), **kwargs)


def test_pns_fixed_width_exports_text_columns_and_drops_zips(tmp_path):
    result = _run(tmp_path, "ibge_pns", _pns_client(), start_year=2019, output_format="csv")
    assert result["documents_found"] == 1
    assert result["downloaded_count"] == 2
    (exported,) = result["exported_files"]
    assert Path(exported).name == "ibge_pns_2019_pns.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.columns == ["V0001", "C008", "V0028"]
    assert frame.rows() == [("35", "007", "0012.50"), ("11", "", "085.5")]  # branco vira vazio, não nulo
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ibge_pns_2019_pns.csv"]


def test_existing_zip_with_same_size_is_not_downloaded_again(tmp_path):
    client = _pns_client()
    _run(tmp_path, "ibge_pns", client, start_year=2019, output_format="parquet", keep_raw=True)
    again = _run(tmp_path, "ibge_pns", client, start_year=2019, output_format="parquet")
    assert again["skipped_count"] == 2 and again["downloaded_count"] == 0
    assert sum(call.startswith("GET") for call in client.calls) == 2


def test_year_without_edition_is_empty_and_touches_no_network(tmp_path):
    client = _Client({})
    result = _run(tmp_path, "ibge_pns", client, start_year=2015, end_year=2018, output_format="csv")
    assert result["documents_found"] == 0
    assert result["exported_files"] == []
    assert client.calls == []
    assert "2013" in result["export_warning"]


_POF_SAS = (
    "data domicilio;\r\n"
    'INFILE ".....\\domicilio.txt";\r\n'
    "INPUT\r\n@01  UF  2.\r\n@03  PESO  5.2\r\n;\r\nrun;\r\n"
    "data morador;\r\n"
    'INFILE ".....\\MORADOR.txt";\r\n'
    "INPUT\r\n@01  UF  2.\r\n@03  COD  $1.\r\n;\r\nrun;\r\n"
).encode("cp1252")


def test_pof_matches_infile_without_case_and_filters_tabelas(tmp_path):
    client = _Client({
        "Dados_20230713.zip": _zip({
            "DOMICILIO.txt": b"3512.50\r\n",
            "MORADOR.txt": b"35A\r\n",
        }),
        "Programas_de_Leitura_20230713.zip": _zip({"SAS/Leitura dos Microdados - SAS.txt": _POF_SAS}),
    })
    result = _run(
        tmp_path, "ibge_pof", client, start_year=2017,
        tabelas=["morador", "domicilio"], output_format="csv",
    )
    names = [Path(p).name for p in result["exported_files"]]
    assert names == ["ibge_pof_2017_domicilio.csv", "ibge_pof_2017_morador.csv"]  # ordem do registro
    assert pl.read_csv(result["exported_files"][0], infer_schema=False).row(0) == ("35", "12.50")
    assert pl.read_csv(result["exported_files"][1], infer_schema=False).row(0) == ("35", "A")

    with pytest.raises(ValueError, match="Unknown tabelas"):
        _run(tmp_path, "ibge_pof", client, start_year=2017, tabelas=["inexistente"])


def test_pense_2015_csv_cp1252_with_semicolon(tmp_path):
    csv = "ANOPESQ;VB01001;NOME\r\n2015;01;São Paulo\r\n".encode("cp1252")
    files = {}
    for amostra in ("1", "2"):
        files[f"PeNSE_2015_AMOSTRA{amostra}.zip"] = _zip({
            f"arquivos csv/PENSE_AMOSTRA{amostra}_{parte}.CSV": csv
            for parte in ("ALUNO", "ALUNOESCOLA", "ESCOLA")
        })
    result = _run(
        tmp_path, "ibge_pense", _Client(files), start_year=2015,
        tabelas=["amostra2_aluno"], output_format="parquet",
    )
    (exported,) = result["exported_files"]
    frame = pl.read_parquet(exported)
    assert frame.rows() == [("2015", "01", "São Paulo")]
    assert result["encodings"] == {"2015/amostra2_aluno": "cp1252"}
    assert result["documents_found"] == 1


def test_pense_2024_csv_utf8_with_comma(tmp_path):
    csv = "REGIAO,UF,PESO\n1,11,0012.5\n".encode("utf-8")
    client = _Client({"2024/microdados/Dados.zip": _zip({"CSV/PENSE2024_MICRODADOS.csv": csv})})
    result = _run(tmp_path, "ibge_pense", client, start_year=2024, output_format="csv")
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.rows() == [("1", "11", "0012.5")]
    assert result["encodings"] == {"2024/microdados": "utf-8"}


def test_pense_2012_sequential_layout_inside_same_zip(tmp_path):
    sas = (
        "DATA ESCOLAS;\r\n"
        "INFILE 'PASTA ONDE ESTÁ O ARQUIVO\\Pense2012Escolas.txt'\tlrecl=5;\r\n"
        "INPUT\t\r\nID_ESCOLA\t4.\t/*Identificação*/\r\nDEP\t$1.\r\n;\r\n"
    ).encode("cp1252")
    client = _Client({
        "PENSE_2012_microdados.zip": _zip({
            "3edicao/Dados/pense2012Escolas.txt": b"0042X\r\n",
            "3edicao/InputSAS/Input SAS escolas.sas": sas,
        })
    })
    result = _run(
        tmp_path, "ibge_pense", client, start_year=2012, tabelas=["escolas"], output_format="csv"
    )
    assert pl.read_csv(result["exported_files"][0], infer_schema=False).row(0) == ("0042", "X")
    assert sum(call.startswith("GET") for call in client.calls) == 1


def test_registry_exposes_the_three_surveys():
    service = DownloadService()
    for key in PESQUISAS:
        schema = service.get_source_schema(key)
        assert schema is not None
    text = str(service.get_source_schema("ibge_pense"))
    assert "2024" in text and "tabelas" in text


_PNADC_SAS = (
    "data pnadc_xxxxxx;\n"
    'infile "...\\Dados\\PNADC_xxxxxx.txt" lrecl=4000 Missover;\n'
    "input\n"
    "@0001 Ano   $4.   /* Ano de referência */\n"
    "@0005 Trimestre   $1.   /* Trimestre de referência */\n"
    "@0006 V1031   8.   /* Peso */\n"
    ";\nrun;"
).encode("cp1252")


def test_pnadc_reads_layout_published_as_plain_txt(tmp_path):
    client = _Client({
        "PNADC_2025_visita1_20260923.zip": _zip({"PNADC_2025_visita1.txt": b"2025300123.45\r\n20251  99.5 \r\n"}),
        "input_PNADC_2025_visita1_20260923.txt": _PNADC_SAS,
    })
    result = _run(tmp_path, "ibge_pnadc_visita1", client, start_year=2025, output_format="csv")
    (exported,) = result["exported_files"]
    assert Path(exported).name == "ibge_pnadc_visita1_2025_microdados.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.columns == ["Ano", "Trimestre", "V1031"]
    assert frame.rows() == [("2025", "3", "00123.45"), ("2025", "1", "99.5")]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ibge_pnadc_visita1_2025_microdados.csv"]


def test_pense_2009_uses_frozen_layout_and_downloads_only_the_data_zip(tmp_path):
    row = "1111" + "1" + "2" * 306  # 311 posições: ID 4, QUESTIONARIO 1, B00P01 1...
    client = _Client({
        "PENSE_2009_microdados.zip": _zip({
            "Dados/Base_Pense Completa_2009.txt": (row + "\r\n" + row + "\r\n").encode("cp1252"),
        }),
    })
    result = _run(tmp_path, "ibge_pense", client, start_year=2009, output_format="csv")
    assert result["downloaded_count"] == 1
    assert client.calls == [
        "HEAD pense/2009/microdados/PENSE_2009_microdados.zip",
        "GET pense/2009/microdados/PENSE_2009_microdados.zip",
    ]
    (exported,) = result["exported_files"]
    assert Path(exported).name == "ibge_pense_2009_microdados.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.width == 187 and frame.height == 2
    assert frame.columns[:3] == ["ID", "QUESTIONARIO", "B00P01"]
    assert frame.row(0)[:3] == ("1111", "1", "2")


def test_pnadc_visita1_editions_skip_2020_and_2021():
    assert sorted(PESQUISAS["ibge_pnadc_visita1"].edicoes) == [
        *range(2012, 2020), 2022, 2023, 2024, 2025,
    ]
