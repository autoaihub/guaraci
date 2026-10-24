"""Turno 2 do Pacote B: RENAEST, BNDES e MAPA sobre o núcleo CKAN (offline)."""

from __future__ import annotations

from guaraci.ckan import CkanResource, resources_from_package, select_resources
from guaraci.ckan.federal import CKAN_FEDERAL
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import ckan_federal

NOVAS = {
    "senatran_renaest", "bndes_operacoes_financiamento", "bndes_desembolsos_mensais",
    "mapa_agrofit", "mapa_sif", "mapa_sipeagro",
}


def _res(i, name, url, fmt="ZIP"):
    return CkanResource(package_id="p", id=str(i), name=name, url=url, format=fmt)


def test_renaest_baixa_so_o_zip_mais_novo_e_le_mes_ano_do_nome():
    spec = CKAN_FEDERAL["senatran_renaest"]
    base = "https://dados.transportes.gov.br/dataset/x/resource/y/download/"
    resources = [
        _res(1, "RENAEST - Mensal - 12-2025", base + "renaest_dabertos_20260412.zip"),
        _res(2, "RENAEST - Mensal - 05-2026", base + "renaest_dabertos_20260912.zip"),
        _res(3, "RENAEST - Mensal -01-2025", base + "renaest_dabertos_20250512.zip"),
        _res(4, "RENAEST - Mensal - 10-2021", base + "dabertos_20220215.zip"),
    ]
    chosen, _, latest = select_resources(spec, resources)
    assert latest and chosen[0][0].id == "2" and chosen[0][1] == (2026, 5)
    chosen, _, _ = select_resources(spec, resources, anos=[2025], meses=["01"])
    assert [c[0].id for c in chosen] == ["3"]


def test_bndes_descarta_dicionario_pdf_e_baixa_cada_csv():
    base = "https://dadosabertos.bndes.gov.br/dataset/d/resource/r/download/"
    resources = [
        _res(1, "Dicionário de dados", base + "dicionario.pdf", "PDF"),
        _res(2, "Operações indiretas automáticas", base + "operacoes-indiretas-automaticas.csv", "CSV"),
        _res(3, "Operações não automáticas", base + "operacoes-nao-automaticas.csv", "CSV"),
    ]
    chosen, _, latest = select_resources(CKAN_FEDERAL["bndes_operacoes_financiamento"], resources)
    assert not latest and [c[0].id for c in chosen] == ["2", "3"]


def test_mapa_usa_user_agent_de_navegador_e_ignora_pdf():
    package = {"name": "p", "resources": [
        {"id": "1", "name": "A", "url": "https://x/sigsifa.csv", "format": "CSV"},
        {"id": "2", "name": "Dicionário", "url": "https://x/dic.pdf", "format": "PDF"},
        {"id": "3", "name": "B", "url": "https://x/sigsifb.csv", "format": ".CSV"},
    ]}
    resources = resources_from_package(package)
    for key in ("mapa_agrofit", "mapa_sif", "mapa_sipeagro"):
        spec = CKAN_FEDERAL[key]
        assert spec.browser_user_agent and not spec.has_period
        chosen, _, latest = select_resources(spec, resources)
        assert not latest and [c[0].id for c in chosen] == ["1", "3"]


def test_chaves_novas_respondem_ao_schema():
    service = DownloadService(sources=ckan_federal.build_sources())
    assert NOVAS <= set(CKAN_FEDERAL)
    for key in NOVAS:
        names = {p["name"] for p in service.get_source_schema(key)["params"]}
        assert {"recursos", "output_format"} <= names
        assert ("anos" in names) == CKAN_FEDERAL[key].has_period
    assert "anos" in {p["name"] for p in service.get_source_schema("senatran_renaest")["params"]}
