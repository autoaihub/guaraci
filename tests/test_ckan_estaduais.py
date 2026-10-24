"""Specs CKAN estaduais (Recife, GERCON, FHEMIG e SES-MG) com cliente fake, sem rede."""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.ckan import (
    BROWSER_USER_AGENT,
    CkanClient,
    ckan_datasource_for,
    resources_from_package,
    select_resources,
)
from guaraci.ckan.estaduais import CKAN_ESTADUAIS, FHEMIG_QUERY
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import ckan_estaduais

CSV = b'"A";"B"\n"1";"Cora\xe7\xe3o"\n'


class _Fake:
    def __init__(self, package, files=None):
        self.package = package
        self.files = files or {}
        self.downloaded = []
        self.queries = []

    def resources(self, package_id):
        return resources_from_package(self.package)

    def package_search(self, q=None, fq=None, rows=1000, start=0):
        self.queries.append(fq)
        return {"count": 1, "results": [self.package] if start == 0 else []}

    def download(self, url, destination, progress_callback=None):
        self.downloaded.append(url)
        data = self.files.get(url, CSV)
        Path(destination).write_bytes(data)
        return len(data)


def _pkg(*items):
    return {
        "name": "p",
        "resources": [
            {"id": str(i), "name": n, "url": u, "format": f}
            for i, (n, u, f) in enumerate(items)
        ],
    }


def _recife_package():
    base = "https://dados.recife.pe.gov.br:443/dataset/x/resource/"
    return _pkg(
        ("Casos de Dengue 2025", base + "a/download/casos-de-dengue-2025.csv", "CSV"),
        # URL de dengue que cita chikungunya não pode vazar para a chave da chikungunya.
        ("Casos de Dengue 2023", base + "b/download/dengue-chikungunya-2023.csv", "CSV"),
        ("Casos de Dengue em 2013", base + "c/download/casos-de-dengue-em-2013.csv", "CSV"),
        ("Casos confirmados de Chikungunya em 2025", base + "d/download/chik-2025.csv", "CSV"),
        ("Casos confirmados de Chikungunya em 2015", base + "e/download/chik-2015.csv", "CSV"),
        ("Casos confirmados de Zika 2024", base + "f/download/zika-2024.csv", "CSV"),
        ("Tabela de Bairros", base + "g/download/tabela-de-bairros.csv", "CSV"),
        ("Metadados dos Casos confirmados de Zika", base + "h/download/meta.json", "JSON"),
    )


def _picked(key, package, **kwargs):
    spec = CKAN_ESTADUAIS[key]
    chosen, _, _ = select_resources(spec, resources_from_package(package), **kwargs)
    return [(r.name, p) for r, p in chosen]


def test_recife_separa_os_tres_agravos_pelo_nome_e_le_o_ano():
    package = _recife_package()
    dengue = _picked("recife_dengue", package)
    assert [p for _, p in dengue] == [(2025, None), (2023, None), (2013, None)]
    assert all(n.startswith("Casos de Dengue") for n, _ in dengue)
    chik = _picked("recife_chikungunya", package)
    assert [n for n, _ in chik] == [
        "Casos confirmados de Chikungunya em 2025",
        "Casos confirmados de Chikungunya em 2015",
    ]
    assert _picked("recife_zika", package) == [("Casos confirmados de Zika 2024", (2024, None))]


def test_recife_seleciona_por_ano():
    package = _recife_package()
    assert [p for _, p in _picked("recife_dengue", package, anos=[2013, 2025])] == [
        (2025, None),
        (2013, None),
    ]
    assert _picked("recife_chikungunya", package, anos=["2015"])[0][1] == (2015, None)


def test_recife_baixa_e_exporta_utf8(tmp_path):
    package = _recife_package()
    client = _Fake(package)
    source = ckan_datasource_for(CKAN_ESTADUAIS["recife_zika"])(
        output_path=str(tmp_path), client=client
    )
    result = source.download(output_format="csv")
    assert result["documents_found"] == 1
    out = Path(result["exported_files"][0])
    assert out.name == "recife_zika__zika_2024.csv"
    assert "Coração" in out.read_text(encoding="utf-8")


