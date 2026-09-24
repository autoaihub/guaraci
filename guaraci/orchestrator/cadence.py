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

import os
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
_INMET_MIN_YEAR = 2000
# Piso do backfill mensal do QUALAR autenticado. Cada mês do recorte custa por
# volta de 240 requisições; de 2022 em diante o backfill inteiro fica em uma
# noite. O QUALAR tem série bem mais antiga: basta baixar este piso.
_QUALAR_HORARIO_MIN_YEAR = 2022

# Bancos históricos que a origem não atualiza mais: (primeiro, último) ano.
_FROZEN_YEAR_RANGES: Dict[str, tuple] = {
    "srag_arquivos_2009_2012": (2009, 2012),
    "srag_arquivos_2013_2018": (2013, 2018),
    "enani_2019": (2019, 2019),
}

# Edit here to re-tune how often a source is re-checked for new data.
# SISAGUA bulk-file sources publish (at most) monthly/semestral batches on
# the portal; the "opendatasus" mode default (WEEKLY) is tuned for the
# DEMAS/CKAN record APIs and would poll SISAGUA far more often than it ever
# changes. SRAG keeps the WEEKLY default (the "banco vivo" current year is
# republished weekly).
CADENCE_OVERRIDES: Dict[str, Cadence] = {
    "sisagua_controle_mensal_parametros_basicos": Cadence.MONTHLY,
    "sisagua_controle_semestral": Cadence.MONTHLY,
    "sisagua_vigilancia_parametros_basicos": Cadence.MONTHLY,
    "sisagua_tratamento_agua": Cadence.MONTHLY,
    "sisagua_populacao_abastecida": Cadence.MONTHLY,
    "sisagua_controle_mensal_demais_parametros": Cadence.MONTHLY,
    "sisagua_controle_mensal_amostras_fora_do_padrao": Cadence.MONTHLY,
    "sisagua_controle_mensal_plano_amostragem": Cadence.MONTHLY,
    "sisagua_controle_mensal_infraestrutura_operacional": Cadence.MONTHLY,
    "sisagua_vigilancia_demais_parametros": Cadence.MONTHLY,
    "sisagua_vigilancia_cianobacterias_e_cianotoxinas": Cadence.MONTHLY,
    "sisagua_pontos_de_captacao": Cadence.MONTHLY,
    "sisagua_cadastro_carro_pipa_procedencia": Cadence.MONTHLY,
    "sisagua_cadastro_carro_pipa_populacao": Cadence.MONTHLY,
}


