"""Vocabulário controlado de temas e o mapa fonte -> temas.

O Guaraci registra mais de cem fontes. Saber QUE a plataforma tem um dado não
é o mesmo que saber ONDE ele está: quem procura "dados de câncer" não adivinha
que a resposta mora nos grupos ``AQ``/``AR`` do SIA, nos grupos ``CC``/``CM``
do SISCAN e num recorte de CID no SIM. Este módulo é a camada que responde
essa pergunta.

Duas decisões de projeto sustentam o arquivo:

1. **Mapa central, não campo espalhado.** Os temas NÃO são declarados em cada
   ``SourceDescriptor`` construído em ``guaraci/services/sources/*.py``. Ficam
   todos aqui, num único lugar auditável, e são acoplados ao descriptor na
   leitura (``DownloadService.list_sources``). Assim a pergunta "quais fontes
   têm dado de oncologia?" se responde lendo um dicionário, e não varrendo dez
   módulos.
2. **Regras por prefixo para as famílias geradas.** As fontes OpenDataSUS são
   geradas a partir do Swagger DEMAS e crescem sozinhas. Mapeá-las uma a uma
   criaria um arquivo que nasce desatualizado, então famílias inteiras
   (``sisagua_*``, ``saude_indigena_*``, ``atencao_primaria_*``) caem em
   regras de prefixo. O mapa explícito tem precedência sobre o prefixo.

Um tema é uma etiqueta grossa, boa para navegar. Um recorte fino, com os
parâmetros certos por fonte, é um *preset*: ver :mod:`guaraci.services.presets`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

__all__ = [
    "Theme",
    "THEMES",
    "theme_slugs",
    "themes_for",
    "sources_by_theme",
    "unknown_theme_slugs",
]


@dataclass(frozen=True)
class Theme:
    """Um eixo temático pelo qual o catálogo de fontes pode ser navegado."""

    slug: str
    label: str
    description: str

    def to_dict(self) -> Dict[str, str]:
        return {"slug": self.slug, "label": self.label, "description": self.description}


# Ordem = ordem de exibição na UI e no CLI. Mantida por afinidade temática
# (assistência, depois eventos vitais, depois determinantes, depois gestão),
# não alfabética, porque a lista é lida por humano procurando um assunto.
_THEME_LIST: Tuple[Theme, ...] = (
    Theme(
        "oncologia",
        "Oncologia",
        "Rastreamento, diagnóstico, tratamento e mortalidade por câncer.",
    ),
    Theme(
        "materno_infantil",
        "Materno-infantil",
        "Gestação, pré-natal, parto e saúde da criança.",
    ),
    Theme(
        "natalidade",
        "Natalidade e registro civil",
        "Nascidos vivos e demais eventos de registro civil.",
    ),
    Theme(
        "mortalidade",
        "Mortalidade",
        "Óbitos por causa, local e características do falecido.",
    ),
    Theme(
        "vigilancia_epidemiologica",
        "Vigilância epidemiológica",
        "Notificação compulsória, arboviroses, síndromes respiratórias e surtos.",
    ),
    Theme(
        "imunizacao",
        "Imunização",
        "Doses aplicadas, insumos de vacinação e eventos adversos pós-vacinação.",
    ),
    Theme(
        "assistencia_hospitalar",
        "Assistência hospitalar",
        "Internações, leitos e produção hospitalar.",
    ),
    Theme(
        "assistencia_ambulatorial",
        "Assistência ambulatorial",
        "Produção ambulatorial, APAC e procedimentos de média e alta complexidade.",
    ),
    Theme(
        "atencao_primaria",
        "Atenção primária",
        "Atenção básica, Previne Brasil e provimento de profissionais.",
    ),
    Theme(
        "estabelecimentos",
        "Estabelecimentos e infraestrutura",
        "Cadastro de serviços de saúde, tipos de unidade e regionalização.",
    ),
    Theme(
        "forca_trabalho",
        "Força de trabalho",
        "Profissionais de saúde, vínculos e formação.",
    ),
    Theme(
        "medicamentos",
        "Medicamentos e insumos",
        "Estoque, distribuição e assistência farmacêutica.",
    ),
    Theme(
        "nutricao",
        "Alimentação e nutrição",
        "Estado nutricional e vigilância alimentar.",
    ),
    Theme(
        "saude_indigena",
        "Saúde indígena",
        "Subsistema de atenção à saúde indígena (SESAI/SIASI).",
    ),
    Theme(
        "saneamento",
        "Saneamento e água",
        "Abastecimento, esgotamento, resíduos e qualidade da água para consumo.",
    ),
    Theme(
        "ambiente_clima",
        "Ambiente e clima",
        "Meteorologia, hidrologia, queimadas e séries ambientais.",
    ),
    Theme(
        "qualidade_ar",
        "Qualidade do ar",
        "Concentração de poluentes atmosféricos em estações de monitoramento.",
    ),
    Theme(
        "socioeconomico",
        "Demografia e socioeconômico",
        "População, território, renda e denominadores para cálculo de taxas.",
    ),
    Theme(
        "economia_saude",
        "Economia da saúde",
        "Orçamento, custos e preços no setor saúde.",
    ),
    Theme(
        "gestao",
        "Gestão, ciência e tecnologia",
        "Ouvidoria, avaliação de tecnologias, pesquisa e demais temas de gestão.",
    ),
)

THEMES: Mapping[str, Theme] = {theme.slug: theme for theme in _THEME_LIST}


def theme_slugs() -> Tuple[str, ...]:
    """Slugs válidos, na ordem de exibição."""
    return tuple(THEMES)


# --- Mapa explícito ---------------------------------------------------------
#
# Fontes curadas à mão. Uma fonte pode ter vários temas, e isso é proposital:
# o SIM responde tanto a "mortalidade" quanto a "oncologia", porque é por ele
# que se chega à mortalidade por neoplasia. Uma fonte aparecer sob um tema
# significa "aqui tem dado desse assunto", não "esta fonte é só sobre isso".

_EXPLICIT: Mapping[str, Tuple[str, ...]] = {
    # DATASUS FTP
    "sim": ("mortalidade", "oncologia"),
    "sinasc": ("natalidade", "materno_infantil"),
    "sinan": ("vigilancia_epidemiologica",),
    "sih": ("assistencia_hospitalar", "oncologia"),
    "sia": ("assistencia_ambulatorial", "oncologia"),
    "cnes": ("estabelecimentos", "forca_trabalho"),
    "pni": ("imunizacao",),
    "ciha": ("assistencia_hospitalar", "assistencia_ambulatorial"),
    "cih": ("assistencia_hospitalar",),
    "siscan": ("oncologia",),
    "sisprenatal": ("materno_infantil",),
    "resp": ("vigilancia_epidemiologica", "materno_infantil"),
    "pce": ("vigilancia_epidemiologica",),
    "painel_oncologia": ("oncologia", "assistencia_ambulatorial"),
    # OpenDataSUS DEMAS, curadas
    "dengue": ("vigilancia_epidemiologica",),
    "chikungunya": ("vigilancia_epidemiologica",),
    "zikavirus": ("vigilancia_epidemiologica",),
    "febre_amarela": ("vigilancia_epidemiologica",),
    "mpox": ("vigilancia_epidemiologica",),
    "srag_demas": ("vigilancia_epidemiologica",),
    "srag_arquivos": ("vigilancia_epidemiologica",),
    "srag_arquivos_2009_2012": ("vigilancia_epidemiologica",),
    "srag_arquivos_2013_2018": ("vigilancia_epidemiologica",),
    "sesai_tuberculose": ("saude_indigena", "vigilancia_epidemiologica"),
    "enani_2019": ("nutricao",),
    "sindrome_gripal_leve": ("vigilancia_epidemiologica",),
    "esavi": ("imunizacao", "vigilancia_epidemiologica"),
    "doses_aplicadas_pni": ("imunizacao",),
    "sisvan_estado_nutricional": ("nutricao",),
    "macrorregiao_e_regiao_de_saude_municipio": ("estabelecimentos",),
    "daf_estoque_medicamentos_bnafar_horus": ("medicamentos",),
    "outros_temas_ced": ("gestao",),
    "educacao_em_saude_pvc": ("forca_trabalho", "gestao"),
    "prevencao_e_promocao_distribuicao_epi_insumo": ("medicamentos",),
    "vacinacao_sistema_de_informacao_de_insumos_estrategicos": (
        "imunizacao",
        "medicamentos",
    ),
    "vigilancia_e_meio_ambiente_sistema_de_informacao_sobre_mortalidade": (
        "mortalidade",
    ),
    "vigilancia_e_meio_ambiente_sistema_de_informacao_sobre_nascidos_vivos": (
        "natalidade",
        "materno_infantil",
    ),
    # gov.br crawl
    "snis": ("saneamento",),
    "sinisa": ("saneamento",),
    # IBGE
    "ibge_populacao": ("socioeconomico",),
    "ibge_populacao_idade_sexo": ("socioeconomico",),
    "ibge_pib_municipios": ("socioeconomico", "economia_saude"),
    "ibge_area_territorial": ("socioeconomico",),
    "ibge_nascidos_vivos_rc": ("natalidade", "socioeconomico"),
    "ibge_obitos_rc": ("mortalidade", "socioeconomico"),
    "ibge_casamentos": ("socioeconomico",),
    "ibge_divorcios": ("socioeconomico",),
    "ibge_saneamento_agua": ("saneamento", "socioeconomico"),
    "ibge_saneamento_esgoto": ("saneamento", "socioeconomico"),
    "ibge_saneamento_lixo": ("saneamento", "socioeconomico"),
    # Ambiental
    "nasa_power": ("ambiente_clima",),
    "nasa_firms": ("ambiente_clima",),
    "nasa_gpm": ("ambiente_clima",),
    "inmet_estacoes": ("ambiente_clima",),
    "inpe_queimadas": ("ambiente_clima",),
    "ana_hidro": ("ambiente_clima", "saneamento"),
    "cetesb_qualar": ("qualidade_ar", "ambiente_clima"),
    "cetesb_estacoes": ("qualidade_ar", "ambiente_clima"),
    "cetesb_qualar_horario": ("qualidade_ar", "ambiente_clima"),
}


# --- Regras por prefixo -----------------------------------------------------
#
# Avaliadas em ordem; a primeira que casar vence. Prefixos mais específicos
# vêm antes dos mais genéricos (``cnes_tipounidades`` antes de ``cnes_``).

_PREFIX_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("sisagua_", ("saneamento",)),
    ("saude_indigena_", ("saude_indigena",)),
    ("atencao_primaria_", ("atencao_primaria",)),
    ("ciencia_tecnologia_", ("gestao",)),
    ("ouvidoria_", ("gestao",)),
    ("economia_da_saude_", ("economia_saude",)),
    ("assistencia_a_saude_", ("assistencia_hospitalar", "estabelecimentos")),
    ("cnes_", ("estabelecimentos",)),
    ("arboviroses_", ("vigilancia_epidemiologica",)),
)

# Fonte sem tema aparece como "sem classificação" em vez de sumir da navegação.
_FALLBACK: Tuple[str, ...] = ()


def themes_for(source: str) -> Tuple[str, ...]:
    """Temas de ``source``, na ordem declarada.

    O mapa explícito tem precedência sobre as regras de prefixo. Fonte
    desconhecida devolve tupla vazia em vez de levantar exceção: o catálogo
    cresce sozinho pelo Swagger DEMAS e uma fonte nova não pode quebrar a
    listagem só por ainda não ter sido classificada.
    """
    key = source.strip().lower()
    explicit = _EXPLICIT.get(key)
    if explicit is not None:
        return explicit
    for prefix, themes in _PREFIX_RULES:
        if key.startswith(prefix):
            return themes
    return _FALLBACK


def sources_by_theme(theme: str, sources: Iterable[str]) -> List[str]:
    """Nomes de ``sources`` classificados sob ``theme``, preservando a ordem."""
    slug = theme.strip().lower()
    if slug not in THEMES:
        known = ", ".join(THEMES)
        raise ValueError(f"Unknown theme '{theme}'. Known: {known}")
    return [name for name in sources if slug in themes_for(name)]


def unknown_theme_slugs() -> Tuple[str, ...]:
    """Slugs citados nos mapas que não existem em :data:`THEMES`.

    Existe para o teste de integridade: um erro de digitação num slug criaria
    um tema fantasma, invisível na navegação e silencioso em produção.
    """
    cited = {slug for slugs in _EXPLICIT.values() for slug in slugs}
    cited.update(slug for _, slugs in _PREFIX_RULES for slug in slugs)
    return tuple(sorted(cited - set(THEMES)))
