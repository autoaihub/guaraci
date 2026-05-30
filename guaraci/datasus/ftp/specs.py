"""Declarative specs for the remaining DATASUS FTP microdata systems.

Phase 5 of ``docs/PLANO_DATASUS_FTP_DIRETO.md``. SIH/SIM/SINAN earned
bespoke parsers in phases 1-3 because they came first; the systems added
here (SINASC, SIA, CNES, PNI, CIHA/CIH, SISCAN, SISPRENATAL, RESP, PCE,
painel de oncologia) are all variations on the same three shapes:

- ``<PREFIX><UF><YYYY>`` — state, yearly, no groups   (SINASC, RESP, PCE…)
- ``<GROUP><UF><YYMM>`` — state, monthly, groups       (SIA, CNES, SISCAN…)
- ``<PREFIX>BR<YYYY>``  — national, yearly             (painel de oncologia)

Rather than copy a parser/discovery/backend per system, each one is a
:class:`SystemSpec`: a compiled regex with named groups plus its FTP
paths and dimension flags. The generic engine
(:func:`guaraci.datasus.ftp.discovery.discover_spec`,
:mod:`guaraci.datasus.ftp.generic_backend`) consumes the spec.

All paths and filename patterns were confirmed by live FTP recon on
2026-05-28; group sets (SIA, CNES, PNI) were enumerated from the server,
not guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Pattern, Tuple

from guaraci.datasus.ftp.catalog import FileRecord, System, _yy_to_year

_PUB = "/dissemin/publicos"


@dataclass(frozen=True)
class SystemSpec:
    """Everything the generic FTP engine needs to handle one DATASUS system.

    ``roots`` lists flat directories whose files carry the group in the
    filename (or have a single implicit group). ``group_dirs`` instead maps
    a group code to its own directory (CNES, SISCAN) — only the requested
    groups' directories are then listed. Exactly one of the two is set.
    """

    name: str  # registry source name, e.g. "sinasc"
    system: System
    title: str
    description: str
    pattern: Pattern[str]
    ext: str  # ".dbc" or ".dbf"
    has_state: bool
    has_month: bool
    min_year: int
    national: bool = False
    fixed_group: str = ""  # group label when the regex has no <group>
    groups: Tuple[str, ...] = ()  # selectable groups; () => single implicit group
    default_groups: Tuple[str, ...] = ()
    roots: Tuple[str, ...] = ()
    group_dirs: Tuple[Tuple[str, str], ...] = ()

    def parse(self, basename: str) -> Optional[FileRecord]:
        """Parse a basename into a :class:`FileRecord`, or ``None``."""
        m = self.pattern.match(basename)
        if not m:
            return None
        gd = m.groupdict()
        if gd.get("year"):
            year = int(gd["year"])
        else:
            year = _yy_to_year(int(gd["yy"]))
        group = (gd.get("group") or self.fixed_group or self.system.value).upper()
        state = None if self.national else (gd.get("state") or None)
        month = int(gd["mm"]) if gd.get("mm") else None
        return FileRecord(
            basename=basename,
            system=self.system,
            group=group,
            state=state.upper() if state else None,
            year=year,
            month=month,
        )


# --- SIM-like: <PREFIX><UF><YYYY|YY>, state, yearly, single group -------------

SINASC = SystemSpec(
    name="sinasc",
    system=System.SINASC,
    title="SINASC",
    description="Sistema de Informações sobre Nascidos Vivos (declarações por residência).",
    roots=(f"{_PUB}/SINASC/NOV/DNRES",),
    pattern=re.compile(r"^DN(?P<state>[A-Z]{2})(?P<year>\d{4})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=True,
    has_month=False,
    fixed_group="DNRES",
    min_year=1996,
)

RESP = SystemSpec(
    name="resp",
    system=System.RESP,
    title="RESP (Microcefalia/arboviroses na gestação)",
    description="Registro de Eventos em Saúde Pública.",
    roots=(f"{_PUB}/RESP/DADOS",),
    pattern=re.compile(r"^RESP(?P<state>[A-Z]{2})(?P<yy>\d{2})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=True,
    has_month=False,
    fixed_group="RESP",
    min_year=2015,
)

PCE = SystemSpec(
    name="pce",
    system=System.PCE,
    title="PCE (Esquistossomose)",
    description="Programa de Controle da Esquistossomose.",
    roots=(f"{_PUB}/PCE/Dados",),
    pattern=re.compile(r"^PCE(?P<state>[A-Z]{2})(?P<yy>\d{2})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=True,
    has_month=False,
    fixed_group="PCE",
    min_year=1995,
)

PNI = SystemSpec(
    name="pni",
    system=System.PNI,
    title="PNI (Imunizações — histórico)",
    description="Programa Nacional de Imunizações (SI-PNI legado; arquivos .DBF).",
    roots=(f"{_PUB}/PNI/DADOS",),
    # Two file families confirmed on the server: CPNI (cobertura) + DPNI (doses).
    pattern=re.compile(r"^(?P<group>CPNI|DPNI)(?P<state>[A-Z]{2})(?P<yy>\d{2})\.dbf$", re.IGNORECASE),
    ext=".dbf",
    has_state=True,
    has_month=False,
    groups=("CPNI", "DPNI"),
    default_groups=("CPNI", "DPNI"),
    min_year=1994,
)


# --- SIH-like: <GROUP><UF><YYMM>, state, monthly, groups ----------------------

_SIA_GROUPS = (
    "PA", "BI", "AB", "ABO", "ACF", "AD", "AM", "AMP",
    "AN", "AQ", "AR", "ATD", "PS", "SAD",
)

SIA = SystemSpec(
    name="sia",
    system=System.SIA,
    title="SIA-SUS (Ambulatorial)",
    description="Sistema de Informações Ambulatoriais (produção ambulatorial).",
    roots=(
        f"{_PUB}/SIASUS/199407_200712/Dados",
        f"{_PUB}/SIASUS/200801_/Dados",
    ),
    # Variable-length group prefixes: longer alternatives first so e.g. ABO
    # is not shadowed by AB, and AMP not by AM.
    pattern=re.compile(
        r"^(?P<group>ABO|ACF|AMP|ATD|SAD|AB|AD|AM|AN|AQ|AR|BI|PA|PS)"
        r"(?P<state>[A-Z]{2})(?P<yy>\d{2})(?P<mm>\d{2})\.dbc$",
        re.IGNORECASE,
    ),
    ext=".dbc",
    has_state=True,
    has_month=True,
    groups=_SIA_GROUPS,
    default_groups=("PA",),
    min_year=1994,
)

_CNES_GROUPS = (
    "DC", "EE", "EF", "EP", "EQ", "GM", "HB",
    "IN", "LT", "PF", "RC", "SR", "ST",
)

CNES = SystemSpec(
    name="cnes",
    system=System.CNES,
    title="CNES (Estabelecimentos)",
    description="Cadastro Nacional de Estabelecimentos de Saúde.",
    group_dirs=tuple((g, f"{_PUB}/CNES/200508_/Dados/{g}") for g in _CNES_GROUPS),
    pattern=re.compile(
        r"^(?P<group>[A-Z]{2})(?P<state>[A-Z]{2})(?P<yy>\d{2})(?P<mm>\d{2})\.dbc$",
        re.IGNORECASE,
    ),
    ext=".dbc",
    has_state=True,
    has_month=True,
    groups=_CNES_GROUPS,
    default_groups=("ST",),
    min_year=2005,
)

SISCAN = SystemSpec(
    name="siscan",
    system=System.SISCAN,
    title="SISCAN (Câncer)",
    description="Sistema de Informação do Câncer (colo do útero / mama).",
    group_dirs=(
        ("CC", f"{_PUB}/SISCAN/SISCOLO4/Dados"),
        ("CM", f"{_PUB}/SISCAN/SISMAMA/Dados"),
    ),
    pattern=re.compile(
        r"^(?P<group>CC|CM)(?P<state>[A-Z]{2})(?P<yy>\d{2})(?P<mm>\d{2})\.dbc$",
        re.IGNORECASE,
    ),
    ext=".dbc",
    has_state=True,
    has_month=True,
    groups=("CC", "CM"),
    default_groups=("CC", "CM"),
    min_year=2006,
)

SISPRENATAL = SystemSpec(
    name="sisprenatal",
    system=System.SISPRENATAL,
    title="SISPRENATAL",
    description="Sistema de Acompanhamento do Pré-Natal.",
    roots=(f"{_PUB}/SISPRENATAL/201201_/Dados",),
    pattern=re.compile(r"^PN(?P<state>[A-Z]{2})(?P<yy>\d{2})(?P<mm>\d{2})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=True,
    has_month=True,
    fixed_group="PN",
    min_year=2012,
)

CIHA = SystemSpec(
    name="ciha",
    system=System.CIHA,
    title="CIHA",
    description="Comunicação de Internação Hospitalar e Ambulatorial (2011+).",
    roots=(f"{_PUB}/CIHA/201101_/Dados",),
    pattern=re.compile(r"^CIHA(?P<state>[A-Z]{2})(?P<yy>\d{2})(?P<mm>\d{2})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=True,
    has_month=True,
    fixed_group="CIHA",
    min_year=2011,
)

CIH = SystemSpec(
    name="cih",
    system=System.CIH,
    title="CIH (legado 2008–2010)",
    description="Comunicação de Internação Hospitalar (substituído pelo CIHA).",
    roots=(f"{_PUB}/CIH/200801_201012/Dados",),
    pattern=re.compile(r"^CR(?P<state>[A-Z]{2})(?P<yy>\d{2})(?P<mm>\d{2})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=True,
    has_month=True,
    fixed_group="CR",
    min_year=2008,
)


# --- SINAN-like: <PREFIX>BR<YYYY>, national, yearly --------------------------

PAINEL_ONCOLOGIA = SystemSpec(
    name="painel_oncologia",
    system=System.PAINEL_ONCOLOGIA,
    title="Painel de Oncologia",
    description="Painel de Oncologia (consolidado nacional anual).",
    roots=(f"{_PUB}/painel_oncologia/Dados",),
    pattern=re.compile(r"^POBR(?P<year>\d{4})\.dbc$", re.IGNORECASE),
    ext=".dbc",
    has_state=False,
    has_month=False,
    national=True,
    fixed_group="PO",
    min_year=2013,
)


ALL_SPECS: Tuple[SystemSpec, ...] = (
    SINASC,
    SIA,
    CNES,
    PNI,
    CIHA,
    CIH,
    SISCAN,
    SISPRENATAL,
    RESP,
    PCE,
    PAINEL_ONCOLOGIA,
)

SPECS = {spec.name: spec for spec in ALL_SPECS}


def get_spec(name: str) -> SystemSpec:
    """Return the spec for a registry source name (case-insensitive)."""
    try:
        return SPECS[name.strip().lower()]
    except KeyError as exc:
        raise KeyError(
            f"Unknown FTP system {name!r}. Known: {', '.join(sorted(SPECS))}"
        ) from exc
