"""Per-source profile: kind + publication cadence + backfill lower bound.

This is the "config de cadência por fonte" the team asked for. Every registered
source resolves to a :class:`SourceProfile` that tells the orchestrator:

* **kind** — how to discover, run and lay out the source (see :class:`Kind`);
* **cadence** — how often the source publishes, so the updater re-checks on
  that rhythm and pulls whatever is newly available (not one fixed monthly
  sweep for everything);
* **min_year** — the backfill lower bound (``None`` = derive from the schema);
* **auto** — whether the source is swept automatically (NASA needs a lat/lon,
  so it is collected on demand, never in a blind sweep).

Resolution is heuristic (by name, then by transport mode) so it covers all ~88
registered sources without a hand-maintained list. Cadence defaults can be
overridden per source in :data:`CADENCE_OVERRIDES`.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from guaraci.datasus.ftp.specs import SPECS
from guaraci.orchestrator.model import Cadence, Kind

# Backfill lower bounds for the three bespoke DATASUS systems (the spec-driven
# systems carry their own ``min_year``). Discovery only returns files that
# actually exist, so a conservative floor just bounds the year range object.
_SINAN_MIN_YEAR = 2001
_SIM_MIN_YEAR = 1979
_SIH_MIN_YEAR = 1992

# Edit here to re-tune how often a source is re-checked for new data.
CADENCE_OVERRIDES: Dict[str, Cadence] = {}


@dataclass(frozen=True)
class SourceProfile:
    """Resolved orchestration profile for one registered source."""

    source: str
    kind: Kind
    cadence: Cadence
    min_year: Optional[int] = None
    auto: bool = True
    note: str = ""

    def with_cadence(self, cadence: Cadence) -> "SourceProfile":
        return replace(self, cadence=cadence)


def profile_for(source: str, mode: str = "") -> SourceProfile:
    """Resolve a :class:`SourceProfile` from a source name and transport mode.

    ``mode`` is the ``DownloadService`` descriptor mode (e.g. ``"datasus ftp"``,
    ``"opendatasus api"``, ``"gov.br crawl"``); it disambiguates the API and
    crawler families that are not enumerable by name.
    """
    name = source.strip().lower()
    mode_l = (mode or "").strip().lower()

    profile: SourceProfile
    if name == "sinan":
        profile = SourceProfile(name, Kind.FTP_SINAN, Cadence.MONTHLY, _SINAN_MIN_YEAR)
    elif name == "sim":
        profile = SourceProfile(name, Kind.FTP_SIM, Cadence.MONTHLY, _SIM_MIN_YEAR)
    elif name == "sih":
        profile = SourceProfile(name, Kind.FTP_SIH, Cadence.MONTHLY, _SIH_MIN_YEAR)
    elif name in SPECS:
        profile = SourceProfile(
            name, Kind.FTP_GENERIC, Cadence.MONTHLY, SPECS[name].min_year
        )
    elif name.startswith("nasa"):
        profile = SourceProfile(
            name,
            Kind.API_POINT,
            Cadence.IRREGULAR,
            None,
            auto=False,
            note="needs latitude/longitude - collect on demand, not swept",
        )
    elif name.startswith("ibge"):
        # Annual IBGE (SIDRA); backfill floor differs per table.
        ibge_floor = {
            "ibge_pib_municipios": 2002,
            "ibge_populacao_idade_sexo": 2022,  # census reference year
            "ibge_nascidos_vivos_rc": 2003,
            "ibge_obitos_rc": 2003,
            "ibge_area_territorial": 2022,  # census reference year, single period
        }.get(name, 2001)
        profile = SourceProfile(name, Kind.API_WINDOW, Cadence.ANNUAL, ibge_floor)
    elif "opendatasus" in mode_l or "demas" in mode_l:
        # Date-window API sources; min_year is read from the schema by the planner.
        profile = SourceProfile(name, Kind.API_WINDOW, Cadence.WEEKLY, None)
    elif "crawl" in mode_l or name in {"snis", "sinisa"}:
        profile = SourceProfile(name, Kind.CRAWLER, Cadence.ANNUAL, None)
    else:
        profile = SourceProfile(
            name,
            Kind.UNKNOWN,
            Cadence.IRREGULAR,
            None,
            auto=False,
            note=f"unrecognised source shape (mode={mode!r}) — skipped by the sweep",
        )

    override = CADENCE_OVERRIDES.get(name)
    if override is not None:
        profile = profile.with_cadence(override)
    return profile
