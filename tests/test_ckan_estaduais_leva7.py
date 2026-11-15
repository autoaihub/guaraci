"""Specs CKAN da leva 7 (SEADE de SP e SES-GO) com cliente fake, sem rede.

Os pacotes simulados repetem a forma dos reais verificados em 2026-11-14: o CSV de dados
ao lado do CSV de dicionário (SEADE) e do PDF de dicionário (SES-GO).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.ckan import (
    BROWSER_USER_AGENT,
    ckan_datasource_for,
    resources_from_package,
    select_resources,
)
from guaraci.ckan.estaduais import CKAN_ESTADUAIS, GO_BASE_URL, SEADE_BASE_URL
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import ckan_estaduais

SEADE_KEYS = {
    "seade_obitos_sp_serie",
    "seade_obitos_sp_ano_corrente",
    "seade_nascidos_vivos_sp_serie",
    "seade_nascidos_vivos_sp_ano_corrente",
    "seade_mortalidade_geral_sp",
    "seade_mortalidade_infantil_sp",
    "seade_esperanca_vida_sp",
    "seade_fecundidade_sp",
    "seade_saude_painel_sp",
    "seade_ipvs_2022",
    "seade_ipvs_2010",
}
GO_KEYS = {
    "ses_go_mapa_leitos",
    "ses_go_dengue",
    "ses_go_zika_chikungunya",
    "ses_go_arboviroses_internacao",
    "ses_go_srag",
    "ses_go_sindrome_gripal",
    "ses_go_mortalidade",
    "ses_go_hiv_aids",
    "ses_go_sifilis",
    "ses_go_hepatites",
    "ses_go_tuberculose",
    "ses_go_hanseniase",
    "ses_go_regulacao_indicadores",
    "ses_go_oncologia",
}
NOVAS = SEADE_KEYS | GO_KEYS
D = chr(0x2014)  # o portal usa travessão nos nomes dos recursos


class _Fake:
    def __init__(self, packages, files=None):
        self.packages = packages
        self.files = files or {}
        self.downloaded = []

    def resources(self, package_id):
        return resources_from_package(self.packages[package_id])

    def download(self, url, destination, progress_callback=None):
        self.downloaded.append(url)
        data = self.files.get(url, b'"a";"b"\n"1";"Cora\xe7\xe3o"\n')
        Path(destination).write_bytes(data)
        return len(data)


def _pkg(name, *items):
    return {
        "name": name,
        "resources": [
            {"id": str(i), "name": n, "url": u, "format": f} for i, (n, u, f) in enumerate(items)
        ],
    }


def _picked(key, package, **kwargs):
    spec = CKAN_ESTADUAIS[key]
    chosen, _, _ = select_resources(spec, resources_from_package(package), **kwargs)
    return [(r.name, p) for r, p in chosen]


def test_chaves_novas_registradas_e_as_nove_antigas_intactas():
    assert NOVAS <= set(CKAN_ESTADUAIS)
    assert len(NOVAS) == 25
    assert CKAN_ESTADUAIS["recife_dengue"].resource_pattern == r"^Casos de Dengue"
    assert CKAN_ESTADUAIS["mg_hanseniase"].browser_user_agent is True


def test_seade_exclui_o_dicionario_e_o_pdf_e_nao_le_periodo_do_nome():
    base = "https://repositorio.seade.gov.br/dataset/x/resource/"
    package = _pkg(
        "obitos",
        ("Óbitos por sexo e faixa etária - 2019 a 2025", base + "a/download/obitos_sexo_idade_periodo.csv", "CSV"),
        (f"Dicionário {D} Óbitos por sexo e faixa etária - 2019 a 2025", base + "b/download/dic_variaveis_obito_sexo_idade_periodo.csv", "CSV"),
        ("Óbitos - 2000 a 2025", base + "c/download/obitos_gerais_esp_periodo.csv", "CSV"),
        # nome do arquivo de dicionário sem a palavra no nome do recurso: o prefixo dic na URL basta
        ("Variáveis", base + "d/download/dicvar_obitos_mesocorrencia_2018a2021.csv", "CSV"),
        (f"Anexo Metodológico {D} Óbitos do ESP", base + "e/download/anexo-metodologico_obitos.pdf", "PDF"),
    )
    chosen = _picked("seade_obitos_sp_serie", package)
    assert [n for n, _ in chosen] == [
        "Óbitos por sexo e faixa etária - 2019 a 2025",
        "Óbitos - 2000 a 2025",
    ]
    spec = CKAN_ESTADUAIS["seade_obitos_sp_serie"]
    assert spec.base_url == SEADE_BASE_URL
    assert not spec.has_period and not spec.browser_user_agent


def test_seade_ano_corrente_mantem_as_duas_tabelas_de_dados():
    base = "https://repositorio.seade.gov.br/dataset/x/resource/"
    package = _pkg(
        "obitos-estado-de-sp-ano-corrente",
        ("Óbitos por sexo e faixa etária - 2026", base + "a/download/obitos_sexo_idade_anoatual.csv", "CSV"),
        (f"Dicionário {D} Óbitos por sexo e faixa etária - 2026", base + "b/download/dicvariaveis_obitos_sexo_idade_anoatual.csv", "CSV"),
        ("Óbitos por mês de ocorrência - 2026", base + "c/download/obitos_mes_anoatual.csv", "CSV"),
        (f"Dicionário {D} Óbitos por mês de ocorrência - 2026", base + "d/download/dicvariaveis_obitos_mes_anoatual.csv", "CSV"),
    )
    names = [n for n, _ in _picked("seade_obitos_sp_ano_corrente", package)]
    assert names == ["Óbitos por sexo e faixa etária - 2026", "Óbitos por mês de ocorrência - 2026"]


def test_seade_baixa_e_exporta_utf8_pelo_pacote_da_chave(tmp_path):
    base = "https://repositorio.seade.gov.br/dataset/x/resource/"
    package = _pkg(
        "esperanca-de-vida",
        ("Esperança de Vida", base + "a/download/esperanca_vida.csv", "CSV"),
        (f"Dicionário {D} Esperança de Vida", base + "b/download/dicvar_esperanca_vida.csv", "CSV"),
        ("Anexo Metodológico ─ Esperança de Vida", base + "c/download/painel_esperanca_vida.pdf", "PDF"),
    )
    client = _Fake({"esperanca-de-vida": package})
    source = ckan_datasource_for(CKAN_ESTADUAIS["seade_esperanca_vida_sp"])(
        output_path=str(tmp_path), client=client
    )
    result = source.download(output_format="csv")
    assert result["documents_found"] == 1
    assert client.downloaded == [base + "a/download/esperanca_vida.csv"]
    out = Path(result["exported_files"][0])
    assert out.name == "seade_esperanca_vida_sp__esperanca_vida.csv"
    assert "Coração" in out.read_text(encoding="utf-8")


def test_seade_fecundidade_escolhe_so_os_dados_e_aceita_recursos():
    base = "https://repositorio.seade.gov.br/dataset/x/resource/"
    package = _pkg(
        "seade-fecundidade",
        ("Fecundidade total ─ Estado de São Paulo e regiões", base + "a/download/fecundidade_total.csv", "CSV"),
        ("Dicionário ─ Fecundidade total", base + "b/download/dicvariaveis_fecundidade_total.csv", "CSV"),
        ("Fecundidade e natalidade por municípios", base + "c/download/fecundidade_natalidade_municipios_serie.csv", "CSV"),
        ("Dicionário ─ Fecundidade e natalidade por municípios", base + "d/download/dicvariaveis_fecundidade_natalidade_municipios_serie.csv", "CSV"),
    )
    spec = CKAN_ESTADUAIS["seade_fecundidade_sp"]
    chosen, _, _ = select_resources(
        spec, resources_from_package(package), recursos=["municipios_serie"]
    )
    assert [r.name for r, _ in chosen] == ["Fecundidade e natalidade por municípios"]


def test_go_ignora_o_pdf_de_dicionario_e_usa_o_ua_padrao(tmp_path):
    base = "https://dadosabertos.go.gov.br/dataset/x/resource/"
    package = _pkg(
        "ist-hiv",
        ("DICIONARIO_DE_DADOS_IST_HIV", base + "a/download/dicionario_de_dados_ist_hiv.pdf", "PDF"),
        ("HIV - Casos", base + "b/download/hiv-casos.csv", "CSV"),
        ("HIV - Crianças", base + "c/download/hiv-criancas.csv", "CSV"),
    )
    package_aids = _pkg(
        "ist-aids",
        ("IST - AIDS Adulto", base + "d/download/aids-adulto.csv", "CSV"),
        ("IST - AIDS Óbitos", base + "e/download/aids-obitos.csv", "CSV"),
    )
    spec = CKAN_ESTADUAIS["ses_go_hiv_aids"]
    assert spec.package_ids == ("ist-hiv", "ist-aids")
    assert spec.base_url == GO_BASE_URL and not spec.browser_user_agent
    client = _Fake({"ist-hiv": package, "ist-aids": package_aids})
    source = ckan_datasource_for(spec)(output_path=str(tmp_path), client=client)
    result = source.download(output_format="csv", recursos=["hiv-criancas", "aids-obitos"])
    assert result["documents_found"] == 2
    assert client.downloaded == [base + "c/download/hiv-criancas.csv", base + "e/download/aids-obitos.csv"]
    made = ckan_datasource_for(spec)(output_path=str(tmp_path))._make_client(30)
    assert made.user_agent != BROWSER_USER_AGENT


def test_go_nome_sem_ano_nao_gera_filtro_de_periodo():
    base = "https://dadosabertos.go.gov.br/dataset/x/resource/"
    package = _pkg(
        "mapa-de-leitos",
        ("Histórico de leitos", base + "a/download/historico_de_leitos.csv", "CSV"),
        ("Histórico de leitos (UTI Neonatal)", base + "b/download/historico_de_leitos_uti_neonatal.csv", "CSV"),
    )
    assert len(_picked("ses_go_mapa_leitos", package)) == 2
    assert not CKAN_ESTADUAIS["ses_go_mapa_leitos"].has_period


@pytest.mark.parametrize("key", sorted(NOVAS))
def test_cada_chave_nova_tem_pacote_url_https_e_formato_csv(key):
    spec = CKAN_ESTADUAIS[key]
    assert spec.package_ids and not spec.package_query
    assert spec.base_url in (SEADE_BASE_URL, GO_BASE_URL)
    assert spec.file_format == "csv" and spec.separator == ";"
    assert spec.browser_user_agent is False
    assert (spec.exclude_pattern is not None) is key.startswith("seade_")


def test_registro_responde_ao_schema_sem_anos_nas_chaves_novas():
    service = DownloadService(sources=ckan_estaduais.build_sources())
    for key in NOVAS:
        names = {p["name"] for p in service.get_source_schema(key)["params"]}
        assert {"recursos", "output_format"} <= names
        assert "anos" not in names


def test_descricoes_sem_travessao_e_com_nota_de_dado_pessoal():
    individuais = {"ses_go_srag", "ses_go_tuberculose", "ses_go_sindrome_gripal",
                   "ses_go_arboviroses_internacao", "ses_go_oncologia"}
    for key in NOVAS:
        spec = CKAN_ESTADUAIS[key]
        text = spec.title + spec.description
        assert chr(0x2014) not in text and chr(0x2013) not in text, key
        assert "identificador pessoal" in text or "LGPD" in text, key
        if key in individuais:
            assert "LGPD" in spec.description, key
