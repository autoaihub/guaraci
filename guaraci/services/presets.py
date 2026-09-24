"""Presets: recortes temáticos que atravessam várias fontes de uma vez.

Um *tema* (:mod:`guaraci.services.themes`) responde "onde tem dado de câncer?".
Um *preset* responde a pergunta seguinte, que é a que realmente trava o
usuário: "com quais parâmetros eu puxo esse dado?".

A diferença importa porque no Guaraci o assunto quase nunca coincide com a
fronteira da fonte. Oncologia não é uma fonte: é o grupo ``AQ`` e o ``AR``
dentro do SIA, os grupos ``CC`` e ``CM`` dentro do SISCAN, o SIH e o SIM
inteiros com um recorte de CID aplicado depois. Sem preset, essa receita vive
na cabeça de quem já conhece o DATASUS, e é justamente essa a barreira que
mantém o dado público inacessível na prática.

Honestidade sobre o alcance
---------------------------
Um preset declara o que dá para declarar. Parte do recorte oncológico acontece
na **coleta** (escolher grupos do SIA e do SISCAN), e essa parte o preset
resolve sozinha. Outra parte só acontece **depois** da coleta, filtrando por
código CID nas colunas de diagnóstico, porque o FTP do DATASUS não oferece
filtro de CID na origem: o arquivo mensal vem inteiro. Cada passo diz
explicitamente em qual dos dois casos está, no campo ``refine``. Um preset que
escondesse essa distinção entregaria ao usuário um recorte que ele acha que
está pronto e não está.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

__all__ = [
    "PresetStep",
    "Preset",
    "PRESETS",
    "preset_names",
    "get_preset",
    "presets_for_theme",
]


@dataclass(frozen=True)
class PresetStep:
    """Uma fonte dentro de um preset, com os parâmetros que o preset fixa."""

    source: str
    rationale: str
    params: Mapping[str, object] = field(default_factory=dict)
    refine: Optional[str] = None
    """Filtro que o preset NÃO consegue aplicar na coleta, quando houver.

    ``None`` significa que os ``params`` já entregam o recorte completo. Texto
    preenchido significa que o download traz a base inteira e o recorte final
    depende de um filtro posterior, descrito aqui.
    """

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "rationale": self.rationale,
            "params": dict(self.params),
            "refine": self.refine,
        }


@dataclass(frozen=True)
class Preset:
    """Receita nomeada que reúne fontes e parâmetros de um mesmo assunto."""

    name: str
    title: str
    description: str
    themes: Tuple[str, ...]
    steps: Tuple[PresetStep, ...]
    caveats: Tuple[str, ...] = ()

    @property
    def sources(self) -> Tuple[str, ...]:
        return tuple(step.source for step in self.steps)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "themes": list(self.themes),
            "steps": [step.to_dict() for step in self.steps],
            "caveats": list(self.caveats),
        }


# --- Oncologia --------------------------------------------------------------
#
# Cobre o percurso do paciente oncológico pelos sistemas do SUS, na ordem em
# que ele acontece: rastreamento, tratamento ambulatorial, internação e óbito.
# Faltam dados de INCIDÊNCIA: no Brasil quem produz incidência são os RCBPs do
# INCA, publicados apenas em relatório e tabulador, sem via automatizável. A
# ausência está declarada em ``caveats`` em vez de ficar implícita.

_ONCOLOGIA = Preset(
    name="oncologia",
    title="Oncologia (rastreamento, tratamento, internação e óbito)",
    description=(
        "Recorte de câncer atravessando os sistemas do SUS que registram o "
        "percurso do paciente oncológico. Não inclui incidência."
    ),
    themes=("oncologia",),
    steps=(
        PresetStep(
            source="siscan",
            rationale=(
                "Rastreamento de câncer de colo do útero (CC) e de mama (CM): "
                "exames citopatológicos, histopatológicos e mamografias."
            ),
            params={"groups": ["CC", "CM"]},
        ),
        PresetStep(
            source="sia",
            rationale=(
                "APAC de quimioterapia (AQ) e de radioterapia (AR): o registro "
                "do tratamento oncológico ambulatorial de alta complexidade. "
                "São justamente os grupos que o padrão do SIA (PA) não traz."
            ),
            params={"groups": ["AQ", "AR"]},
        ),
        PresetStep(
            source="painel_oncologia",
            rationale=(
                "Consolidado nacional anual de diagnóstico e primeiro "
                "tratamento, já organizado pelo Ministério da Saúde."
            ),
            params={},
        ),
        PresetStep(
            source="sih",
            rationale=(
                "Internações hospitalares, para chegar à morbidade oncológica "
                "internada e ao custo da internação."
            ),
            params={},
            refine=(
                "O SIH vem completo. Filtre o diagnóstico principal "
                "(DIAG_PRINC) por CID-10 C00-C97 para neoplasias malignas, ou "
                "C00-D48 para o capítulo II inteiro."
            ),
        ),
        PresetStep(
            source="sim",
            rationale="Mortalidade por neoplasia, o desfecho da série.",
            params={},
            refine=(
                "O SIM vem completo. Filtre a causa básica (CAUSABAS) por "
                "CID-10 C00-C97 para mortalidade por neoplasia maligna."
            ),
        ),
    ),
    caveats=(
        "Não há dado de INCIDÊNCIA neste preset. Incidência de câncer no Brasil "
        "vem dos Registros de Câncer de Base Populacional (RCBP) do INCA, "
        "publicados só em relatório e tabulador, sem via automatizável que "
        "atenda ao critério de fonte primária do projeto.",
        "SISCAN cobre rastreamento a partir de 2006; o Painel de Oncologia, a "
        "partir de 2013. Séries que começam antes disso ficam desbalanceadas "
        "entre as fontes.",
        "O Painel de Oncologia é consolidado nacional anual, sem recorte por "
        "UF na coleta, diferente das demais fontes do preset.",
    ),
)


# --- Nascimentos ------------------------------------------------------------
#
# Segundo preset menos por necessidade e mais por prova: mostra que o mecanismo
# generaliza e que o cruzamento DATASUS x IBGE, duas contagens independentes do
# mesmo evento, cabe numa receita só.

_NASCIMENTOS = Preset(
    name="nascimentos",
    title="Nascimentos (SINASC, registro civil e pré-natal)",
    description=(
        "Nascidos vivos por duas contagens independentes, a do SUS e a do "
        "registro civil, mais o pré-natal que antecede o parto."
    ),
    themes=("natalidade", "materno_infantil"),
    steps=(
        PresetStep(
            source="sinasc",
            rationale=(
                "Declaração de Nascido Vivo: a contagem do SUS, com peso ao "
                "nascer, Apgar, idade gestacional e características da mãe."
            ),
            params={},
        ),
        PresetStep(
            source="ibge_nascidos_vivos_rc",
            rationale=(
                "Nascidos vivos pelo registro civil (IBGE, tabela 2680). "
                "Contagem independente do SINASC: a divergência entre as duas "
                "é ela própria um indicador de cobertura."
            ),
            params={},
        ),
        PresetStep(
            source="sisprenatal",
            rationale="Acompanhamento pré-natal, o cuidado que antecede o parto.",
            params={},
        ),
        PresetStep(
            source="ibge_populacao",
            rationale=(
                "Denominador populacional, sem o qual as contagens acima não "
                "viram taxa."
            ),
            params={},
        ),
    ),
    caveats=(
        "SINASC e registro civil contam o mesmo evento por vias distintas e "
        "não devem ser somados. Use um como numerador e o outro como "
        "verificação de cobertura.",
        "O SISPRENATAL cobre a partir de 2012.",
    ),
)


_PRESET_LIST: Tuple[Preset, ...] = (_ONCOLOGIA, _NASCIMENTOS)

PRESETS: Mapping[str, Preset] = {preset.name: preset for preset in _PRESET_LIST}


def preset_names() -> Tuple[str, ...]:
    """Nomes dos presets, na ordem de declaração."""
    return tuple(PRESETS)


def get_preset(name: str) -> Preset:
    """Devolve o preset ``name``, ou levanta ``ValueError`` com a lista válida."""
    key = name.strip().lower()
    preset = PRESETS.get(key)
    if preset is None:
        known = ", ".join(PRESETS) or "(nenhum)"
        raise ValueError(f"Unknown preset '{name}'. Known: {known}")
    return preset


def presets_for_theme(theme: str) -> List[Preset]:
    """Presets que declaram ``theme``, preservando a ordem de declaração."""
    slug = theme.strip().lower()
    return [preset for preset in _PRESET_LIST if slug in preset.themes]
