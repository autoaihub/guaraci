// Catálogo das 91 bases do Guaraci — fonte única de dados para o explorador.
// area: saude | pop | clima | san
const GUARACI_BASES = [
  // ─── DATASUS · sistemas nacionais (FTP direto) ───
  { n: "SIH", d: "Internações hospitalares pelo SUS", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "SIM", d: "Mortalidade — óbitos e causas", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "SINAN", d: "Notificação compulsória de agravos", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "SINASC", d: "Nascidos vivos", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "SIA-SUS", d: "Atendimentos ambulatoriais (14 subgrupos)", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "CNES", d: "Cadastro de estabelecimentos de saúde (13 subgrupos)", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "PNI (histórico)", d: "Imunizações, base legada", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "CIHA", d: "Comunicação de internação hospitalar e ambulatorial", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "CIH (legado 2008–2010)", d: "Internações, versão anterior ao SIH", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "SISCAN", d: "Rastreamento de câncer de colo do útero e mama", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "SISPRENATAL", d: "Acompanhamento de pré-natal", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "RESP", d: "Microcefalia e arboviroses na gestação", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "PCE", d: "Controle da esquistossomose", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },
  { n: "Painel de Oncologia", d: "Produção de tratamentos oncológicos", g: "DATASUS · sistemas nacionais", m: "Ministério da Saúde (DATASUS)", area: "saude" },

  // ─── Emergências e vigilância · vitrine dedicada ───
  { n: "Dengue", d: "Casos notificados de dengue", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Chikungunya", d: "Casos notificados de chikungunya", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Zika", d: "Casos notificados de zika vírus", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Febre amarela", d: "Casos notificados de febre amarela", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Mpox", d: "Casos notificados de mpox", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Síndrome gripal leve", d: "Notificações de síndrome gripal leve", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "SRAG", d: "Síndrome respiratória aguda grave", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "ESAVI", d: "Eventos adversos pós-vacinação", g: "Emergências e vigilância", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Doses aplicadas (PNI)", d: "Painel de vacinação — doses aplicadas", g: "Emergências e vigilância", m: "Ministério da Saúde — Programa Nacional de Imunizações", area: "saude" },

  // ─── Arboviroses · catálogo aberto ───
  { n: "Chikungunya (catálogo aberto)", d: "Endpoint adicional no catálogo aberto", g: "Arboviroses · catálogo aberto", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Dengue (catálogo aberto)", d: "Endpoint adicional no catálogo aberto", g: "Arboviroses · catálogo aberto", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Febre amarela (catálogo aberto)", d: "Humanos e primatas não humanos", g: "Arboviroses · catálogo aberto", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },

  // ─── Vigilância e meio ambiente ───
  { n: "Mpox (catálogo aberto)", d: "Endpoint via catálogo aberto", g: "Vigilância e meio ambiente", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Mortalidade (catálogo aberto)", d: "Sistema de informação sobre mortalidade via catálogo aberto", g: "Vigilância e meio ambiente", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },
  { n: "Nascidos vivos (catálogo aberto)", d: "Sistema de informação sobre nascidos vivos via catálogo aberto", g: "Vigilância e meio ambiente", m: "Ministério da Saúde — Secretaria de Vigilância em Saúde", area: "saude" },

  // ─── Vacinação ───
  { n: "ESAVI (catálogo aberto)", d: "Endpoint via catálogo aberto", g: "Vacinação", m: "Ministério da Saúde — Programa Nacional de Imunizações", area: "saude" },
  { n: "Insumos estratégicos de vacinação", d: "Estoque e distribuição de insumos", g: "Vacinação", m: "Ministério da Saúde — Programa Nacional de Imunizações", area: "saude" },

  // ─── CNES · catálogo aberto ───
  { n: "Estabelecimentos de saúde", d: "Cadastro nacional via catálogo aberto", g: "CNES · catálogo aberto", m: "Ministério da Saúde (CNES)", area: "saude" },
  { n: "Estabelecimentos por código CNES", d: "Consulta individual por código", g: "CNES · catálogo aberto", m: "Ministério da Saúde (CNES)", area: "saude" },
  { n: "Tipos de unidade de saúde", d: "Tabela de tipos de unidade", g: "CNES · catálogo aberto", m: "Ministério da Saúde (CNES)", area: "saude" },
  { n: "Tipos de unidade por código", d: "Consulta individual por código", g: "CNES · catálogo aberto", m: "Ministério da Saúde (CNES)", area: "saude" },

  // ─── Sisagua · qualidade da água ───
  { n: "Vigilância — parâmetros básicos", d: "Qualidade da água para consumo humano", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Controle semestral", d: "Monitoramento semestral da água", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Controle mensal — parâmetros básicos", d: "Monitoramento mensal da água", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Pontos de captação de água", d: "Localização dos pontos de captação", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Carros-pipa — população atendida", d: "Abastecimento emergencial por carros-pipa", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Carros-pipa — procedência da água", d: "Origem da água distribuída", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Controle mensal — amostras fora do padrão", d: "Amostras em desacordo com o padrão", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Controle mensal — demais parâmetros", d: "Parâmetros complementares mensais", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Controle mensal — infraestrutura operacional", d: "Infraestrutura dos sistemas de abastecimento", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Controle mensal — plano de amostragem", d: "Planos de amostragem dos sistemas", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "População abastecida", d: "População atendida por sistema", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Tratamento de água", d: "Formas de tratamento aplicadas", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Vigilância — cianobactérias e cianotoxinas", d: "Monitoramento de cianobactérias", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },
  { n: "Vigilância — demais parâmetros", d: "Parâmetros complementares de vigilância", g: "Sisagua · qualidade da água", m: "Ministério da Saúde — Vigilância em Saúde Ambiental", area: "saude" },

  // ─── Saúde indígena · SASISUS/SIASI ───
  { n: "Esgotamento sanitário em aldeias", d: "Saneamento em territórios indígenas", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Gerenciamento de resíduos sólidos", d: "Resíduos sólidos em aldeias", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Obras de infraestrutura de saúde", d: "Acompanhamento de obras em territórios indígenas", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Fornecimento e qualidade da água", d: "Acesso à água em aldeias", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Habilitação e recebimento de incentivo", d: "Registros de habilitação e incentivos", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Vigilância alimentar e nutricional indígena", d: "Estado nutricional de povos indígenas", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Acompanhamento gestacional (SIASI)", d: "Gestação em povos indígenas", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Módulo de morbidades (SIASI)", d: "Morbidades em povos indígenas", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Saúde bucal — ficha 3", d: "Atividades coletivas: escovação supervisionada, flúor gel, educação em saúde", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Saúde bucal — ficha 4", d: "Ficha odontológica individual: prótese, fluorose, má-formação orofacial", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Saúde bucal — ficha 7", d: "Procedimentos clínicos das equipes multidisciplinares (EMSI)", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },
  { n: "Covid-19 em povos indígenas", d: "Enfrentamento e monitoramento da Covid-19", g: "Saúde indígena · SASISUS/SIASI", m: "Ministério da Saúde — SESAI", area: "saude" },

  // ─── Atenção primária ───
  { n: "PMMB — Programa Médicos pelo Brasil", d: "Dados gerais do programa", g: "Atenção primária", m: "Ministério da Saúde — Atenção Primária à Saúde", area: "saude" },
  { n: "PMMB — profissionais ativos", d: "Profissionais em atividade", g: "Atenção primária", m: "Ministério da Saúde — Atenção Primária à Saúde", area: "saude" },
  { n: "PMMB — série histórica", d: "Evolução histórica do programa", g: "Atenção primária", m: "Ministério da Saúde — Atenção Primária à Saúde", area: "saude" },
  { n: "Cadastro vinculado ao Previne Brasil", d: "Cadastros do programa Previne Brasil", g: "Atenção primária", m: "Ministério da Saúde — Atenção Primária à Saúde", area: "saude" },
  { n: "Indicador de desempenho do Previne Brasil", d: "Indicadores de desempenho", g: "Atenção primária", m: "Ministério da Saúde — Atenção Primária à Saúde", area: "saude" },

  // ─── Assistência à saúde ───
  { n: "Hospitais e leitos", d: "Capacidade hospitalar instalada", g: "Assistência à saúde", m: "Ministério da Saúde", area: "saude" },
  { n: "Ocupação hospitalar — Covid-19", d: "Ocupação de leitos na pandemia", g: "Assistência à saúde", m: "Ministério da Saúde", area: "saude" },
  { n: "Unidades básicas de saúde", d: "Rede de UBS do país", g: "Assistência à saúde", m: "Ministério da Saúde", area: "saude" },

  // ─── Economia da saúde ───
  { n: "BPS", d: "Indicadores de economia da saúde", g: "Economia da saúde", m: "Ministério da Saúde", area: "saude" },
  { n: "ApuraSUS", d: "Apuração e gestão de custos do SUS", g: "Economia da saúde", m: "Ministério da Saúde", area: "saude" },

  // ─── Ciência e tecnologia · DGITS ───
  { n: "Contribuições em consultas públicas", d: "Participação social em consultas", g: "Ciência e tecnologia · DGITS", m: "Ministério da Saúde — DGITS", area: "saude" },
  { n: "Controle de demandas da CONITEC", d: "Demandas de incorporação de tecnologias", g: "Ciência e tecnologia · DGITS", m: "Ministério da Saúde — DGITS", area: "saude" },
  { n: "Controle de PCDT", d: "Protocolos e diretrizes terapêuticas", g: "Ciência e tecnologia · DGITS", m: "Ministério da Saúde — DGITS", area: "saude" },
  { n: "Tecnologias e diretrizes", d: "Tecnologias avaliadas e diretrizes", g: "Ciência e tecnologia · DGITS", m: "Ministério da Saúde — DGITS", area: "saude" },

  // ─── Plataforma Brasil ───
  { n: "Projetos de pesquisa cadastrados", d: "Pesquisas com seres humanos registradas", g: "Plataforma Brasil", m: "Ministério da Saúde — CONEP", area: "saude" },
  { n: "Projetos de pesquisa por número CAAE", d: "Consulta individual por CAAE", g: "Plataforma Brasil", m: "Ministério da Saúde — CONEP", area: "saude" },

  // ─── Outras áreas do catálogo aberto ───
  { n: "Sisvan", d: "Estado nutricional da população", g: "Outras áreas do catálogo aberto", m: "Ministério da Saúde", area: "saude" },
  { n: "DAF", d: "Estoque de medicamentos (BNAFAR/Hórus)", g: "Outras áreas do catálogo aberto", m: "Ministério da Saúde", area: "saude" },
  { n: "Educação em saúde (PVC)", d: "Ações de educação em saúde", g: "Outras áreas do catálogo aberto", m: "Ministério da Saúde", area: "saude" },
  { n: "Macrorregião e região de saúde", d: "Regiões de saúde por município", g: "Outras áreas do catálogo aberto", m: "Ministério da Saúde", area: "saude" },
  { n: "Outros temas (CED)", d: "Temas complementares do catálogo", g: "Outras áreas do catálogo aberto", m: "Ministério da Saúde", area: "saude" },
  { n: "Distribuição de insumos (EPI)", d: "Prevenção e promoção — insumos", g: "Outras áreas do catálogo aberto", m: "Ministério da Saúde", area: "saude" },

  // ─── IBGE · população e economia ───
  { n: "População estimada", d: "Estimativas anuais de população", g: "IBGE · população e economia", m: "IBGE", area: "pop" },
  { n: "População por idade e sexo (Censo)", d: "Pirâmide etária do Censo", g: "IBGE · população e economia", m: "IBGE", area: "pop" },
  { n: "PIB dos municípios", d: "Produto interno bruto municipal", g: "IBGE · população e economia", m: "IBGE", area: "pop" },

  // ─── NASA · clima e ambiente ───
  { n: "POWER", d: "Temperatura, radiação solar e vento", g: "NASA · clima e ambiente", m: "NASA (EUA)", area: "clima" },
  { n: "GPM IMERG", d: "Precipitação estimada por satélite", g: "NASA · clima e ambiente", m: "NASA (EUA)", area: "clima" },
  { n: "FIRMS", d: "Focos de incêndio detectados por satélite", g: "NASA · clima e ambiente", m: "NASA (EUA)", area: "clima" },

  // ─── Saneamento · gov.br ───
  { n: "SNIS", d: "Sistema Nacional de Informações sobre Saneamento", g: "Saneamento · gov.br", m: "Governo federal — gov.br (SNIS/SINISA)", area: "san" },
  { n: "SINISA", d: "Sistema Nacional de Informações em Saneamento Básico", g: "Saneamento · gov.br", m: "Governo federal — gov.br (SNIS/SINISA)", area: "san" },
];
