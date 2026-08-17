"""
Tests for SINISA raw extractor utilities.
"""

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from guaraci.snis.sinisa import SinisaDataSource


SAMPLE_HTML = """
<html>
  <body>
    <a href="/arquivos/SINISA_AGUA_Planilhas_2023_v2.1.1.zip">Planilhas - Água</a>
    <a href="/arquivos/SINISA_ESGOTO_Planilhas_2023_v2.1.1.zip/view">Planilhas - Esgoto</a>
    <a href="/arquivos/SINISA_Glossario_2023.xlsx">Glossário SINISA</a>
    <a href="/arquivos/SINISA_Relatorio_2023.pdf">Relatório de Diagnóstico</a>
    <a href="/arquivos/SINISA_ESGOTO_Planilhas_2024.pdf">Planilhas de Informações e Indicadores</a>
    <a href="mailto:contato@example.com">contato</a>
    <a href="/pagina-interna">Leia mais</a>
  </body>
</html>
"""


def test_extract_links_only_downloadables():
    links = SinisaDataSource._extract_links(
        SAMPLE_HTML,
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/resultados-sinisa",
    )

    urls = [item.url for item in links]
    assert len(urls) == 5
    assert all(url.endswith((".zip", ".xlsx", ".pdf")) for url in urls)
    assert "/view" not in "".join(urls)


def test_infer_kind_and_module():
    links = SinisaDataSource._extract_links(
        SAMPLE_HTML,
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/resultados-sinisa",
    )
    by_url = {item.url: item for item in links}

    agua = by_url[
        "https://www.gov.br/arquivos/SINISA_AGUA_Planilhas_2023_v2.1.1.zip"
    ]
    esgoto = by_url[
        "https://www.gov.br/arquivos/SINISA_ESGOTO_Planilhas_2023_v2.1.1.zip"
    ]
    glossario = by_url["https://www.gov.br/arquivos/SINISA_Glossario_2023.xlsx"]
    relatorio = by_url["https://www.gov.br/arquivos/SINISA_Relatorio_2023.pdf"]

    assert agua.kind == "planilhas"
    assert agua.module == "agua"
    assert esgoto.kind == "planilhas"
    assert esgoto.module == "esgoto"
    assert glossario.kind == "glossarios"
    assert relatorio.kind == "relatorios"


def test_list_documents_filters(monkeypatch):
    ds = SinisaDataSource(output_path="data/test_sinisa")

    def fake_fetch_text(url, timeout):  # noqa: ARG001
        return SAMPLE_HTML

    monkeypatch.setattr(ds, "_fetch_text", fake_fetch_text)

    planilhas_agua = ds.list_documents(
        file_kinds=["planilhas"],
        modules=["agua"],
    )
    assert len(planilhas_agua) == 1
    assert planilhas_agua[0].module == "agua"
    assert all(not item.url.lower().endswith(".pdf") for item in planilhas_agua)

    relatorios = ds.list_documents(file_kinds=["relatorios"])
    assert len(relatorios) == 1
    assert relatorios[0].kind == "relatorios"


def test_invalid_filters_raise():
    ds = SinisaDataSource(output_path="data/test_sinisa")

    with pytest.raises(ValueError):
        ds.list_documents(file_kinds=["invalid_kind"])

    with pytest.raises(ValueError):
        ds.list_documents(modules=["invalid_module"])


def test_extract_zip_keeps_only_csv_xlsx(tmp_path):
    ds = SinisaDataSource(output_path=str(tmp_path / "sinisa"))
    zip_path = tmp_path / "sample.zip"
    extracted_root = tmp_path / "extracted"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.csv", "x,y\n1,2\n")
        zf.writestr("b.xlsx", b"fake-xlsx")
        zf.writestr("c.pdf", b"fake-pdf")
        zf.writestr("nested/d.txt", "ignore")

    destination = ds._extract_zip(  # type: ignore[attr-defined]
        zip_path,
        extracted_root,
        overwrite=True,
        allowed_extensions={".csv", ".xlsx"},
    )
    assert destination is not None
    files = sorted(
        str(path.relative_to(destination))
        for path in Path(destination).rglob("*")
        if path.is_file()
    )
    assert files == ["a.csv", "b.xlsx"]


def test_extract_zip_blocks_path_traversal(tmp_path):
    ds = SinisaDataSource(output_path=str(tmp_path / "sinisa"))
    zip_path = tmp_path / "malicious.zip"
    extracted_root = tmp_path / "extracted"
    outside_file = tmp_path / "escape.csv"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../escape.csv", "x,y\n1,2\n")
        zf.writestr("safe.csv", "x,y\n3,4\n")

    destination = ds._extract_zip(  # type: ignore[attr-defined]
        zip_path,
        extracted_root,
        overwrite=True,
        allowed_extensions={".csv"},
    )
    assert destination is not None
    assert (destination / "safe.csv").exists()
    assert not outside_file.exists()


def test_sinisa_download_returns_job_result(monkeypatch, tmp_path):
    """SinisaDataSource.download now matches SnisDataSource: it returns a
    JobResult, and key access keeps working (JobResult is a Mapping)."""
    from guaraci.core.results import JobResult
    from guaraci.snis.sinisa import SinisaDocumentLink

    ds = SinisaDataSource(output_path=str(tmp_path / "sinisa"))
    doc = SinisaDocumentLink(
        url="https://example.org/arquivos/SINISA_AGUA_Planilhas_2023.zip",
        text="Planilhas Agua 2023",
        kind="planilhas",
        module="agua",
    )
    fake_state = SimpleNamespace(
        downloaded=["a.zip"],
        skipped=[],
        extracted=["a"],
        failed=[],
    )

    monkeypatch.setattr(ds, "list_documents", lambda **kwargs: [doc])
    monkeypatch.setattr(
        ds,
        "_prepare_output_dirs",
        lambda **kwargs: (tmp_path, tmp_path / "raw", tmp_path / "extracted"),
    )
    monkeypatch.setattr(ds, "_download_documents", lambda **kwargs: fake_state)
    monkeypatch.setattr(
        ds, "_write_manifest", lambda **kwargs: tmp_path / "manifest.json"
    )

    result = ds.download()

    assert isinstance(result, JobResult)
    assert result.source == "sinisa"
    assert result.documents_found == 1
    assert result.downloaded_count == 1
    assert result.failed_count == 0
    # Backwards-compatible mapping access for legacy consumers.
    assert result["documents_found"] == 1
    assert result["manifest_path"] == str(tmp_path / "manifest.json")
    assert result["output_dir"] == str(tmp_path)


def test_build_manifest_includes_standard_schema():
    ds = SinisaDataSource(output_path="data/test_sinisa")
    state = SimpleNamespace(
        downloaded=["raw/a.zip"],
        skipped=["raw/b.zip"],
        extracted=["extracted/a"],
        failed=["https://example.org/fail.zip"],
    )

    manifest = ds._build_manifest(  # type: ignore[attr-defined]
        source_url="https://example.org/results",
        file_kinds=["planilhas"],
        modules=["agua"],
        extract_archives=True,
        overwrite=False,
        documents_found=2,
        state=state,
    )

    assert manifest["manifest_schema_version"] == "1.1"
    assert manifest["source"] == "sinisa"
    assert manifest["stats"]["documents_found"] == 2
    assert manifest["artifacts"]["downloaded_files"] == ["raw/a.zip"]
    assert manifest["filters"]["file_kinds"] == ["planilhas"]