@dataclass(frozen=True)
class SourceProfile:
    """Resolved orchestration profile for one registered source."""

    source: str
    kind: Kind
    cadence: Cadence
    min_year: Optional[int] = None
    auto: bool = True
    note: str = ""
    # Último ano publicado de um banco congelado. O update para de reconsultar
    # a fonte depois que esse ano está no ledger.
    max_year: Optional[int] = None

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
    elif name.startswith("ana"):
        profile = SourceProfile(
            name,
            Kind.API_POINT,
            Cadence.IRREGULAR,
            None,
            auto=False,
            note="needs station_ids - collect on demand, not swept",
        )
    elif name.startswith("ibge"):
        # Annual IBGE (SIDRA); backfill floor differs per table.
        ibge_floor = {
            "ibge_pib_municipios": 2002,
            "ibge_populacao_idade_sexo": 2022,  # census reference year
            "ibge_nascidos_vivos_rc": 2003,
            "ibge_obitos_rc": 2003,
            "ibge_area_territorial": 2022,  # census reference year, single period
            "ibge_casamentos": 2013,
            "ibge_divorcios": 2014,
            "ibge_saneamento_agua": 2022,  # census reference year, single period
            "ibge_saneamento_esgoto": 2022,  # census reference year, single period
            "ibge_saneamento_lixo": 2022,  # census reference year, single period
        }.get(name, 2001)
        profile = SourceProfile(name, Kind.API_WINDOW, Cadence.ANNUAL, ibge_floor)
    elif name.startswith("inmet"):
        # Annual ZIP per year (all automatic stations); the current year is
        # re-checked by Content-Length since INMET republishes it as more
        # months land (see guaraci/inmet/datasource.py).
        profile = SourceProfile(name, Kind.API_WINDOW, Cadence.ANNUAL, _INMET_MIN_YEAR)
    elif name.startswith("inpe"):
        # INPE Queimadas: annual files (2003+), re-checked monthly since the
        # current year's file is republished as new detections arrive.
        profile = SourceProfile(name, Kind.API_WINDOW, Cadence.MONTHLY, 2003)
    elif name == "cetesb_qualar_horario":
        # Tem histórico e aceita intervalo de datas, então é varrida mês a mês,
        # mas só num recorte fixo (SWEEP_STATIONS x SWEEP_PARAMETERS em
        # guaraci/cetesb/horario.py): o QUALAR responde um par
        # estação/parâmetro por requisição, e a rede inteira seriam 1500
        # chamadas por mês. Sem credencial no ambiente a fonte sai da
        # varredura com o motivo, em vez de gerar uma linha de erro por mês.
        has_credential = bool(
            os.getenv("GUARACI_QUALAR_LOGIN") and os.getenv("GUARACI_QUALAR_SENHA")
        )
        profile = SourceProfile(
            name,
            Kind.API_MONTHLY,
            Cadence.MONTHLY,
            _QUALAR_HORARIO_MIN_YEAR,
            auto=has_credential,
            note=(
                ""
                if has_credential
                else "needs GUARACI_QUALAR_LOGIN/GUARACI_QUALAR_SENHA in the "
                "environment - skipped until the credential is set"
            ),
        )
    elif name == "cetesb_qualar":
        # Janela MÓVEL de 48 horas, sem histórico: o que não for guardado se
        # perde. A varredura diária grava um instantâneo datado; como a janela
        # é o dobro do intervalo, um dia de falha do servidor não abre buraco.
        # A sobreposição entre instantâneos consecutivos é esperada no bronze
        # e se resolve na camada prata, deduplicando por estação/poluente/hora.
        profile = SourceProfile(name, Kind.SNAPSHOT, Cadence.DAILY, None)
    elif name.startswith("cetesb"):
        # Cadastro das estações (com o índice corrente de cada uma). Muda
        # pouco; um instantâneo por mês mantém o histórico de estações ativas
        # para a junção com a série de concentração.
        profile = SourceProfile(name, Kind.SNAPSHOT, Cadence.MONTHLY, None)
    elif name in _cumulative_portal_sources():
        # Arquivo único republicado com o estado atual: um instantâneo por mês
        # guarda a evolução, e pedir por ano baixaria o mesmo arquivo N vezes.
        profile = SourceProfile(name, Kind.SNAPSHOT, Cadence.MONTHLY, None)
    elif name in _FROZEN_YEAR_RANGES:
        first, last = _FROZEN_YEAR_RANGES[name]
        profile = SourceProfile(
            name, Kind.API_WINDOW, Cadence.ANNUAL, first, max_year=last
        )
    elif "anvisa" in mode_l:
        # A ANVISA sobrescreve cada arquivo a cada atualização, sem versão:
        # o histórico só existe guardando cópias. Mensal equilibra o custo
        # (VigiMed soma cerca de 575 MB por cópia) com a resolução temporal.
        profile = SourceProfile(name, Kind.SNAPSHOT, Cadence.MONTHLY, None)
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


def _cumulative_portal_sources() -> frozenset:
    from guaraci.services.sources.opendatasus_files import CUMULATIVE_SOURCES

    return CUMULATIVE_SOURCES


def sweep_params(source: str) -> Dict[str, object]:
    """Parâmetros fixos que a varredura passa a uma fonte, além das datas.

    Só existe para fontes cujo recorte não sai do schema: hoje, o QUALAR
    autenticado, que exige lista explícita de estações.
    """
    if source == "cetesb_qualar_horario":
        from guaraci.cetesb.horario import SWEEP_PARAMETERS, SWEEP_STATIONS

        return {
            "stations": list(SWEEP_STATIONS),
            "parameters": list(SWEEP_PARAMETERS),
            # Bronze guarda o dado como publicado. A coluna ``validado`` diz
            # o que já passou pela validação da CETESB; filtrar aqui apagaria
            # o mês corrente inteiro.
            "only_validated": False,
        }
    return {}
