"""Lista padrão (congelada) de séries do IPEADATA que o Guaraci traz.

Política do dono (leva de outubro de 2026): o IPEADATA é sobretudo agregador, de
modo que só entram séries sem par primário acessível. O critério, aplicado ao
catálogo ``Metadados`` de 2026-10-23 (4.075 séries):

* fora ``ADH_*`` e as séries IDHM, que são o Atlas do Desenvolvimento Humano;
* fora toda série cuja fonte primária o Guaraci já tem ou expõe por API: IBGE
  (SIDRA: PNAD Contínua, PIM, PMC, PAM, PPM, PIB, estimativas e projeções de
  população), BCB (SGS, SICOR), DATASUS, Tesouro (as séries municipais da STN
  chegam até 2025 e se sobrepõem ao SICONFI), TSE, MDS e FGV;
* fora as séries inativas (``INATIVA`` no nome) e as macroeconômicas do IPEA
  (câmbio efetivo real e afins), sem relação com saúde ou território;
* dentro as séries próprias do IPEA com recorte municipal ou estadual (Atlas da
  Violência, Atlas da Vulnerabilidade Social, arrecadação municipal, distâncias) e
  as séries históricas longas sem equivalente no SIDRA, que são os censos
  demográficos de 1872 a 2010 por município e por Área Mínima Comparável (AMC).

Cada item é ``(codigo, motivo)``. O catálogo inteiro está em ``ipeadata_metadados``.
"""

from __future__ import annotations

from typing import Tuple

__all__ = ["DEFAULT_SERIES", "DEFAULT_SERIES_CODES"]

_AVIOL = "IPEA: Atlas da Violência (séries próprias do instituto)"
_AVS = "IPEA: Atlas da Vulnerabilidade Social, sem par primário"
_CENSO = "IBGE: censos demográficos antigos por município e AMC, anteriores ao SIDRA do Censo 2022"
_IPEA = "IPEA: série própria do instituto"

DEFAULT_SERIES: Tuple[Tuple[str, str], ...] = (
    ("AVIOL12_TACIDT", _AVIOL),
    ("AVIOL12_THOMIC", _AVIOL),
    ("AVIOL12_TSUICID", _AVIOL),
    ("AVIOL12_VIOLPOP", _AVIOL),
    ("AVS_IVS", _AVS),
    ("AVS_IVSCH", _AVS),
    ("AVS_IVSIU", _AVS),
    ("AVS_IVSRT", _AVS),
    ("IPTUCH", _IPEA + " (arrecadação do IPTU por município, 2003-2019)"),
    ("ISSCH", _IPEA + " (arrecadação do ISS por município, 2003-2019)"),
    ("ITBICH", _IPEA + " (arrecadação do ITBI por município, 2003-2019)"),
    ("RECPROPCH", _IPEA + " (arrecadação de IPTU, ITBI e ISS por município, 2003-2019)"),
    ("DISTCAPF", _IPEA + " (distância municipal à capital federal)"),
    ("DISTCAPU", _IPEA + " (distância municipal à capital estadual)"),
    ("POPTOT", _CENSO),
    ("POPUR", _CENSO),
    ("POPRU", _CENSO),
    ("POPM", _CENSO),
    ("POPF", _CENSO),
    ("POP0_4M", _CENSO),
    ("POP0_4F", _CENSO),
    ("POP5_9M", _CENSO),
    ("POP5_9F", _CENSO),
    ("POP10_14M", _CENSO),
    ("POP10_14F", _CENSO),
    ("POP15_19M", _CENSO),
    ("POP15_19F", _CENSO),
    ("POP20_24M", _CENSO),
    ("POP20_24F", _CENSO),
    ("POP25_29M", _CENSO),
    ("POP25_29F", _CENSO),
    ("POP30_39M", _CENSO),
    ("POP30_39F", _CENSO),
    ("POP40_49M", _CENSO),
    ("POP40_49F", _CENSO),
    ("POP50_59M", _CENSO),
    ("POP50_59F", _CENSO),
    ("POP60_69M", _CENSO),
    ("POP60_69F", _CENSO),
    ("POP70M_M", _CENSO),
    ("POP70M_F", _CENSO),
)

DEFAULT_SERIES_CODES: Tuple[str, ...] = tuple(code for code, _ in DEFAULT_SERIES)
