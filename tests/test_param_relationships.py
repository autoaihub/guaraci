"""Regressões da validação que cruza mais de um parâmetro.

Um intervalo invertido ou uma data impossível passavam pela validação e só
falhavam adiante, com a coleta já em andamento, ou eram ignorados pela origem
e devolviam o conjunto inteiro, o oposto do recorte pedido. Levantamento feito
sobre as 99 fontes registradas: 37 aceitavam ano invertido, 10 aceitavam ano
negativo e 10 aceitavam data malformada.
"""

from __future__ import annotations

import pytest

from guaraci.core.contracts import MINIMUM_YEAR, validate_param_relationships
from guaraci.services.downloads import DownloadService


@pytest.fixture(scope="module")
def service() -> DownloadService:
    return DownloadService()


# --- anos --------------------------------------------------------------------


def test_inverted_year_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="start_year"):
        validate_param_relationships({"start_year": 2024, "end_year": 2014})


def test_equal_years_are_accepted() -> None:
    validate_param_relationships({"start_year": 2020, "end_year": 2020})


def test_year_below_the_floor_is_rejected() -> None:
    with pytest.raises(ValueError, match=str(MINIMUM_YEAR)):
        validate_param_relationships({"start_year": -5, "end_year": -5})


def test_year_that_is_not_a_number_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be a year"):
        validate_param_relationships({"start_year": "ontem"})


def test_only_one_bound_is_fine() -> None:
    validate_param_relationships({"start_year": 2020})
    validate_param_relationships({"end_year": 2020})


# --- datas -------------------------------------------------------------------


def test_inverted_date_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="start_date"):
        validate_param_relationships(
            {"start_date": "2024-12-31", "end_date": "2024-01-01"}
        )


@pytest.mark.parametrize("valor", ["31/12/2024", "2024-13-01", "2024-02-30", "hoje"])
def test_malformed_or_impossible_dates_are_rejected(valor) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_param_relationships({"start_date": valor})


def test_valid_date_window_passes() -> None:
    validate_param_relationships(
        {"start_date": "2024-01-01", "end_date": "2024-01-31"}
    )


def test_blank_date_is_ignored() -> None:
    validate_param_relationships({"start_date": "  ", "end_date": "2024-01-31"})


# --- integrado ao serviço ----------------------------------------------------


def test_service_rejects_inverted_years_before_touching_the_network(service) -> None:
    with pytest.raises(ValueError):
        service.validate_source_params(
            "sinan", {"start_year": 2024, "end_year": 2014, "diseases": ["DENG"]}
        )


def test_service_rejects_malformed_date(service) -> None:
    with pytest.raises(ValueError):
        service.validate_source_params(
            "dengue",
            {"start_year": 2024, "end_year": 2024, "start_date": "31/12/2024"},
        )


def test_service_still_accepts_a_valid_request(service) -> None:
    service.validate_source_params(
        "sinan", {"start_year": 2014, "end_year": 2024, "diseases": ["DENG"]}
    )
    service.validate_source_params(
        "dengue",
        {
            "start_year": 2024,
            "end_year": 2024,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
    )


def test_no_registered_source_accepts_an_inverted_range(service) -> None:
    """Varredura ampla: a regra vale para toda fonte, não para uma lista."""
    aceitaram = []
    for descriptor in service.list_sources():
        nomes = {p["name"] for p in service.get_source_schema(descriptor.source)["params"]}
        if not {"start_year", "end_year"} <= nomes:
            continue
        try:
            service.validate_source_params(
                descriptor.source, {"start_year": 2024, "end_year": 2014}
            )
            aceitaram.append(descriptor.source)
        except Exception:
            pass
    assert aceitaram == []
