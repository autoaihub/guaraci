"""Offline tests for the bulk-file portal transport (SRAG/SISAGUA).

No network calls: HTML parsing is tested against static fixtures that mirror
the real dadosabertos.saude.gov.br page shape (verified live 2026-08-17, see
docs/PLANO_NOVAS_FONTES.md Fase A), and the datasource is exercised through a
fake client (duck-typed, same pattern as tests/test_opendatasus_datasource.py).
"""

from __future__ import annotations

import json

import pytest

from guaraci.opendatasus.portal_files import (
    PortalFileDataSource,
    PortalFilePackageSpec,
    parse_dataset_resources,
    parse_resource_s3_url,
)

SRAG_SLUG = "srag-2019-a-2026"


def _resource_card(resource_id: str, name: str) -> str:
    """One resource card, mirroring the real dataset-page markup (verified
    live 2026-08-17): the resource NAME lives in a sibling
    ``div.text-weight-bold`` *before* the anchor, whose own text is just
    "Explorar" (desktop button) — never the resource name itself. Each card
    also repeats the same href in a mobile icon-only anchor.
    """
    return f"""
    <div class="br-card rounder-md"><div class="card-content d-flex">
      <div class="p-0 p-md-2"><div class="sprite sprite-csv"></div></div>
      <div class="p-2 m-0 ml-md-2">
        <div class="text-weight-bold" style="margin-bottom:10px">{name}</div>
        <div><span class="p-1">Data de Atualizacao: 05/01/2025</span></div>
      </div>
      <div class="mr-0 mr-md-3 ml-auto p-0 p-sm-1 p-md-3">
        <div class="d-none d-md-block">
          <a class="br-button primary" href="/dataset/{SRAG_SLUG}/resource/{resource_id}">Explorar</a>
        </div>
        <a class="br-button primary circle d-md-none" href="/dataset/{SRAG_SLUG}/resource/{resource_id}">
          <i class="fas fa-eye" aria-hidden="true"></i>
        </a>
      </div>
    </div></div>
    """


SRAG_DATASET_HTML = (
    "<html><body><div class=\"text-weight-bold\">SRAG - Bancos Anuais</div>"
    + _resource_card("11111111-1111-1111-1111-111111111111", "2019- Banco vivo 05/01/2025 - PARQUET")
    + _resource_card("22222222-2222-2222-2222-222222222222", "2019- Banco vivo 05/01/2025 - CSV")
    + _resource_card("33333333-3333-3333-3333-333333333333", "2026- Banco vivo 17/08/2026 - PARQUET")
    + _resource_card("44444444-4444-4444-4444-444444444444", "2026- Dicionario de dados")
    + f'<a href="/dataset/{SRAG_SLUG}">not a resource link</a>'
    + "</body></html>"
)


def _resource_page(url: str) -> str:
    return f"""
    <html><body>
    <a href="{url}" class="resource-url-analytics" target="_blank">Baixar</a>
    </body></html>
    """


SRAG_RESOURCE_URLS = {
    "11111111-1111-1111-1111-111111111111": (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2019/INFLUD19.parquet"
    ),
    "22222222-2222-2222-2222-222222222222": (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2019/INFLUD19.csv"
    ),
    "33333333-3333-3333-3333-333333333333": (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2026/"
        "INFLUD26-17-08-2026.parquet"
    ),
}


def test_parse_dataset_resources_extracts_id_and_name() -> None:
    resources = parse_dataset_resources(SRAG_DATASET_HTML, SRAG_SLUG)
    ids = [item[0] for item in resources]
    assert "11111111-1111-1111-1111-111111111111" in ids
    assert "44444444-4444-4444-4444-444444444444" in ids  # dictionary resource also listed
    names = dict(resources)
    assert "Banco vivo" in names["11111111-1111-1111-1111-111111111111"]
    assert "PARQUET" in names["11111111-1111-1111-1111-111111111111"]


