"""Censo Escolar INEP (tabela de escolas), sem rede.

Os casos que valem teste produziriam dado plausível e errado: a tabela de
escolas trocada por outra do mesmo zip (2025 traz seis), o CSV em cp1252 lido
como UTF-8 e a URL de 2025 (com sublinhado final) montada sem ele.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict

import polars as pl
import pytest

from guaraci.arquivos import RemoteFile
from guaraci.arquivos.http_files import HttpFileClientError
from guaraci.arquivos.inep_censo_escolar import InepCensoEscolarDataSource, year_url
from guaraci.services.downloads import DownloadService


class _Client:
    def __init__(self, payloads: Dict[str, bytes]) -> None:
        self.payloads = payloads

    def head(self, url: str) -> RemoteFile:
        if url not in self.payloads:
            raise HttpFileClientError("nope", category="not_found", retryable=False)
        return RemoteFile(url=url, size=len(self.payloads[url]), last_modified="Wed")

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        destination.write_bytes(self.payloads[url])
        return len(self.payloads[url])


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


ESCOLAS = "NU_ANO_CENSO;NO_ENTIDADE;IN_AGUA_POTAVEL\n2025;ESCOLA SÃO JOÃO;1\n2025;EEEF AÇAÍ;0\n"
OUTRA = "NU_ANO_CENSO;CO_PESSOA\n2025;999\n"


def test_year_url_sublinhado_so_em_2025():
    assert year_url(2024).endswith("microdados_censo_escolar_2024.zip")
    assert year_url(2025).endswith("microdados_censo_escolar_2025_.zip")


def test_exporta_tabela_de_escolas_entre_tres_tabelas(tmp_path):
    zipped = _zip({
        "microdados_censo_escolar_2025_v2/dados/Tabela_Docente_2025_V2.csv": OUTRA.encode("cp1252"),
        "microdados_censo_escolar_2025_v2/dados/Tabela_Escola_2025_V2.csv": ESCOLAS.encode("cp1252"),
        "microdados_censo_escolar_2025_v2/dados/Tabela_Turma_2025_V2.csv": OUTRA.encode("cp1252"),
    })
    client = _Client({year_url(2025): zipped})
    source = InepCensoEscolarDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(output_dir=str(tmp_path), output_format="csv", start_year=2025)
    assert payload["failed_count"] == 0
    (exported,) = payload["exported_files"]
    assert Path(exported).name == "inep_censo_escolar_2025.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.columns == ["NU_ANO_CENSO", "NO_ENTIDADE", "IN_AGUA_POTAVEL"]
    assert frame["NO_ENTIDADE"].to_list() == ["ESCOLA SÃO JOÃO", "EEEF AÇAÍ"]


def test_membro_antigo_e_intervalo_de_anos(tmp_path):
    z24 = _zip({
        "microdados_censo_escolar_2024_defeso/dados/microdados_ed_basica_2024.csv": ESCOLAS.encode("cp1252"),
        "microdados_censo_escolar_2024_defeso/dados/suplemento_cursos_tecnicos_2024.csv": OUTRA.encode("cp1252"),
    })
    client = _Client({year_url(2024): z24})
    source = InepCensoEscolarDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv", start_year=2024, end_year=2025
    )
    # 2025 não existe no cliente falso: falha isolada, 2024 sai.
    assert payload["failed_count"] == 1
    assert [Path(p).name for p in payload["exported_files"]] == ["inep_censo_escolar_2024.csv"]


def test_ano_anterior_ao_piso_e_recusado(tmp_path):
    source = InepCensoEscolarDataSource(output_path=str(tmp_path), client=_Client({}))
    with pytest.raises(ValueError):
        source.download(output_dir=str(tmp_path), start_year=2003)


def test_schema_registrado():
    schema = DownloadService().get_source_schema("inep_censo_escolar")
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "output_format"} <= names
