"""Último ano publicado das fontes que publicam com atraso.

O formulário abre, por padrão, no ano passado. Para as fontes abaixo esse ano
ainda não existe na origem, e o job terminava "concluído" sem dado. O valor
aqui só troca o padrão de ``start_year``/``end_year``; o teto continua sendo o
ano corrente, para o ano novo ser pedido assim que sair.

Conferido ao vivo em 2026-09-24 (sonda ano a ano, do padrão para trás). Ao
revisar, rode a camada ``jobs`` de ``scripts/verificar_rotas.py``: fonte que
volta com "0 exportados" no ano padrão é candidata a entrar ou sair daqui.
As FTP genéricas guardam o mesmo dado no próprio spec (``default_year``).
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Sequence

from guaraci.core.contracts import SourceParameterSpec

LATEST_PUBLISHED_YEAR: Dict[str, int] = {
    "sim": 2024,
    "sindrome_gripal_leve": 2024,  # endpoints anuais do DEMAS vão de 2020 a 2024
    "ibge_casamentos": 2024,
    "ibge_divorcios": 2024,
    "ibge_nascidos_vivos_rc": 2024,
    "ibge_obitos_rc": 2024,
    "ibge_pib_municipios": 2023,
}


def apply_latest_published_year(
    source: str, specs: Sequence[SourceParameterSpec]
) -> List[SourceParameterSpec]:
    year = LATEST_PUBLISHED_YEAR.get(source)
    if year is None:
        return list(specs)
    return [
        dataclasses.replace(spec, default=min(int(spec.default), year))
        if spec.name in ("start_year", "end_year") and isinstance(spec.default, int)
        else spec
        for spec in specs
    ]