def test_parse_dataset_resources_dedups_and_ignores_non_resource_links() -> None:
    resources = parse_dataset_resources(SRAG_DATASET_HTML, SRAG_SLUG)
    ids = [item[0] for item in resources]
    assert len(ids) == len(set(ids))
    assert SRAG_SLUG not in [item[0] for item in resources]  # the bare dataset link is skipped


def test_parse_resource_s3_url_extracts_url() -> None:
    url = SRAG_RESOURCE_URLS["11111111-1111-1111-1111-111111111111"]
    html = _resource_page(url)
    assert parse_resource_s3_url(html) == url


def test_parse_resource_s3_url_returns_none_when_absent() -> None:
    assert parse_resource_s3_url("<html><body>no url here</body></html>") is None


class _FakePortalClient:
    """Duck-typed fake for PortalFilesClient: no network, canned HTML/S3 URLs."""

    def __init__(self) -> None:
        self.download_calls: list[str] = []
        self.head_calls: list[str] = []

    def get_dataset_page(self, slug: str) -> str:
        assert slug == SRAG_SLUG
        return SRAG_DATASET_HTML

    def get_resource_page(self, slug: str, resource_id: str) -> str:
        assert slug == SRAG_SLUG
        url = SRAG_RESOURCE_URLS.get(resource_id)
        if url is None:
            return "<html><body>no file here</body></html>"
        return _resource_page(url)

    def head_content_length(self, url: str) -> int:
        self.head_calls.append(url)
        return 1024 * 1024 * 3  # pretend every file is 3 MiB

    def download_file(self, url: str, destination, **_kwargs) -> int:  # noqa: ANN001
        self.download_calls.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = f"fake-content-for:{url}".encode("utf-8")
        destination.write_bytes(payload)
        return len(payload)


@pytest.fixture()
def srag_spec() -> PortalFilePackageSpec:
    return PortalFileDataSource.PACKAGE_SPECS["srag_arquivos"]


def test_discover_filters_by_year_and_include_terms(tmp_path) -> None:  # noqa: ANN001
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=_FakePortalClient())

    result = datasource.discover(dataset="srag_arquivos", start_year=2019, end_year=2019)

    assert result["documents_found"] == 2  # PARQUET + CSV for 2019, "Dicionario" excluded
    formats = {item["format"] for item in result["resources"]}
    assert formats == {"parquet", "csv"}
    assert all(item["year"] == 2019 for item in result["resources"])


def test_discover_with_fetch_sizes_reports_total(tmp_path) -> None:  # noqa: ANN001
    client = _FakePortalClient()
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=client)

    result = datasource.discover(
        dataset="srag_arquivos", start_year=2019, end_year=2019, fetch_sizes=True
    )

    assert result["total_size_bytes"] == 2 * 1024 * 1024 * 3
    assert len(client.head_calls) == 2


def test_discover_unknown_dataset_raises(tmp_path) -> None:  # noqa: ANN001
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=_FakePortalClient())
    with pytest.raises(ValueError, match="Unsupported portal-files dataset"):
        datasource.discover(dataset="not_a_real_dataset")


def test_download_selects_best_format_per_year_and_writes_manifest(tmp_path) -> None:  # noqa: ANN001
    client = _FakePortalClient()
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=client)

    payload = datasource.download(dataset="srag_arquivos", start_year=2019, end_year=2026)

    # One resource per year selected, preferring parquet (format_priority[0]).
    assert payload["downloaded_count"] == 2  # years 2019 and 2026
    assert payload["failed_count"] == 0
    assert len(client.download_calls) == 2
    assert all(url.endswith(".parquet") for url in client.download_calls)

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == "srag_arquivos"
    assert manifest["stats"]["downloaded_count"] == 2


def test_download_is_idempotent_by_basename(tmp_path) -> None:  # noqa: ANN001
    client = _FakePortalClient()
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=client)

    first = datasource.download(dataset="srag_arquivos", start_year=2019, end_year=2019)
    assert first["downloaded_count"] == 1
    assert len(client.download_calls) == 1

    second = datasource.download(dataset="srag_arquivos", start_year=2019, end_year=2019)
    assert second["skipped_count"] == 1
    assert second["downloaded_count"] == 0
    # No new network/download call: same basename already exists on disk.
    assert len(client.download_calls) == 1


