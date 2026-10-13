"""Séries novas da PNAD Contínua anual (visita 5 e trimestres temáticos), sem rede."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.ibge.microdados import PESQUISAS, IbgeMicrodadosDataSource, RemoteFile
from guaraci.services.downloads import DownloadService

_NOVAS = {
    "ibge_pnadc_visita5": [*range(2016, 2025)],
    "ibge_pnadc_trimestre1": [2023],
    "ibge_pnadc_trimestre2": [*range(2016, 2020), *range(2022, 2026)],
    "ibge_pnadc_trimestre3": [2019, 2022, 2024, 2025],
    "ibge_pnadc_trimestre4": [*range(2016, 2020), 2021, 2022, 2023, 2024, 2025],
}
_BASE = "Trabalho_e_Rendimento/Pesquisa_Nacional_por_Amostra_de_Domicilios_continua/Anual/Microdados/"

_SAS = (
    "data pnadc_xxxxxx;\n"
    'infile "...\\Dados\\PNADC_xxxxxx.txt" lrecl=4000 Missover;\n'
    "input\n"
    "@0001 Ano   $4.   /* Ano de referência */\n"
    "@0005 Trimestre   $1.   /* Trimestre de referência */\n"
    "@0006 V1031   8.   /* Peso */\n"
    ";\nrun;"
).encode("cp1252")


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class _Client:
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


@pytest.mark.parametrize("key,anos", sorted(_NOVAS.items()))
def test_new_series_cover_published_years(key, anos):
    assert sorted(PESQUISAS[key].edicoes) == anos


def test_new_series_are_listed_by_the_service():
    listed = {item.source for item in DownloadService().list_sources()}
    assert set(_NOVAS) <= listed


def test_visita5_urls():
    edicoes = PESQUISAS["ibge_pnadc_visita5"].edicoes
    base = _BASE + "Visita/Visita_5/"
    assert edicoes[2016].arquivos == {
        "dados": base + "Dados/PNADC_2016_visita5_20260520.zip",
        "leitura": base + "Documentacao/input_PNADC_2016_visita5_20231222.txt",
    }
    assert edicoes[2024].arquivos["dados"].endswith("Dados/PNADC_2024_visita5.zip")
    assert edicoes[2021].arquivos["leitura"].endswith("Documentacao/input_PNADC_2021_visita5.txt")
    assert edicoes[2020].tabelas[0].membro == "PNADC_2020_visita5.txt"


def test_trimestre_urls_share_one_layout_program():
    base = _BASE + "Trimestre/"
    t1 = PESQUISAS["ibge_pnadc_trimestre1"].edicoes[2023]
    assert t1.arquivos["dados"] == base + "Trimestre_1/Dados/PNADC_2023_trimestre1.zip"
    assert t1.arquivos["leitura"] == base + "Trimestre_1/Documentacao/input_PNADC_trimestre1.txt"
    t4 = PESQUISAS["ibge_pnadc_trimestre4"].edicoes
    assert t4[2024].arquivos["dados"].endswith("Trimestre_4/Dados/PNADC_2024_trimestre4_20251014.zip")
    assert t4[2025].arquivos["dados"].endswith("Trimestre_4/Dados/PNADC_2025_trimestre4_20260702.zip")
    assert {e.arquivos["leitura"] for e in t4.values()} == {
        base + "Trimestre_4/Documentacao/input_PNADC_trimestre4_20251010.txt"
    }
    assert t4[2021].tabelas[0].membro == "PNADC_2021_trimestre4.txt"


def test_trimestre_reads_layout_published_as_plain_txt(tmp_path):
    client = _Client({
        "PNADC_2019_trimestre3_20260904.zip": _zip({"PNADC_2019_trimestre3.txt": b"2019300123.45\r\n20191  99.5 \r\n"}),
        "input_PNADC_trimestre3_20260904.txt": _SAS,
    })
    source = IbgeMicrodadosDataSource(output_path=str(tmp_path), dataset="ibge_pnadc_trimestre3", client=client)
    result = source.download(output_dir=str(tmp_path), start_year=2019, output_format="csv")
    (exported,) = result["exported_files"]
    assert Path(exported).name == "ibge_pnadc_trimestre3_2019_microdados.csv"
    frame = pl.read_csv(exported, infer_schema=False)
    assert frame.columns == ["Ano", "Trimestre", "V1031"]
    assert frame.rows() == [("2019", "3", "00123.45"), ("2019", "1", "99.5")]
