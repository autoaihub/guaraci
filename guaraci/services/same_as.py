"""Fontes que são a mesma base de outra fonte, por outro caminho.

O catálogo registra uma fonte por caminho de coleta (API, FTP, arquivo), e
alguns caminhos levam à mesma base: o SRAG pela API do OpenDataSUS e pelos
bancos anuais, a dengue pela API e pelo FTP do SINAN. Essas entradas ficam no
catálogo, porque o caminho alternativo tem uso (filtrar por UF ou data sem
baixar o arquivo inteiro, consultar um registro só), mas não contam como base
distinta. O mapa mora aqui, num lugar só, para que a API, a interface e o site
digam a mesma coisa.

Cada par foi conferido campo a campo no ``field_dictionary.json`` em
2026-10-14. Zika e febre amarela pela API entraram em 2026-10-19, quando o
SINAN pelo FTP passou a trazer os agravos ZIKA e FMAC. Vacinação e SISVAN pela
API têm outro leiaute de colunas que os arquivos, mas são os mesmos registros,
e a API não entrega um ano inteiro (para por volta de 1 milhão de offset).
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Tuple

__all__ = ["SAME_AS", "same_as_for", "distinct_count"]

SAME_AS: Mapping[str, Tuple[str, str]] = {
    "srag_demas": (
        "srag_arquivos",
        "Mesmos registros do SIVEP-Gripe dos bancos anuais, pela API com filtros.",
    ),
    "dengue": (
        "sinan",
        "Notificações de dengue do SINAN pela API; o FTP traz o mesmo agravo (DENG).",
    ),
    "chikungunya": (
        "sinan",
        "Notificações de chikungunya do SINAN pela API; o FTP traz o mesmo agravo (CHIK).",
    ),
    "zikavirus": (
        "sinan",
        "Notificações de zika do SINAN pela API; o FTP traz o mesmo agravo (ZIKA).",
    ),
    "febre_amarela": (
        "sinan",
        "Notificações de febre amarela do SINAN pela API; o FTP traz o mesmo agravo (FMAC).",
    ),
    "doses_aplicadas_pni": (
        "pni_doses_aplicadas_arquivos",
        "Mesmas doses dos arquivos mensais, com outro leiaute; a API não entrega um ano inteiro.",
    ),
    "sisvan_estado_nutricional": (
        "sisvan_estado_nutricional_arquivos",
        "Mesmos acompanhamentos dos arquivos anuais, com outro leiaute; a API não entrega um ano inteiro.",
    ),
    "vigilancia_e_meio_ambiente_sistema_de_informacao_sobre_mortalidade": (
        "sim",
        "Declarações de óbito do SIM pela API.",
    ),
    "vigilancia_e_meio_ambiente_sistema_de_informacao_sobre_nascidos_vivos": (
        "sinasc",
        "Declarações de nascido vivo do SINASC pela API.",
    ),
    "sisagua_tratamento_de_agua": (
        "sisagua_tratamento_agua",
        "Mesmo cadastro de tratamento de água pela API, com outros nomes de coluna.",
    ),
    "cnes_estabelecimentos_por_codigo_cnes": (
        "cnes_estabelecimentos",
        "Consulta de um estabelecimento só, pelo código CNES.",
    ),
    "cnes_tipounidades_por_codigo_tipo_unidade": (
        "cnes_tipounidades",
        "Consulta de um tipo de unidade só, pelo código.",
    ),
}


def same_as_for(source: str) -> Optional[str]:
    """Fonte da qual ``source`` é outro caminho, ou ``None`` se é base própria."""
    entry = SAME_AS.get(source)
    return entry[0] if entry else None


def distinct_count(sources) -> int:
    """Quantas das ``sources`` (chaves) são bases distintas."""
    keys = set(sources)
    return len(keys - set(SAME_AS))


def _check(registered) -> Dict[str, str]:
    """Pares cuja origem ou destino não está registrado, ou que formam cadeia."""
    keys = set(registered)
    bad: Dict[str, str] = {}
    for key, (target, _) in SAME_AS.items():
        if key not in keys or target not in keys:
            bad[key] = target
        elif target in SAME_AS:
            bad[key] = f"{target} (também é outro caminho)"
    return bad