def test_download_resource_filter_excludes_non_matching(tmp_path) -> None:  # noqa: ANN001
    client = _FakePortalClient()
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=client)

    payload = datasource.download(
        dataset="srag_arquivos",
        start_year=2019,
        end_year=2019,
        resource_filter="csv",
    )

    assert payload["downloaded_count"] == 1
    assert client.download_calls[0].endswith(".csv")


def test_load_dataframe_is_not_implemented(tmp_path) -> None:  # noqa: ANN001
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=_FakePortalClient())
    with pytest.raises(NotImplementedError):
        datasource.load_dataframe()


# ---------------------------------------------------------------------------
# SISAGUA-shaped fixtures: cumulative dataset (no year in any resource name),
# one .zip per inner format (csv/json/xml, no parquet — verified live
# 2026-08-17), plus a data-dictionary resource that must be excluded.
# ---------------------------------------------------------------------------

POP_SLUG = "sisagua-populacao-abastecida"
POP_DATASET_HTML = (
    "<html><body>"
    + _resource_card("bbbbbbbb-0000-0000-0000-000000000001", "Dicionario de dados").replace(
        SRAG_SLUG, POP_SLUG
    )
    + _resource_card("bbbbbbbb-0000-0000-0000-000000000002", "Cadastro - Populacao abastecida").replace(
        SRAG_SLUG, POP_SLUG
    )
    + _resource_card("bbbbbbbb-0000-0000-0000-000000000003", "Cadastro populacao abastecida").replace(
        SRAG_SLUG, POP_SLUG
    )
    + "</body></html>"
)
POP_RESOURCE_URLS = {
    "bbbbbbbb-0000-0000-0000-000000000001": (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SISAGUA/MetaDados.pdf"
    ),
    "bbbbbbbb-0000-0000-0000-000000000002": (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SISAGUA/"
        "cadastro_populacao_abastecida_csv.zip"
    ),
    "bbbbbbbb-0000-0000-0000-000000000003": (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SISAGUA/"
        "cadastro_populacao_abastecida_json.zip"
    ),
}


class _FakePopulacaoAbastecidaClient(_FakePortalClient):
    def get_dataset_page(self, slug: str) -> str:  # noqa: ANN001
        assert slug == POP_SLUG
        return POP_DATASET_HTML

    def get_resource_page(self, slug: str, resource_id: str) -> str:  # noqa: ANN001
        assert slug == POP_SLUG
        url = POP_RESOURCE_URLS.get(resource_id)
        if url is None:
            return "<html><body>no file here</body></html>"
        return _resource_page(url)


def test_discover_excludes_dictionary_and_infers_zip_inner_format(tmp_path) -> None:  # noqa: ANN001
    datasource = PortalFileDataSource(
        output_path=str(tmp_path), client=_FakePopulacaoAbastecidaClient()
    )

    result = datasource.discover(dataset="sisagua_populacao_abastecida")

    assert result["documents_found"] == 2  # dictionary excluded
    formats = {item["format"] for item in result["resources"]}
    assert formats == {"csv", "json"}
    # The materialized file would still be the real .zip, not a bare .csv/.json.
    assert all(item["basename"].endswith(".zip") for item in result["resources"])


def test_download_cumulative_dataset_picks_single_best_format(tmp_path) -> None:  # noqa: ANN001
    client = _FakePopulacaoAbastecidaClient()
    datasource = PortalFileDataSource(output_path=str(tmp_path), client=client)

    payload = datasource.download(dataset="sisagua_populacao_abastecida")

    # No year in any resource name -> falls back to the cumulative "None"
    # bucket and picks exactly one (csv preferred over json for this source).
    assert payload["downloaded_count"] == 1
    assert len(client.download_calls) == 1
    assert client.download_calls[0].endswith("_csv.zip")
