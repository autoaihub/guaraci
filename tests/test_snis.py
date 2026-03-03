"""
Tests for primary SNIS datasource (gov.br direct download).
"""

from types import SimpleNamespace

from guaraci.core.results import JobResult
from guaraci.snis.sinisa import SinisaDataSource, SinisaDocumentLink
from guaraci.snis.snis import SnisDataSource


SAMPLE_HTML = """
<html>
  <body>
    <a href="/arquivos/SINISA_AGUA_Planilhas_2023_v2.1.1.zip">Planilhas - Água</a>
    <a href="/arquivos/SINISA_ESGOTO_Planilhas_2023_v2.1.1.zip">Planilhas - Esgoto</a>
    <a href="/arquivos/SINISA_Glossario_2023.xlsx">Glossário SINISA</a>
  </body>
</html>
"""


def test_snis_datasource_is_gov_br_based():
    ds = SnisDataSource(output_path="data/test_snis")

    assert isinstance(ds, SinisaDataSource)
    assert ds.name == "snis"


def test_snis_output_path_defaults_to_data_snis():
    ds = SnisDataSource()
    assert ds.output_path.name == "snis"


def test_snis_list_documents_uses_sinisa_pipeline(monkeypatch):
    ds = SnisDataSource(output_path="data/test_snis")

    def fake_fetch_text(url, timeout):  # noqa: ARG001
        return SAMPLE_HTML

    monkeypatch.setattr(ds, "_fetch_text", fake_fetch_text)

    docs = ds.list_documents(file_kinds=["planilhas"], modules=["agua", "esgoto"])

    assert len(docs) == 2
    assert {doc.module for doc in docs} == {"agua", "esgoto"}
    assert all(doc.kind == "planilhas" for doc in docs)


def test_snis_discovers_nested_historical_pages(monkeypatch):
    ds = SnisDataSource(output_path="data/test_snis")
    root = ds.DEFAULT_RESULTS_URL
    agua = f"{root}/agua-e-esgotos-1"
    year = f"{agua}/2011"

    html_by_url = {
        root: f"""
            <a href="{agua}">Agua e Esgotos</a>
        """,
        agua: f"""
            <a href="{year}">2011</a>
        """,
        year: """
            <a href="/arquivos/snis_2011.zip">Download arquivo consolidado</a>
        """,
    }

    def fake_fetch_text(url, timeout):  # noqa: ARG001
        return html_by_url.get(url.rstrip("/"), "")

    monkeypatch.setattr(ds, "_fetch_text", fake_fetch_text)

    docs = ds.list_documents(file_kinds=["planilhas"])

    assert len(docs) == 1
    assert docs[0].url.endswith("/arquivos/snis_2011.zip")
    assert docs[0].kind == "planilhas"


def test_snis_extract_accepts_xls_inside_zip():
    ds = SnisDataSource(output_path="data/test_snis")
    doc = SinisaDocumentLink(
        url="https://example.org/arquivos/Planilhas_AE2011.zip",
        text="Planilhas AE 2011",
        kind="planilhas",
        module="agua",
    )
    allowed = ds._allowed_archive_extensions(doc)  # type: ignore[attr-defined]
    assert allowed == {".csv", ".xlsx", ".xls"}


def test_snis_download_returns_job_result(monkeypatch, tmp_path):
    ds = SnisDataSource(output_path=str(tmp_path / "snis"))
    doc = SinisaDocumentLink(
        url="https://example.org/arquivos/Planilhas_AE2011.zip",
        text="Planilhas AE 2011",
        kind="planilhas",
        module="agua",
    )
    fake_state = SimpleNamespace(
        downloaded=["a.zip"],
        skipped=[],
        extracted=["a"],
        failed=[],
    )

    monkeypatch.setattr(ds, "list_documents", lambda **kwargs: [doc])  # type: ignore[arg-type]
    monkeypatch.setattr(
        ds,
        "_prepare_output_dirs",
        lambda **kwargs: (tmp_path, tmp_path / "raw", tmp_path / "extracted"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(ds, "_download_documents", lambda **kwargs: fake_state)  # type: ignore[arg-type]
    captured_manifest = {}

    def fake_write_manifest(**kwargs):  # noqa: ANN003
        captured_manifest.update(kwargs["manifest"])
        return tmp_path / "manifest.json"

    monkeypatch.setattr(ds, "_write_manifest", fake_write_manifest)  # type: ignore[arg-type]

    result = ds.download()

    assert isinstance(result, JobResult)
    assert result.source == "snis"
    assert result.documents_found == 1
    assert result.downloaded_count == 1
    assert result.status == "success"
    assert result["manifest_path"] == str(tmp_path / "manifest.json")
    assert captured_manifest["source"] == "snis"
    assert captured_manifest["manifest_schema_version"] == "1.0"
