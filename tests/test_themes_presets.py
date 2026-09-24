"""Tests for the theme vocabulary and the cross-source thematic presets.

Three families of guarantee live here:

1. **Integrity of the maps.** A typo in a theme slug, or an entry pointing at a
   source that no longer exists, would fail silently in production: the source
   would simply stop showing up under its theme. These tests turn both into a
   red build.
2. **Fidelity of the presets.** A preset is code that describes *other*
   sources' parameters, so it rots whenever a spec changes. The params of every
   step are validated against the live schema.
3. **Honesty of the presets.** A step that collects a whole base and still
   needs a post-collection filter must say so. A preset that hid that would
   hand the user a cut they believe is ready and is not.
"""

from __future__ import annotations

import importlib.util

import pytest

from guaraci.services import presets as presets_mod
from guaraci.services import themes as themes_mod
from guaraci.services.downloads import DownloadService


@pytest.fixture(scope="module")
def service() -> DownloadService:
    return DownloadService()


@pytest.fixture(scope="module")
def registered(service: DownloadService) -> set[str]:
    return {descriptor.source for descriptor in service.list_sources()}


# --- Integrity of the maps --------------------------------------------------


def test_no_phantom_theme_slugs() -> None:
    """Every slug cited in the maps must exist in the theme vocabulary."""
    assert themes_mod.unknown_theme_slugs() == ()


def test_theme_slugs_are_unique() -> None:
    slugs = [theme.slug for theme in themes_mod.THEMES.values()]
    assert len(slugs) == len(set(slugs))


def test_explicit_map_has_no_dead_entries(registered: set[str]) -> None:
    """A hand-curated entry pointing at an unregistered source is dead weight."""
    dead = sorted(set(themes_mod._EXPLICIT) - registered)
    assert not dead, f"themes._EXPLICIT points at unregistered sources: {dead}"


def test_every_registered_source_is_classified(service: DownloadService) -> None:
    """No source may sit outside the navigation.

    This is deliberately strict. The OpenDataSUS family is generated from the
    DEMAS Swagger and grows on its own, so a new upstream dataset will fail
    this test. That is the intent: an unclassified source is invisible to
    anyone browsing by subject, which is precisely the problem the theme map
    exists to solve. The fix is one line in ``themes._EXPLICIT`` or a new
    prefix rule.
    """
    unclassified = sorted(
        descriptor.source for descriptor in service.list_sources() if not descriptor.themes
    )
    assert not unclassified, (
        "these sources have no theme; add them to themes._EXPLICIT or to a "
        f"prefix rule: {unclassified}"
    )


def test_themes_for_is_case_insensitive_and_trims() -> None:
    assert themes_mod.themes_for("  SISCAN  ") == themes_mod.themes_for("siscan")


def test_themes_for_unknown_source_returns_empty_rather_than_raising() -> None:
    assert themes_mod.themes_for("fonte_que_nao_existe") == ()


def test_explicit_map_wins_over_prefix_rule() -> None:
    """``cnes`` is curated; ``cnes_*`` falls to the prefix rule."""
    assert themes_mod.themes_for("cnes") == ("estabelecimentos", "forca_trabalho")
    assert themes_mod.themes_for("cnes_tipounidades") == ("estabelecimentos",)


# --- Theme filtering --------------------------------------------------------


def test_list_sources_rejects_unknown_theme(service: DownloadService) -> None:
    with pytest.raises(ValueError, match="Unknown theme"):
        service.list_sources(theme="oncologiaa")


def test_list_sources_filtered_returns_only_that_theme(service: DownloadService) -> None:
    filtered = service.list_sources(theme="oncologia")
    assert filtered
    for descriptor in filtered:
        assert "oncologia" in descriptor.themes


def test_oncology_theme_reaches_every_expected_system(service: DownloadService) -> None:
    """The point of the theme: 'where is the cancer data?' answered in full."""
    found = {descriptor.source for descriptor in service.list_sources(theme="oncologia")}
    assert {"siscan", "sia", "painel_oncologia", "sih", "sim"} <= found


def test_list_sources_unfiltered_is_unchanged_in_size(service: DownloadService) -> None:
    assert len(service.list_sources(theme=None)) == len(service.list_sources())


def test_theme_counts_match_the_filtered_listing(service: DownloadService) -> None:
    by_slug = {item["slug"]: item["source_count"] for item in service.list_themes()}
    for slug, count in by_slug.items():
        assert count == len(service.list_sources(theme=slug)), slug


def test_descriptor_themes_are_populated_on_read(service: DownloadService) -> None:
    """Adapters never declare themes; the service attaches them."""
    from guaraci.services.sources import build_default_sources

    raw = {src.descriptor.source: src.descriptor for src in build_default_sources()}
    assert raw["siscan"].themes == ()
    enriched = {d.source: d for d in service.list_sources()}
    assert enriched["siscan"].themes == ("oncologia",)


