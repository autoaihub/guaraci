"""Tradução do catálogo do site (en, es), sem rede: cobertura, travessões e falha de fonte nova."""

from __future__ import annotations

import json

import pytest

from guaraci.services.same_as import SAME_AS
from scripts import build_site_catalog as bsc

LANGS = bsc.LANGS


def _entries(lang: str) -> dict:
    return json.loads((bsc.I18N_DIR / f"catalog.{lang}.json").read_text(encoding="utf-8"))


def _terms(lang: str) -> dict:
    return json.loads((bsc.I18N_DIR / f"terms.{lang}.json").read_text(encoding="utf-8"))


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        # só os valores: as chaves das tabelas são o texto em português da fonte
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _fake_catalog() -> dict:
    """Catálogo mínimo, com as chaves e os grupos e mantenedores reais do CURATED."""
    catalog = {}
    for key, (_n, _d, g, m, _area) in bsc.CURATED.items():
        catalog[key] = {"g": g, "m": m, "modeLabel": "API OpenDataSUS (DEMAS)", "cadence": "mensal"}
        if key in SAME_AS:
            catalog[key]["sameAsNote"] = SAME_AS[key][1]
    return catalog


@pytest.mark.parametrize("lang", LANGS)
def test_toda_chave_do_catalogo_tem_descricao_traduzida(lang):
    entries = _entries(lang)
    sem_d = [k for k in bsc.CURATED if not (entries.get(k) or {}).get("d")]
    assert sem_d == []
    assert set(entries) == set(bsc.CURATED)


@pytest.mark.parametrize("lang", LANGS)
def test_nota_de_same_as_e_termos_cobrem_o_catalogo(lang):
    entries, terms = _entries(lang), _terms(lang)
    assert [k for k in SAME_AS if not entries[k].get("sameAsNote")] == []
    assert {c[2] for c in bsc.CURATED.values()} <= set(terms["groups"])
    assert {c[3] for c in bsc.CURATED.values()} <= set(terms["maintainers"])


@pytest.mark.parametrize("lang", LANGS)
def test_texto_traduzido_nao_tem_travessao_nem_traco(lang):
    fontes = [_entries(lang), _terms(lang), bsc.MODE_I18N[lang], bsc.CADENCE_I18N[lang],
              bsc.VOLUME_I18N[lang], bsc.DOCS_I18N[lang]]
    ruins = [s for f in fontes for s in _strings(f) if "—" in s or "–" in s]
    assert ruins == []


@pytest.mark.parametrize("lang", LANGS)
def test_build_i18n_gera_os_campos_do_contrato(lang):
    data = bsc.build_i18n(_fake_catalog(), {})[lang]
    assert len(data) == len(bsc.CURATED)
    for key, t in data.items():
        assert {"d", "g", "m", "modeLabel", "cadence"} <= set(t)
        assert set(t) <= {"n", "d", "g", "m", "sameAsNote", "volume", "modeLabel", "cadence"}
        assert ("sameAsNote" in t) == (key in SAME_AS)
    assert data["sih"]["cadence"] == bsc.CADENCE_I18N[lang]["mensal"]


def test_fonte_nova_sem_traducao_derruba_o_gerador():
    catalog = _fake_catalog()
    catalog["fonte_nova_sem_traducao"] = dict(catalog["sih"])
    with pytest.raises(SystemExit) as exc:
        bsc.build_i18n(catalog, {})
    assert "fonte_nova_sem_traducao" in str(exc.value)


def test_rotulos_de_cadencia_cobrem_todos_os_valores():
    for lang in LANGS:
        assert set(bsc.CADENCE_PT.values()) <= set(bsc.CADENCE_I18N[lang])


def test_selo_de_volume_traduzido():
    est = {"method": "medido", "csv_bytes": 1_200_000_000}
    assert bsc.volume_label(est) == "histórico completo ≈ 1,2 GB em CSV"
    assert bsc.volume_label(est, "en") == "full history ≈ 1.2 GB as CSV"
    assert bsc.volume_label(est, "es") == "historial completo ≈ 1,2 GB en CSV"
    assert bsc.volume_label({"method": "sob demanda"}, "en") == "volume: on demand"