def test_gercon_exige_anos_e_escolhe_o_arquivo_do_ano():
    spec = CKAN_ESTADUAIS["poa_gercon_consultas"]
    base = "https://dadosabertos.poa.br/dataset/x/resource/"
    package = _pkg(
        ("Dicionário de Dados", base + "d/download/dicionario.pdf", "PDF"),
        ("Solicitação de consultas especializadas 2025", base + "a/download/gercon_solicitacoes_2025.csv", "CSV"),
        ("Solicitação de consultas especializadas 2017", base + "b/download/gercon_solicitacoes_2017.csv", "CSV"),
    )
    resources = resources_from_package(package)
    with pytest.raises(ValueError, match="anos"):
        select_resources(spec, resources)
    chosen, _, _ = select_resources(spec, resources, anos=[2017])
    assert [p for _, p in chosen] == [(2017, None)]
    client = _Fake(package)
    source = ckan_datasource_for(spec)(output_path="unused", client=client)
    with pytest.raises(ValueError, match="anos"):
        source.download()
    assert client.downloaded == []


def test_fhemig_usa_package_query_ua_de_navegador_e_recursos(tmp_path):
    spec = CKAN_ESTADUAIS["fhemig_indicadores_hospitalares"]
    assert spec.package_query == FHEMIG_QUERY and spec.browser_user_agent
    base = "https://dados.mg.gov.br/dataset/x/resource/"
    package = _pkg(
        ("Dados", base + "a/download/taxa-readmissao-2025.csv", "CSV"),
        ("Dados", base + "b/download/case-mix-2025.csv", "CSV"),
        ("Datapackage", base + "c/download/datapackage.json", "JSON"),
    )
    client = _Fake(package)
    source = ckan_datasource_for(spec)(output_path=str(tmp_path), client=client)
    result = source.download(output_format="csv", recursos=["readmissao"])
    assert client.queries == [FHEMIG_QUERY]
    assert result["documents_found"] == 1
    assert client.downloaded == [base + "a/download/taxa-readmissao-2025.csv"]
    made = ckan_datasource_for(spec)(output_path=str(tmp_path))._make_client(30)
    assert made.user_agent == BROWSER_USER_AGENT


def test_mg_ses_baixa_o_recurso_csv_e_ignora_o_datapackage(tmp_path):
    spec = CKAN_ESTADUAIS["mg_hanseniase"]
    base = "https://dados.mg.gov.br/dataset/x/resource/"
    package = _pkg(
        ("Dados", base + "a/download/dados_hanseniase.csv", "CSV"),
        ("Datapackage", base + "b/download/datapackage.json", "JSON"),
    )
    client = _Fake(package, {base + "a/download/dados_hanseniase.csv": b"dt;nome\n2019;Itu\xe1\n"})
    source = ckan_datasource_for(spec)(output_path=str(tmp_path), client=client)
    result = source.download(output_format="csv")
    assert result["documents_found"] == 1
    assert Path(result["exported_files"][0]).read_text(encoding="utf-8").splitlines()[1] == "2019,Ituá"


def test_registro_responde_ao_schema_e_so_recife_e_gercon_trazem_anos():
    service = DownloadService(sources=ckan_estaduais.build_sources())
    assert set(CKAN_ESTADUAIS) == {
        "recife_dengue", "recife_chikungunya", "recife_zika", "poa_gercon_consultas",
        "fhemig_indicadores_hospitalares", "mg_hanseniase", "mg_aids_hiv", "mg_tuberculose",
        "mg_acidentes_transporte",
    }
    for key, spec in CKAN_ESTADUAIS.items():
        schema = service.get_source_schema(key)
        names = {p["name"] for p in schema["params"]}
        assert {"recursos", "output_format"} <= names
        assert ("anos" in names) == (key.startswith("recife") or key.startswith("poa"))
    anos = [p for p in service.get_source_schema("poa_gercon_consultas")["params"] if p["name"] == "anos"]
    assert anos[0]["required"] is True


def test_descricoes_sem_travessao_e_com_nota_de_dado_pessoal():
    for key, spec in CKAN_ESTADUAIS.items():
        text = spec.title + spec.description
        assert "—" not in text and "–" not in text, key
        if key.startswith(("recife", "mg_", "poa")):
            assert "LGPD" in spec.description, key
