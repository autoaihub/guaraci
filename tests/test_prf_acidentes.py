import zipfile
from pathlib import Path

import pytest

from guaraci.prf.acidentes import PrfClient, datasource_for, parse_page

PAGE = """
<table><tr><td><p>Documento CSV de Acidentes 2025 (Agrupados por ocorr&ecirc;ncia)</p></td>
<td><a href="https://drive.google.com/file/d/AAA/view?usp=sharing/download">Baixar planilha</a>
<a href="https://drive.google.com/file/d/ZZZ/view"></a></td></tr>
<tr><td>Documento CSV de Acidentes 2025 (Agrupados por pessoa)</td>
<td><a href="https://drive.google.com/file/d/BBB/view">Baixar planilha</a></td></tr>
<tr><td>Documento CSV de Acidentes 2025 (Agrupados por pessoa - Todas as causas e tipos de acidentes)</td>
<td><a href="https://drive.google.com/file/d/CCC/view">Baixar planilha</a></td></tr>
<tr><td>Documento CSV de multas 2025</td>
<td><a href="https://drive.google.com/file/d/DDD/view">Baixar planilha</a></td></tr></table>
"""


def test_parse_page_keeps_only_the_two_groupings():
    assert parse_page(PAGE) == {("ocorrencia", 2025): "AAA", ("pessoa", 2025): "BBB"}


def test_confirm_url_follows_the_drive_warning_form():
    body = (
        '<form action="https://drive.usercontent.google.com/download" method="get">'
        '<input type="hidden" name="id" value="X"><input type="hidden" name="confirm" value="t">'
        '<input type="hidden" name="uuid" value="u&amp;1"></form>'
    )
    url = PrfClient._confirm_url(body, "https://drive.google.com/uc")
    assert url == "https://drive.usercontent.google.com/download?id=X&confirm=t&uuid=u%261"


class FakeClient:
    def discover(self):
        return {("ocorrencia", 2025): "AAA"}

    def download(self, file_id, destination, *, progress_callback=None):
        csv = '"id";"municipio";"km"\n1;"SÃO PAULO";"146,1"\n'.encode("latin-1")
        with zipfile.ZipFile(destination, "w") as z:
            z.writestr("datatran2025.csv", csv)
        return 1


def test_download_exports_utf8_text_columns(tmp_path: Path):
    source = datasource_for("prf_acidentes_ocorrencias")(str(tmp_path), client=FakeClient())
    result = source.download(start_year=2025, output_format="csv")
    out = Path(result["exported_files"][0])
    assert out.name == "prf_acidentes_ocorrencias_2025.csv"
    text = out.read_text(encoding="utf-8")
    assert "SÃO PAULO" in text and "146,1" in text
    assert not (tmp_path / "prf_acidentes_ocorrencias_2025.zip").exists()


def test_missing_year_is_an_error(tmp_path: Path):
    source = datasource_for("prf_acidentes_ocorrencias")(str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        source.download(start_year=2024, output_format="csv")


def test_schema_exposes_year_window():
    from guaraci.services.downloads import DownloadService

    names = {p["name"] for p in DownloadService().get_source_schema("prf_acidentes_pessoas")["params"]}
    assert {"start_year", "end_year", "output_format"} <= names
