"""Gera site/assets/catalog-data.js — catálogo detalhado das fontes do Guaraci.

Fontes de verdade:
- DownloadService: parâmetros (tipo, default, allowed_values, min/max, fase) e modo.
- guaraci/data/field_dictionary.json: campos reais amostrados por fonte.
- guaraci.orchestrator.cadence.profile_for: cadência e piso histórico.
- CURATED (abaixo): nome de exibição, descrição PT, grupo, mantenedor e área
  (conteúdo editorial herdado do antigo site/assets/bases.js).
- reports/discover_stats.json (opcional, gerado por --live): contagem de
  arquivos ao vivo no FTP do DATASUS.

Uso:
    python scripts/build_site_catalog.py            # gera o catálogo
    python scripts/build_site_catalog.py --live     # + discover ao vivo (FTP)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "assets" / "catalog-data.js"
DICT = ROOT / "guaraci" / "data" / "field_dictionary.json"
STATS = ROOT / "reports" / "discover_stats.json"

# ─── Conteúdo editorial (área: saude | pop | clima | san) ───
MS = "Ministério da Saúde"
SVS = "Ministério da Saúde — Secretaria de Vigilância em Saúde"
PNI_M = "Ministério da Saúde — Programa Nacional de Imunizações"
AMB = "Ministério da Saúde — Vigilância em Saúde Ambiental"
SESAI = "Ministério da Saúde — SESAI"
APS = "Ministério da Saúde — Atenção Primária à Saúde"
DGITS = "Ministério da Saúde — DGITS"
DTS = "Ministério da Saúde (DATASUS)"

G_FTP = "DATASUS · sistemas nacionais"
G_VIG = "Emergências e vigilância"
G_ARBO = "Arboviroses · catálogo aberto"
G_VMA = "Vigilância e meio ambiente"
G_VAC = "Vacinação"
G_CNES = "CNES · catálogo aberto"
G_SIS = "Sisagua · qualidade da água"
G_IND = "Saúde indígena · SASISUS/SIASI"
G_AP = "Atenção primária"
G_AS = "Assistência à saúde"
G_ECO = "Economia da saúde"
G_CT = "Ciência e tecnologia · DGITS"
G_PB = "Plataforma Brasil"
G_OUT = "Outras áreas do catálogo aberto"
G_IBGE = "IBGE · população e economia"
G_NASA = "NASA · clima e ambiente"
G_SAN = "Saneamento · gov.br"
G_AMB = "Ambiental · clima, água e território"

# key → (nome exibição, descrição, grupo, mantenedor, área)
CURATED = {
    # DATASUS FTP (microdados)
    "sih": ("SIH", "Internações hospitalares pelo SUS", G_FTP, DTS, "saude"),
    "sim": ("SIM", "Mortalidade — óbitos e causas", G_FTP, DTS, "saude"),
    "sinan": ("SINAN", "Notificação compulsória de agravos", G_FTP, DTS, "saude"),
    "sinasc": ("SINASC", "Nascidos vivos", G_FTP, DTS, "saude"),
    "sia": ("SIA-SUS", "Atendimentos ambulatoriais (14 subgrupos)", G_FTP, DTS, "saude"),
    "cnes": ("CNES", "Cadastro de estabelecimentos de saúde (13 subgrupos)", G_FTP, DTS, "saude"),
    "pni": ("PNI (histórico)", "Imunizações, base legada", G_FTP, DTS, "saude"),
    "ciha": ("CIHA", "Comunicação de internação hospitalar e ambulatorial", G_FTP, DTS, "saude"),
    "cih": ("CIH (legado 2008–2010)", "Internações, versão anterior ao SIH", G_FTP, DTS, "saude"),
    "siscan": ("SISCAN", "Rastreamento de câncer de colo do útero e mama", G_FTP, DTS, "saude"),
    "sisprenatal": ("SISPRENATAL", "Acompanhamento de pré-natal", G_FTP, DTS, "saude"),
    "resp": ("RESP", "Microcefalia e arboviroses na gestação", G_FTP, DTS, "saude"),
    "pce": ("PCE", "Controle da esquistossomose", G_FTP, DTS, "saude"),
    "painel_oncologia": ("Painel de Oncologia", "Produção de tratamentos oncológicos", G_FTP, DTS, "saude"),
    # Emergências e vigilância (vitrine OpenDataSUS)
    "dengue": ("Dengue", "Casos notificados de dengue", G_VIG, SVS, "saude"),
    "chikungunya": ("Chikungunya", "Casos notificados de chikungunya", G_VIG, SVS, "saude"),
    "zikavirus": ("Zika", "Casos notificados de zika vírus", G_VIG, SVS, "saude"),
    "febre_amarela": ("Febre amarela", "Casos notificados de febre amarela", G_VIG, SVS, "saude"),
    "mpox": ("Mpox", "Casos notificados de mpox", G_VIG, SVS, "saude"),
    "sindrome_gripal_leve": ("Síndrome gripal leve", "Notificações de síndrome gripal leve", G_VIG, SVS, "saude"),
    "srag_demas": ("SRAG", "Síndrome respiratória aguda grave", G_VIG, SVS, "saude"),
    "srag_arquivos": ("SRAG — bancos anuais", "Bancos anuais consolidados (2019–2026), arquivo bruto do portal", G_VIG, SVS, "saude"),
    "esavi": ("ESAVI", "Eventos adversos pós-vacinação", G_VIG, SVS, "saude"),
    "doses_aplicadas_pni": ("Doses aplicadas (PNI)", "Painel de vacinação — doses aplicadas", G_VIG, PNI_M, "saude"),
    # Arboviroses · catálogo aberto
    # (pre-Fase-A cleanup: "arboviroses_chikungunya"/"arboviroses_dengue"/
    # "arboviroses_febre_amarela_humanos_primatas_nao_humanos" no longer exist
    # as registered sources — superseded by the manual "chikungunya"/"dengue"/
    # "febre_amarela" entries under "Emergências e vigilância" above; removed
    # here since they were blocking `python scripts/build_site_catalog.py`
    # with an unrelated pre-existing "entradas CURATED sem fonte" error.)
    # Vigilância e meio ambiente
    # ("vigilancia_e_meio_ambiente_mpox" removed for the same reason — see note above.)
    "vigilancia_e_meio_ambiente_sistema_de_informacao_sobre_mortalidade": ("Mortalidade (catálogo aberto)", "Sistema de informação sobre mortalidade via catálogo aberto", G_VMA, SVS, "saude"),
    "vigilancia_e_meio_ambiente_sistema_de_informacao_sobre_nascidos_vivos": ("Nascidos vivos (catálogo aberto)", "Sistema de informação sobre nascidos vivos via catálogo aberto", G_VMA, SVS, "saude"),
    # Vacinação
    # ("vacinacao_esavi" removed for the same reason — see note above.)
    "vacinacao_sistema_de_informacao_de_insumos_estrategicos": ("Insumos estratégicos de vacinação", "Estoque e distribuição de insumos", G_VAC, PNI_M, "saude"),
    # CNES · catálogo aberto
    "cnes_estabelecimentos": ("Estabelecimentos de saúde", "Cadastro nacional via catálogo aberto", G_CNES, "Ministério da Saúde (CNES)", "saude"),
    "cnes_estabelecimentos_{codigo_cnes}": ("Estabelecimentos por código CNES", "Consulta individual por código", G_CNES, "Ministério da Saúde (CNES)", "saude"),
    "cnes_tipounidades": ("Tipos de unidade de saúde", "Tabela de tipos de unidade", G_CNES, "Ministério da Saúde (CNES)", "saude"),
    "cnes_tipounidades_{codigo_tipo_unidade}": ("Tipos de unidade por código", "Consulta individual por código", G_CNES, "Ministério da Saúde (CNES)", "saude"),
    # Sisagua
    "sisagua_vigilancia_parametros_basicos": ("Vigilância — parâmetros básicos", "Qualidade da água para consumo humano", G_SIS, AMB, "saude"),
    "sisagua_controle_semestral": ("Controle semestral", "Monitoramento semestral da água", G_SIS, AMB, "saude"),
    "sisagua_controle_mensal_parametros_basicos": ("Controle mensal — parâmetros básicos", "Monitoramento mensal da água", G_SIS, AMB, "saude"),
    "sisagua_pontos_de_captacao": ("Pontos de captação de água", "Localização dos pontos de captação", G_SIS, AMB, "saude"),
    "sisagua_cadastro_carro_pipa_populacao": ("Carros-pipa — população atendida", "Abastecimento emergencial por carros-pipa", G_SIS, AMB, "saude"),
    "sisagua_cadastro_carro_pipa_procedencia": ("Carros-pipa — procedência da água", "Origem da água distribuída", G_SIS, AMB, "saude"),
    "sisagua_controle_mensal_amostras_fora_do_padrao": ("Controle mensal — amostras fora do padrão", "Amostras em desacordo com o padrão", G_SIS, AMB, "saude"),
    "sisagua_controle_mensal_demais_parametros": ("Controle mensal — demais parâmetros", "Parâmetros complementares mensais", G_SIS, AMB, "saude"),
    "sisagua_controle_mensal_infraestrutura_operacional": ("Controle mensal — infraestrutura operacional", "Infraestrutura dos sistemas de abastecimento", G_SIS, AMB, "saude"),
    "sisagua_controle_mensal_plano_amostragem": ("Controle mensal — plano de amostragem", "Planos de amostragem dos sistemas", G_SIS, AMB, "saude"),
    "sisagua_populacao_abastecida": ("População abastecida", "População atendida por sistema", G_SIS, AMB, "saude"),
    "sisagua_tratamento_de_agua": ("Tratamento de água", "Formas de tratamento aplicadas", G_SIS, AMB, "saude"),
    "sisagua_tratamento_agua": ("Tratamento de água — cadastro", "Cadastro de tratamento de água, arquivo bruto do portal", G_SIS, AMB, "saude"),
    "sisagua_vigilancia_cianobacterias_e_cianotoxinas": ("Vigilância — cianobactérias e cianotoxinas", "Monitoramento de cianobactérias", G_SIS, AMB, "saude"),
    "sisagua_vigilancia_demais_parametros": ("Vigilância — demais parâmetros", "Parâmetros complementares de vigilância", G_SIS, AMB, "saude"),
    # Saúde indígena
    "saude_indigena_sasisus_esgotamento_sanitario": ("Esgotamento sanitário em aldeias", "Saneamento em territórios indígenas", G_IND, SESAI, "saude"),
    "saude_indigena_sasi_sus_gerenciamento_de_residuos_solidos": ("Gerenciamento de resíduos sólidos", "Resíduos sólidos em aldeias", G_IND, SESAI, "saude"),
    "saude_indigena_acompanhamento_obra_infraestrutura_saude": ("Obras de infraestrutura de saúde", "Acompanhamento de obras em territórios indígenas", G_IND, SESAI, "saude"),
    "saude_indigena_planilha_de_fornecimento_e_monitoramento_da_qualidade_da_agua_acesso_a_agua": ("Fornecimento e qualidade da água", "Acesso à água em aldeias", G_IND, SESAI, "saude"),
    "saude_indigena_planilha_registros_habilitacao_recebimento_incentivo": ("Habilitação e recebimento de incentivo", "Registros de habilitação e incentivos", G_IND, SESAI, "saude"),
    "saude_indigena_sistema_de_atencao_a_saude_indigena_modulo_de_vigilancia_alimentar_e_nutricional": ("Vigilância alimentar e nutricional indígena", "Estado nutricional de povos indígenas", G_IND, SESAI, "saude"),
    "saude_indigena_siasi_acompanhamento_gestacional": ("Acompanhamento gestacional (SIASI)", "Gestação em povos indígenas", G_IND, SESAI, "saude"),
    "saude_indigena_siasi_modulo_morbidades": ("Módulo de morbidades (SIASI)", "Morbidades em povos indígenas", G_IND, SESAI, "saude"),
    "saude_indigena_siasi_modulo_saude_bucal_ficha3": ("Saúde bucal — ficha 3", "Atividades coletivas: escovação supervisionada, flúor gel, educação em saúde", G_IND, SESAI, "saude"),
    "saude_indigena_siasi_modulo_saude_bucal_ficha4": ("Saúde bucal — ficha 4", "Ficha odontológica individual: prótese, fluorose, má-formação orofacial", G_IND, SESAI, "saude"),
    "saude_indigena_siasi_modulo_saude_bucal_ficha7": ("Saúde bucal — ficha 7", "Procedimentos clínicos das equipes multidisciplinares (EMSI)", G_IND, SESAI, "saude"),
    "saude_indigena_indicadores_enfrentamento_monitoramento_covid19_indigenas": ("Covid-19 em povos indígenas", "Enfrentamento e monitoramento da Covid-19", G_IND, SESAI, "saude"),
    # Atenção primária
    "atencao_primaria_pmmb": ("PMMB — Programa Médicos pelo Brasil", "Dados gerais do programa", G_AP, APS, "saude"),
    "atencao_primaria_pmmb_profissionais_ativos": ("PMMB — profissionais ativos", "Profissionais em atividade", G_AP, APS, "saude"),
    "atencao_primaria_pmmb_serie_historica": ("PMMB — série histórica", "Evolução histórica do programa", G_AP, APS, "saude"),
    "atencao_primaria_cadastro_vinculado_programa_previne_brasil": ("Cadastro vinculado ao Previne Brasil", "Cadastros do programa Previne Brasil", G_AP, APS, "saude"),
    "atencao_primaria_indicador_desempenho_programa_previne_brasil": ("Indicador de desempenho do Previne Brasil", "Indicadores de desempenho", G_AP, APS, "saude"),
    # Assistência à saúde
    "assistencia_a_saude_hospitais_e_leitos": ("Hospitais e leitos", "Capacidade hospitalar instalada", G_AS, MS, "saude"),
    "assistencia_a_saude_registro_de_ocupacao_hospitalar_covid_19": ("Ocupação hospitalar — Covid-19", "Ocupação de leitos na pandemia", G_AS, MS, "saude"),
    "assistencia_a_saude_unidade_basicas_de_saude": ("Unidades básicas de saúde", "Rede de UBS do país", G_AS, MS, "saude"),
    # Economia da saúde
    "economia_da_saude_bps": ("BPS", "Indicadores de economia da saúde", G_ECO, MS, "saude"),
    "economia_da_saude_sistema_de_apuracao_e_gestao_de_custos_do_sus_apurasus": ("ApuraSUS", "Apuração e gestão de custos do SUS", G_ECO, MS, "saude"),
    # Ciência e tecnologia
    "ciencia_tecnologia_dgits_contribuicoes_consultas_publicas": ("Contribuições em consultas públicas", "Participação social em consultas", G_CT, DGITS, "saude"),
    "ciencia_tecnologia_dgits_controle_demandas_conitec": ("Controle de demandas da CONITEC", "Demandas de incorporação de tecnologias", G_CT, DGITS, "saude"),
    "ciencia_tecnologia_dgits_controle_pcdt": ("Controle de PCDT", "Protocolos e diretrizes terapêuticas", G_CT, DGITS, "saude"),
    "ciencia_tecnologia_dgits_tecnologias_diretrizes": ("Tecnologias e diretrizes", "Tecnologias avaliadas e diretrizes", G_CT, DGITS, "saude"),
    # Plataforma Brasil
    "plataformabr_projetos": ("Projetos de pesquisa cadastrados", "Pesquisas com seres humanos registradas", G_PB, "Ministério da Saúde — CONEP", "saude"),
    "plataformabr_projetos_{numero_caae}": ("Projetos de pesquisa por número CAAE", "Consulta individual por CAAE", G_PB, "Ministério da Saúde — CONEP", "saude"),
    # Outras áreas
    "sisvan_estado_nutricional": ("Sisvan", "Estado nutricional da população", G_OUT, MS, "saude"),
    "daf_estoque_medicamentos_bnafar_horus": ("DAF", "Estoque de medicamentos (BNAFAR/Hórus)", G_OUT, MS, "saude"),
    "educacao_em_saude_pvc": ("Educação em saúde (PVC)", "Ações de educação em saúde", G_OUT, MS, "saude"),
    "macrorregiao_e_regiao_de_saude_municipio": ("Macrorregião e região de saúde", "Regiões de saúde por município", G_OUT, MS, "saude"),
    "outros_temas_ced": ("Outros temas (CED)", "Temas complementares do catálogo", G_OUT, MS, "saude"),
    "prevencao_e_promocao_distribuicao_epi_insumo": ("Distribuição de insumos (EPI)", "Prevenção e promoção — insumos", G_OUT, MS, "saude"),
    # IBGE
    "ibge_populacao": ("População estimada", "Estimativas anuais de população", G_IBGE, "IBGE", "pop"),
    "ibge_populacao_idade_sexo": ("População por idade e sexo (Censo)", "Pirâmide etária do Censo", G_IBGE, "IBGE", "pop"),
    "ibge_pib_municipios": ("PIB dos municípios", "Produto interno bruto municipal", G_IBGE, "IBGE", "pop"),
    "ibge_nascidos_vivos_rc": ("Nascidos vivos (registro civil)", "Nascimentos por mês/sexo — registro cartorial", G_IBGE, "IBGE", "pop"),
    "ibge_obitos_rc": ("Óbitos (registro civil)", "Óbitos por mês/sexo — registro cartorial", G_IBGE, "IBGE", "pop"),
    "ibge_area_territorial": ("Área territorial e densidade", "Área, população e densidade demográfica (Censo 2022)", G_IBGE, "IBGE", "pop"),
    "ibge_casamentos": ("Casamentos (registro civil)", "Casamentos por mês do registro — registro cartorial", G_IBGE, "IBGE", "pop"),
    "ibge_divorcios": ("Divórcios (registro civil)", "Divórcios concedidos em 1ª instância — registro cartorial", G_IBGE, "IBGE", "pop"),
    "ibge_saneamento_agua": ("Saneamento: abastecimento de água (Censo)", "Domicílios por forma de abastecimento de água (Censo 2022)", G_IBGE, "IBGE", "san"),
    "ibge_saneamento_esgoto": ("Saneamento: esgotamento sanitário (Censo)", "Domicílios por tipo de esgotamento sanitário (Censo 2022)", G_IBGE, "IBGE", "san"),
    "ibge_saneamento_lixo": ("Saneamento: destino do lixo (Censo)", "Domicílios por destino do lixo (Censo 2022)", G_IBGE, "IBGE", "san"),
    # NASA
    "nasa_power": ("POWER", "Temperatura, radiação solar e vento", G_NASA, "NASA (EUA)", "clima"),
    "nasa_gpm": ("GPM IMERG", "Precipitação estimada por satélite", G_NASA, "NASA (EUA)", "clima"),
    "nasa_firms": ("FIRMS", "Focos de incêndio detectados por satélite", G_NASA, "NASA (EUA)", "clima"),
    # Ambiental (fontes brasileiras primárias)
    "inmet_estacoes": ("Estações Automáticas (INMET)", "Séries horárias históricas das estações meteorológicas automáticas", G_AMB, "INMET", "clima"),
    # Ambiental (Brasil)
    "inpe_queimadas": ("Queimadas (BDQueimadas)", "Focos de incêndio do programa nacional do INPE", G_AMB, "INPE", "clima"),
    # Saneamento
    "snis": ("SNIS", "Sistema Nacional de Informações sobre Saneamento", G_SAN, "Governo federal — gov.br (SNIS/SINISA)", "san"),
    "sinisa": ("SINISA", "Sistema Nacional de Informações em Saneamento Básico", G_SAN, "Governo federal — gov.br (SNIS/SINISA)", "san"),
    # Ambiental (INPE/INMET/ANA)
    "ana_hidro": ("ANA HidroWebService", "Séries telemétricas de chuva, nível e vazão por estação", G_AMB, "ANA — Agência Nacional de Águas", "clima"),
}

MODE_LABEL = {
    "opendatasus api": "API OpenDataSUS (DEMAS)",
    "datasus ftp": "FTP DATASUS (microdados)",
    "pysus ftp": "FTP DATASUS (microdados)",
    "ibge api": "API IBGE SIDRA",
    "nasa power api": "API NASA POWER",
    "nasa gpm api": "API NASA GPM",
    "nasa firms api": "API NASA FIRMS",
    "inpe queimadas api": "API INPE Queimadas",
    "gov.br crawl": "Crawler gov.br",
    "ana hidro api": "API ANA HidroWebService",
}

CADENCE_PT = {
    "daily": "diária", "weekly": "semanal", "monthly": "mensal",
    "annual": "anual", "irregular": "irregular",
}


def cli_example(key: str, params: list) -> str:
    names = {p["name"] for p in params}
    parts = [f"guaraci fetch run {key}"]
    if "start_year" in names:
        parts.append("--set start_year=2024 --set end_year=2024")
    if "states" in names:
        parts.append("--set states=SP")
    if "groups" in names:
        for p in params:
            if p["name"] == "groups" and p.get("allowed_values"):
                parts.append(f"--set groups={p['allowed_values'][0]}")
                break
    if "diseases" in names:
        parts.append("--set diseases=DENG")
    if "nu_ano" in names:
        parts.append("--set nu_ano=2024")
    if "latitude" in names:
        parts.append("--set latitude=-23.55 --set longitude=-46.63")
    if "start_date" in names and "start_year" not in names:
        parts.append("--set start_date=2024-01-01 --set end_date=2024-03-31")
    if "station_ids" in names:
        parts.append("--set station_ids=12345678")
    if "variable" in names and "latitude" not in names:
        for p in params:
            if p["name"] == "variable" and p.get("allowed_values"):
                parts.append(f"--set variable={p['allowed_values'][0]}")
                break
    parts.append("--format csv")
    return " ".join(parts)


def main() -> None:
    live = "--live" in sys.argv

    from guaraci.services.downloads import DownloadService
    from guaraci.orchestrator.cadence import profile_for

    service = DownloadService()
    fields_by_source = json.loads(DICT.read_text(encoding="utf-8"))
    stats = json.loads(STATS.read_text(encoding="utf-8")) if STATS.exists() else {}

    if live:
        stats = run_live_discover(service, stats)

    descriptors = {d.source: d for d in service.list_sources()}
    missing = [k for k in descriptors if k not in CURATED]

    catalog = {}
    # itera na ordem do CURATED — é a ordem editorial de exibição no site
    for key, cur in CURATED.items():
        desc = descriptors.get(key)
        if desc is None:
            continue
        n, d, g, m, area = cur
        schema = service.get_source_schema(key)
        prof = profile_for(key, desc.mode)
        entry_fields = fields_by_source.get(key, {})
        params = [
            {
                "name": p["name"], "type": p["type"], "desc": p["description"],
                "phase": p["phase"], "required": p["required"], "default": p["default"],
                "allowed": p["allowed_values"], "min": p["minimum"], "max": p["maximum"],
            }
            for p in schema["params"]
        ]
        catalog[key] = {
            "key": key, "n": n, "d": d, "g": g, "m": m, "area": area,
            "mode": desc.mode, "modeLabel": MODE_LABEL.get(desc.mode, desc.mode),
            "cadence": CADENCE_PT.get(prof.cadence.value, prof.cadence.value),
            "minYear": prof.min_year,
            "params": params,
            "fields": entry_fields.get("fields") or [],
            "rowsSampled": entry_fields.get("rows_sampled"),
            "fieldStatus": entry_fields.get("status"),
            "cli": cli_example(key, params),
            "discover": stats.get(key),
        }

    if missing:
        raise SystemExit(f"fontes sem entrada CURATED: {missing}")
    extra = set(CURATED) - set(catalog)
    if extra:
        raise SystemExit(f"entradas CURATED sem fonte no serviço: {sorted(extra)}")

    payload = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(
        "// GERADO por scripts/build_site_catalog.py — não editar à mão.\n"
        f"// Catálogo detalhado das {len(catalog)} fontes: parâmetros (DownloadService),\n"
        "// campos amostrados (field_dictionary.json), cadência (orquestrador) e discover FTP.\n"
        f"const GUARACI_CATALOG = {payload};\n"
        "const GUARACI_BASES = Object.values(GUARACI_CATALOG);\n",
        encoding="utf-8",
    )
    n_fields = sum(1 for c in catalog.values() if c["fields"])
    n_disc = sum(1 for c in catalog.values() if c["discover"])
    print(f"ok: {len(catalog)} fontes -> {OUT}")
    print(f"    {n_fields} com campos amostrados, {n_disc} com discover ao vivo")


# Anos candidatos por fonte (fontes legadas não têm dados recentes).
YEAR_CANDIDATES = {
    "cih": [2010],
    "pni": [2021, 2019, 2015],
    "sinasc": [2022, 2021],
    "siscan": [2015],
    "sisprenatal": [2013],
    "default": [2025, 2024, 2023],
}


def _all_groups(service, key: str):
    for p in service.get_source_schema(key)["params"]:
        if p["name"] == "groups" and p.get("allowed_values"):
            return list(p["allowed_values"])
    return None


def run_live_discover(service, stats: dict) -> dict:
    """Discover ao vivo (contagem de arquivos, sem download) nas fontes FTP."""
    ftp_sources = [
        d.source for d in service.list_sources()
        if d.mode in ("datasus ftp", "pysus ftp")
    ]
    for key in ftp_sources:
        if stats.get(key, {}).get("files"):
            print(f"cache: {key}")
            continue
        for year in YEAR_CANDIDATES.get(key, YEAR_CANDIDATES["default"]):
            try:
                if key in ("sim", "sinan"):
                    summary = _discover_sim_sinan(key, year)
                else:
                    kwargs = {"start_year": year, "end_year": year}
                    groups = _all_groups(service, key)
                    if groups:
                        kwargs["groups"] = groups
                    result = service.discover(key, **kwargs)
                    summary = {
                        "year": year,
                        "files": result.get("documents_found", 0),
                        "byGroup": result.get("by_group") or None,
                    }
            except Exception as exc:  # noqa: BLE001 — preflight best-effort
                print(f"skip: {key}@{year} ({type(exc).__name__}: {exc})")
                continue
            if summary["files"]:
                stats[key] = {k: v for k, v in summary.items() if v}
                print(f"live: {key}@{year} -> {summary['files']} arquivos")
                break
            print(f"vazio: {key}@{year}")
    STATS.parent.mkdir(exist_ok=True)
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    return stats


def _discover_sim_sinan(key: str, year: int) -> dict:
    """SIM/SINAN não passam pelo service.discover — usa o módulo FTP direto."""
    import asyncio

    from guaraci.datasus.ftp.client import DatasusFtpClient
    from guaraci.datasus.ftp.discovery import discover_sim, discover_sinan

    async def _run():
        async with DatasusFtpClient() as client:
            if key == "sim":
                return await discover_sim(client, years=[year])
            return await discover_sinan(client, years=[year])

    records = asyncio.run(_run())
    by_group: dict[str, int] = {}
    for rec in records:
        by_group[rec.group] = by_group.get(rec.group, 0) + 1
    return {"year": year, "files": len(records), "byGroup": by_group or None}


if __name__ == "__main__":
    main()