# --- Presets ----------------------------------------------------------------


def test_preset_sources_are_registered(registered: set[str]) -> None:
    for preset in presets_mod.PRESETS.values():
        for step in preset.steps:
            assert step.source in registered, f"{preset.name} -> {step.source}"


def test_preset_params_validate_against_live_schemas(service: DownloadService) -> None:
    """Guards against a preset that names a group a spec no longer offers."""
    for name in presets_mod.preset_names():
        service.get_preset(name)  # raises if any step's params are invalid


def test_preset_themes_exist() -> None:
    for preset in presets_mod.PRESETS.values():
        for slug in preset.themes:
            assert slug in themes_mod.THEMES, f"{preset.name} -> {slug}"


def test_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="Unknown preset"):
        presets_mod.get_preset("cardiologia")


def test_oncology_preset_selects_the_apac_groups_the_sia_default_omits(
    service: DownloadService,
) -> None:
    """The whole reason the preset exists: SIA defaults to PA, not to AQ/AR."""
    from guaraci.datasus.ftp import specs

    assert specs.SIA.default_groups == ("PA",)
    step = next(s for s in presets_mod.get_preset("oncologia").steps if s.source == "sia")
    assert step.params["groups"] == ["AQ", "AR"]


def test_oncology_preset_declares_the_post_collection_filters() -> None:
    """SIH and SIM come whole; the preset must not pretend otherwise."""
    steps = {s.source: s for s in presets_mod.get_preset("oncologia").steps}
    for name in ("sih", "sim"):
        assert steps[name].refine, f"{name} needs a declared post-collection filter"
        assert "CID" in steps[name].refine
    # Conversely, the steps that ARE fully cut at collection must not claim a
    # pending filter, or the user would look for work that does not exist.
    for name in ("siscan", "sia"):
        assert steps[name].refine is None


def test_oncology_preset_admits_it_has_no_incidence_data() -> None:
    """The known limitation is declared, not implied by absence."""
    caveats = " ".join(presets_mod.get_preset("oncologia").caveats).upper()
    assert "INCID" in caveats
    assert "RCBP" in caveats


def test_presets_for_theme() -> None:
    assert [p.name for p in presets_mod.presets_for_theme("oncologia")] == ["oncologia"]
    assert presets_mod.presets_for_theme("gestao") == []


def test_preset_steps_all_carry_a_rationale() -> None:
    """A step without a stated reason is a step nobody can audit."""
    for preset in presets_mod.PRESETS.values():
        for step in preset.steps:
            assert step.rationale.strip(), f"{preset.name} -> {step.source}"


# --- API surface ------------------------------------------------------------

_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None


@pytest.mark.skipif(not _HAS_FASTAPI, reason="Requires fastapi to be installed")
class TestThemeAndPresetEndpoints:
    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from guaraci.api import main as api_main

        return TestClient(api_main.app)

    def test_themes_endpoint(self, client) -> None:
        response = client.get("/themes")
        assert response.status_code == 200
        payload = response.json()
        slugs = {item["slug"] for item in payload}
        assert "oncologia" in slugs
        for item in payload:
            assert item["label"] and item["description"]
            assert item["source_count"] >= 0

    def test_sources_endpoint_exposes_themes(self, client) -> None:
        response = client.get("/sources")
        assert response.status_code == 200
        by_source = {item["source"]: item for item in response.json()}
        assert by_source["siscan"]["themes"] == ["oncologia"]

    def test_sources_endpoint_theme_filter(self, client) -> None:
        response = client.get("/sources", params={"theme": "oncologia"})
        assert response.status_code == 200
        payload = response.json()
        assert payload
        assert all("oncologia" in item["themes"] for item in payload)

    def test_sources_endpoint_rejects_unknown_theme(self, client) -> None:
        response = client.get("/sources", params={"theme": "nao_existe"})
        assert response.status_code == 400

    def test_source_schema_exposes_themes(self, client) -> None:
        response = client.get("/sources/sia/schema")
        assert response.status_code == 200
        assert "oncologia" in response.json()["themes"]

    def test_presets_endpoint(self, client) -> None:
        response = client.get("/presets")
        assert response.status_code == 200
        assert {item["name"] for item in response.json()} >= {"oncologia", "nascimentos"}

    def test_preset_detail_endpoint(self, client) -> None:
        response = client.get("/presets/oncologia")
        assert response.status_code == 200
        payload = response.json()
        steps = {step["source"]: step for step in payload["steps"]}
        assert steps["sia"]["params"]["groups"] == ["AQ", "AR"]
        assert steps["sim"]["refine"]
        assert payload["caveats"]

    def test_unknown_preset_returns_404(self, client) -> None:
        assert client.get("/presets/cardiologia").status_code == 404
