"""Regressões da resolução de endpoints DEMAS.

Levantadas por uma varredura ao vivo das 51 fontes OpenDataSUS registradas,
que apontou 6 falhas: um caminho grafado com underscore onde a origem usa
hífen, uma série anual pedida fora da cobertura publicada, e endpoints
removidos pela origem.
"""

from __future__ import annotations

import pytest

from guaraci.opendatasus.datasource import OpenDataSUSDataSource
from guaraci.services.downloads import DownloadService

BASE_GRIPAL = "/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve"


@pytest.fixture(scope="module")
def datasource() -> OpenDataSUSDataSource:
    return OpenDataSUSDataSource(output_path=".")


def _plan(datasource, dataset: str, start_year: int, end_year: int):
    spec = datasource.DATASET_SPECS[dataset]
    return datasource._resolve_demas_endpoints(
        spec=spec,
        dataset=dataset,
        start_year=start_year,
        end_year=end_year,
        api_params={},
    )


# --- séries publicadas por ano ----------------------------------------------


def test_yearly_series_covers_only_the_published_years(datasource) -> None:
    """A origem publica um endpoint por ano e a série não é infinita."""
    planos = _plan(datasource, "sindrome_gripal_leve", 2023, 2024)
    caminhos = [item.path for item in planos]
    assert caminhos == [f"{BASE_GRIPAL}-2023", f"{BASE_GRIPAL}-2024"]


def test_years_outside_the_series_are_skipped(datasource) -> None:
    """Pedir 2023-2026 traz os anos que existem, não um 404 no meio do caminho."""
    planos = _plan(datasource, "sindrome_gripal_leve", 2023, 2026)
    anos = [item.path.rsplit("-", 1)[-1] for item in planos]
    assert anos == ["2023", "2024"]


def test_asking_only_for_missing_years_says_what_is_available(datasource) -> None:
    """Antes, o pedido terminava num 404 opaco da origem."""
    with pytest.raises(ValueError, match="Available years"):
        _plan(datasource, "sindrome_gripal_leve", 2026, 2026)


def test_the_error_names_the_covered_range(datasource) -> None:
    with pytest.raises(ValueError, match="2020-2024"):
        _plan(datasource, "sindrome_gripal_leve", 2030, 2030)


# --- caminhos declarados no catálogo ----------------------------------------


def test_epi_supply_endpoint_uses_the_hyphenated_path() -> None:
    """A origem serve `distribuicao-epi-insumo`; o catálogo trazia underscore."""
    service = DownloadService()
    schema = service.get_source_schema("prevencao_e_promocao_distribuicao_epi_insumo")
    assert schema["source"] == "prevencao_e_promocao_distribuicao_epi_insumo"

    fonte = service._get_registered_source(
        "prevencao_e_promocao_distribuicao_epi_insumo"
    )
    assert fonte.fixed_dataset == "prevencao-e-promocao/distribuicao-epi-insumo"


def test_registry_paths_have_no_stray_underscore_segment() -> None:
    """Os caminhos da DEMAS usam hífen entre palavras; underscore era erro nosso.

    A checagem cobre apenas o último segmento dos valores que são caminho de
    API (os que têm barra); as fontes declaradas à mão guardam aí o nome do
    dataset, que segue a convenção com underscore. Parâmetros de caminho entre
    chaves são tolerados.
    """
    service = DownloadService()
    suspeitos = []
    for descriptor in service.list_sources():
        fonte = service._get_registered_source(descriptor.source)
        caminho = getattr(fonte, "fixed_dataset", None)
        if not caminho or "/" not in caminho:
            continue
        ultimo = caminho.rstrip("/").rsplit("/", 1)[-1]
        if "_" in ultimo and "{" not in ultimo:
            suspeitos.append((descriptor.source, caminho))
    assert suspeitos == []
