# Changelog

## [Unreleased]

### Fixed: falha de rede registrada como vazio no orquestrador
No ciclo real do orquestrador (backfill, atualização e backfill de novo, dez
fontes de cinco tipos de perfil, 503 unidades), quatro anos do IBGE
(2017 a 2020) deram timeout e entraram no ledger como `empty`. A atualização
só revisita o último ano, então esses anos ficariam faltando no bronze sem
ninguém perceber. Duas camadas:

- Nas fontes SIDRA do IBGE, erro recuperável (timeout, conexão) conta em
  `failed_count` e, se todos os anos pedidos falharem, sobe como erro. O ano
  que a SIDRA recusa por não existir (censo sem estimativa) segue pulado.
- No runner, para toda fonte, `failed_count` maior que zero ou falha de
  exportação reportada como aviso viram `error`, e a unidade volta a ser
  pedida na próxima execução.

### Fixed: conteúdo exportado e resiliência dos jobs
Duas verificações novas. `scripts/verificar_conteudo.py` coleta cada fonte em
CSV, Parquet e SQLite e abre o arquivo: linhas, colunas entre formatos,
colunas contra o dicionário, acentuação quebrada e valor perdido na
conversão (nas APIs, contra o JSON bruto da mesma coleta, porque o DEMAS não
devolve as linhas na mesma ordem duas vezes). `scripts/verificar_resiliencia.py`
sobe um servidor real e provoca jobs simultâneos, cancelamento no meio do
download, origem fora do ar e muda, servidor derrubado no meio da coleta e
entradas inválidas; os seis casos passam.

Defeitos encontrados:

- **Valor perdido na conversão dos arquivos do portal** (SRAG, SISAGUA,
  tuberculose, ENANI). Parquet e SQLite eram tipados pelas primeiras 10 mil
  linhas com `ignore_errors`: o que não cabia no tipo virava nulo sem aviso
  ("10A" numa coluna lida como inteira), e o inteiro comia o zero à esquerda
  de CNES e CEP. Toda coluna agora sai como texto, como na ANVISA.
- **CSV do portal fora do padrão**: saía como publicado, com `;`, e a SRAG de
  2016 em latin-1. Agora é UTF-8 com vírgula, como toda outra fonte; com
  `keep_raw` o original fica como `<nome>.original.csv`.
- **Carro-pipa (procedência) sem cabeçalho**: o SISAGUA publica o CSV sem
  essa linha, e a primeira linha de dado virava nome de coluna e sumia do
  resultado; o SQLite nem exportava. O cabeçalho é reconstruído pela
  convenção do próprio SISAGUA (o dicionário da página dá 404), e a conversão
  falha com erro claro se a origem mudar o número de campos.
- **Texto codificado duas vezes pela origem** nas APIs do DEMAS
  ("ALTO RIO JURUÃ\x81" por "ALTO RIO JURUÁ", saúde indígena): corrigido
  quando a volta é exata, com aviso no job de quantos valores mudaram.
- **Downloads do portal e da ANVISA sem progresso**: o job mostrava 0 B até
  o fim e o cancelamento só agia depois do arquivo inteiro. Agora o progresso
  sai a cada 1 MB e o cancelamento leva menos de um segundo, sem deixar
  `.part`.
- **Cópia local desatualizada**: um arquivo já presente na pasta era
  reaproveitado só por existir, e o banco vivo da SRAG, republicado toda
  semana com o mesmo nome, podia sair velho. Agora só se o tamanho bater com
  o do servidor.
- `POST /jobs` quebrava em fontes cujo ano é opcional no schema e obrigatório
  no adapter (registro civil do IBGE): todo padrão do schema passa a ser
  aplicado, como a interface já fazia.
- Nome de coluna do CMED com espaço não separável no fim
  (`DESTINAÇÃO COMERCIAL`).

Dicionário de campos: 114 das 124 fontes com colunas reais (eram 94). As 13
do SISAGUA tinham os nomes da antiga API do DEMAS, e o PNI os nomes antigos
da API. Ficam como defeito conhecido da origem, sem correção possível: `�`
no PNI (a API já manda `\ufffd`) e 29 lotes de vacina com `Â` na SRAG 2026.

### Fixed: defeitos achados pela varredura de rotas
Nova ferramenta `scripts/verificar_rotas.py` percorre as 124 fontes pela API
e pela CLI, na camada offline (746 verificações), na de estimativa e na de
coleta pelos jobs. Na primeira passada ela achou três defeitos que a suíte não
cobria:

- O botão "Estimar volume" respondia 500 em 25 das 31 fontes que o oferecem
  (SISAGUA, SRAG, tuberculose SESAI, ENANI): o adapter de arquivos do portal
  devolve `dataset`/`resources`, e a resposta da API exigia `source` e
  `total_size_bytes`. A rota agora normaliza o formato.
- O formulário das fontes FTP abria em 2025 para todas, e seis sistemas não
  têm esse ano: CIH termina em 2011, SISPRENATAL em 2014, SISCAN em 2015 e
  PNI em 2019 (conferido ao vivo em 24/09/2026). Esses quatro ganham teto
  (`max_year`), que também limita o orquestrador. SINASC (último ano em
  NOV/DNRES: 2022) e RESP (2024) seguem vivos e só mudam o ano inicial.
- `guaraci fetch run sinasc` e `fetch discover sinasc` sem `--set` quebravam
  com TypeError/KeyError: a validação aceitava omitir um obrigatório com
  padrão, mas ninguém aplicava o padrão. O serviço agora o preenche antes de
  despachar, valendo para CLI, API, jobs e orquestrador.

A camada de interface (`scripts/verificar_interface.py`, Chrome real via
Playwright) percorre as 124 fontes: abre o formulário, confere que todo
parâmetro virou campo, estima o volume e captura o pedido que "Iniciar
coleta" monta. Ela achou mais três defeitos:

- Com o formulário intocado, o formato de saída vinha vazio e `keep_raw`
  desligado: IBGE, NASA e DEMAS baixavam, descartavam e o job terminava
  "Concluída" sem arquivo. O formato agora vem em CSV, e a opção vazia se
  chama "(não exportar)" em vez de "(sem filtro)".
- A gaveta do job mostrava "2 / 1" arquivos: um `file_completed` que já traz
  `files_completed` era contado de novo.
- Trocar o idioma deixava o rodapé em "API: conectando…" até a próxima
  checagem de saúde.

A camada de coleta real (`--camada jobs`: uma coleta pequena por fonte pela
API de jobs, 124 fontes em cerca de 10 minutos) achou o resto:

- Sete fontes abriam num ano ainda não publicado, e o job terminava sem dado:
  SIM e síndrome gripal leve (último ano: 2024), os quatro indicadores do
  registro civil do IBGE (2024) e o PIB municipal (2023). O último ano
  publicado agora mora em `guaraci/services/publication_years.py`, conferido
  ao vivo; o teto continua no ano corrente.
- A consulta pontual do CNES (`cnes_estabelecimentos_por_codigo_cnes`,
  `cnes_tipounidades_por_codigo_tipo_unidade`) sempre dizia "No records": a
  origem devolve o próprio registro, sem lista em volta, e ele era
  descartado. O arquivo também saía com o molde literal
  (`cnes_estabelecimentos_{codigo_cnes}_...`) no nome.
- `economia_da_saude_bps` devolvia vazio para o CATMAT escrito como no portal
  (`BR0267614`); o prefixo agora é removido.
- Quando o DATASUS publica um arquivo sem registro (RESP do Acre em 2024), o
  aviso mandava "conferir formato e filtros"; agora diz que o recorte veio
  vazio da origem.

Cinco endpoints do DEMAS respondem lista vazia na própria origem, sem
parâmetro obrigatório; ficam no catálogo e estão listados em
`docs/SOURCES_AND_FILTERS.md` §3.6. Os 34 testes ao vivo que vêm desligados
(`GUARACI_*_SMOKE=1`) passam; o da ANA segue pulado por falta de credencial.

### Added: oito fontes da ANVISA, e o tema vigilância sanitária
O catálogo vai a 124, com a ANVISA como nona instituição de origem. Os
arquivos vêm de `dados.anvisa.gov.br/dados/`, uma listagem sem API, e são
sobrescritos a cada atualização: o orquestrador guarda um instantâneo por mês
para existir histórico.

| Fonte | Linhas em 24/09/2026 |
| --- | --- |
| `anvisa_vigimed_notificacoes` (farmacovigilância) | 356 107 |
| `anvisa_vigimed_medicamentos` | 699 311 |
| `anvisa_vigimed_reacoes` (MedDRA) | 1 093 739 |
| `anvisa_tecnovigilancia` (dispositivos médicos) | 287 464 |
| `anvisa_hemovigilancia` (reações transfusionais) | 237 737 |
| `anvisa_medicamentos_registrados` | 43 557 |
| `anvisa_cmed_precos` | 25 702 |
| `anvisa_cmed_precos_governo` (PMVG) | 25 702 |

Todas coletadas ao vivo pelo orquestrador, sem erro, e a segunda execução não
baixou nada. A exportação converte cp1252 para UTF-8 em fluxo e mantém toda
coluna como texto, porque o formato de data muda de um arquivo para outro.
Três defeitos da origem são tratados sem adivinhar:

- O VigiMed não usa aspas, mas um campo começa com uma (`"500" Dosage
  unit...`), e o leitor engolia o resto do arquivo. Arquivos sem aspas agora
  são redivididos linha a linha.
- A tecnovigilância publica listas `" ; "` dentro de dois campos, sem aspas.
  O `;` entre espaços fica dentro do campo. A única linha que ainda não
  encaixa (1 de 287 465) vai inteira para `.rejeitadas.csv`, com o número da
  linha, em vez de ser cortada por palpite; o orquestrador leva esse arquivo
  junto para o bronze.
- O CMED abre com preâmbulo de tamanho variável (59 e 72 linhas); o
  cabeçalho é achado pelo conteúdo.

Novo tema `vigilancia_sanitaria` (farmacovigilância, tecnovigilância,
hemovigilância e registro de produtos), porque nenhum dos 20 anteriores
cobria esse assunto.

Ficaram de fora: o NOTIVISA do Núcleo de Segurança do Paciente, que não tem
cabeçalho e cujo dicionário publicado descreve outra tabela, e o SNGPC, com
cerca de 1 GB por mês e sem os meses de 2021-11 a 2025-12.

### Fixed: as 14 fontes SISAGUA nunca chegavam ao data lake
O SISAGUA publica tudo em `.zip`, e a conversão só aceitava CSV e Parquet
soltos. Na CLI isso aparecia como aviso; no orquestrador, como `empty`,
porque nenhum CSV era produzido. Verificado ao vivo em 24/09/2026: a varredura
de `sisagua_cadastro_carro_pipa_populacao` devolvia cinco unidades `empty`, e
o mesmo valia para as outras 13. Nenhuma fonte SISAGUA tinha chegado ao bronze.

- Um zip com CSV agora é extraído em fluxo, só pelo nome-base de cada membro
  (sem zip slip), e cada CSV é convertido. Zip sem CSV continua dando erro
  explícito.
- As dez fontes SISAGUA cumulativas, que republicam um arquivo único com o
  estado atual, viram instantâneo mensal no orquestrador. Antes eram pedidas
  uma vez por ano, e cada unidade baixaria o mesmo arquivo inteiro.

Depois da correção, ao vivo: carro-pipa com 2 107 linhas num instantâneo só,
pontos de captação com 2,9 milhões e controle semestral de 2026 com 1,43
milhão.

### Added: tuberculose na saúde indígena e o ENANI-2019
Duas fontes novas do portal de dados abertos do MS, e o catálogo vai a 116.

- `sesai_tuberculose`: casos de tuberculose atendidos pelo SIASI, com o
  paciente já desidentificado na origem. Só 2022 está publicado (505 casos).
- `enani_2019`: microdados do Estudo Nacional de Alimentação e Nutrição
  Infantil, edição única. Um zip de 223 MB com 26 bancos (cerca de 2,7 GB
  abertos), o original e 25 cópias imputadas, todas com 741 colunas e 14 558
  crianças. O orquestrador grava cada banco como arquivo próprio no bronze,
  com o nome do banco como sufixo, em vez de só o primeiro.

O SIES, terceira candidata desta leva, ficou de fora: os links de download
no portal redirecionam para a página inicial, e o bucket não tem os arquivos.
O SIES já está no catálogo pela API, como
`vacinacao_sistema_de_informacao_de_insumos_estrategicos`.

### Added: bancos históricos de SRAG, de 2009 a 2018
Duas fontes novas, `srag_arquivos_2009_2012` e `srag_arquivos_2013_2018`, e o
catálogo vai a 114. A série de síndrome respiratória aguda grave passa a
começar em 2009 em vez de 2019, o que traz a pandemia de H1N1: 88 354
notificações só em 2009. As duas espelham os conjuntos do portal como estão
publicados, no layout antigo do SINAN Influenza (113 e 114 colunas contra as
194 do SIVEP-Gripe atual), então não empilham com `srag_arquivos` sem um
mapeamento de colunas.

Coletadas ao vivo em 24/09/2026, ano a ano, pelo orquestrador: 125 250 linhas
em 2009-2012 e 201 799 em 2013-2018, sem erro. O update seguinte não pediu
nada, porque um banco congelado agora tem teto de ano (`max_year` no perfil
de cadência) e sai da reconsulta quando o último ano entra no ledger. Sem o
teto, o update semanal pediria todo ano de 2012 até o corrente.

### Fixed: três defeitos na conversão dos arquivos do portal
Apareceram na primeira coleta dos bancos históricos. Os dois primeiros valem
também para o `srag_arquivos` atual.

- **Todo CSV de SRAG usa `;`**, de 2009 ao banco vivo de 2026, e o conversor
  lia com a vírgula padrão. Cada linha virava um campo só e a conversão
  abortava com "found more fields than defined in Schema". Não aparecia antes
  porque o `srag_arquivos` prefere o parquet da origem e nunca passava pelo
  CSV. O separador agora sai do cabeçalho.
- **O polars só lê UTF-8**, e o banco de 2016 vem em latin-1. Um arquivo que
  não seja UTF-8 é lido por uma cópia transcodificada, feita em blocos e
  apagada ao fim. O arquivo baixado não é alterado.
- **O CSV desses bancos não está no bucket S3**, e sim na distribuição
  CloudFront do Ministério que a página do recurso linka. O scraper só
  reconhecia o S3, então esses recursos sumiam da descoberta sem aviso. A
  CDN entra como segunda opção, e só para URL com extensão de dado, porque a
  página também carrega fontes e estilos de CDN.

## [0.8.0] - 2026-09-24

### Added: a CETESB entra na varredura do data lake
As três fontes CETESB ficavam fora do orquestrador bronze. Para duas delas
isso custava dado: a janela aberta de 48 horas não tem histórico, e o que não
for guardado no dia se perde. O orquestrador ganha dois formatos de fonte.

| Fonte | Formato | Cadência | Partição bronze |
| --- | --- | --- | --- |
| `cetesb_qualar` | `snapshot` | diária | `CETESB_QUALAR/2026/09/cetesb_qualar_20260924.csv` |
| `cetesb_estacoes` | `snapshot` | mensal | `CETESB_ESTACOES/2026/09/cetesb_estacoes_202609.csv` |
| `cetesb_qualar_horario` | `api_monthly` | mensal, desde 2022 | `CETESB_QUALAR_HORARIO/2026/08/cetesb_qualar_horario_202608.csv` |

- **Instantâneo** (`snapshot`): cada execução grava uma cópia com a data da
  coleta como identidade da partição. Não há backfill, porque o passado já
  não está na fonte. A janela de 48h é o dobro do intervalo diário, então um
  dia de falha do servidor não abre buraco. Instantâneos consecutivos se
  sobrepõem por construção; a deduplicação por estação, poluente e hora é
  papel da camada prata.
- **Série mensal** (`api_monthly`): o QUALAR autenticado é varrido um mês
  civil por unidade, num recorte fixo, porque cada par estação/parâmetro é
  uma requisição e a rede inteira seriam 1500 por mês. O recorte é a Grande
  São Paulo (30 estações) com os seis poluentes, temperatura e umidade,
  definido em `SWEEP_STATIONS` e `SWEEP_PARAMETERS`. O bronze guarda também
  a leitura ainda não validada, marcada na coluna `validado`, e o update
  repuxa sempre os dois meses anteriores ao corrente, porque a CETESB valida
  com atraso. Sem `GUARACI_QUALAR_LOGIN`/`GUARACI_QUALAR_SENHA` no ambiente
  a fonte sai da varredura com o motivo, em vez de gerar erro todo mês.

Verificado ao vivo em 24/09/2026 numa árvore bronze temporária: as duas
fontes abertas materializaram 9 940 leituras e 62 estações, e a segunda
execução não repetiu nada. Um mês do recorte autenticado (agosto de 2026)
rendeu 82 877 leituras de 26 das 30 estações, nos oito parâmetros, em 7,7
minutos; o backfill desde 2022 fica em torno de 7 horas, para rodar uma vez
fora do horário de pico.

### Fixed: login do QUALAR autenticado, validado ao vivo
A primeira coleta real de `cetesb_qualar_horario` (24/09/2026, Pinheiros,
MP10 e temperatura, 01 a 07/08/2026) expôs dois defeitos que os testes
offline não alcançavam, porque a resposta simulada do login era 200.

- O QUALAR confirma login certo com **302 sem cabeçalho `Location`**. O
  `urllib` não tem para onde seguir e levanta `HTTPError`, que o cliente
  convertia em falha. Nenhum login funcionava. Um 3xx agora é lido como
  resposta; o cookie de sessão já veio nele. Senha errada continua
  detectada pela tela de login devolvida com 200, conferido ao vivo.
- Com todos os pares estação/parâmetro falhando, a coleta terminava em
  "dataframe vazio", que parece ausência de dado. Agora levanta
  `CetesbClientError` com a primeira causa, e falha parcial vira aviso com os
  pares afetados.

Depois da correção a mesma coleta trouxe 336 leituras (168 horas de cada
parâmetro), em µg/m³ e °C, com a hora `24:00` da CETESB convertida para a
meia-noite do dia seguinte. A fonte deixa de ser experimental.

### Added: concentração medida de poluentes pelo QUALAR autenticado
`cetesb_qualar_horario`, a contraparte da fonte aberta adicionada na entrada
seguinte. O catálogo vai a 112. Onde o ArcGIS público entrega índice das
últimas 48 horas, o QUALAR clássico entrega **concentração medida** em série
histórica, que é o que um estudo de exposição precisa: índice é transformação
por faixas e não alimenta modelo dose-resposta.

| | `cetesb_qualar` | `cetesb_qualar_horario` |
| --- | --- | --- |
| Medida | índice | concentração (µg/m³, ppm…) |
| Período | últimas 48h | qualquer intervalo |
| Credencial | nenhuma | conta no QUALAR |
| Parâmetros | 6 poluentes | 12 poluentes + 8 meteorológicos |

A segunda linha da direita é o ganho menos esperado: o QUALAR mede temperatura,
umidade, vento, pressão e radiação **nas mesmas estações** onde mede poluente.
Dá para montar exposição e confundidor meteorológico a partir de uma fonte só,
no mesmo ponto geográfico.

A credencial sai apenas de `GUARACI_QUALAR_LOGIN` e `GUARACI_QUALAR_SENHA`,
nunca de parâmetro de job, porque parâmetro de job é persistido no manifesto e
no histórico de execuções. É o mesmo tratamento de `nasa_firms`, `nasa_gpm` e
`ana_hidro`. Conta gratuita em
`https://seguranca.cetesb.sp.gov.br/Home/CadastrarUsuario`.

O protocolo foi reconstruído a partir do HTML do próprio sistema e do pacote R
`qualR` (rOpenSci, MIT, mesma licença do Guaraci), que também é a procedência
das tabelas de código em `guaraci/cetesb/codes.py`: 75 estações e 20
parâmetros, cujos códigos não existem publicados fora dos `<select>` do
formulário, atrás do login. O crédito está registrado no cabeçalho do módulo.

Cinco armadilhas que o conector trata, todas capazes de produzir resposta
plausível e errada em vez de erro:

- **Senha errada não parece erro.** O QUALAR responde HTTP 200 com a própria
  tela de login, o que passaria por "nenhum dado no período". O cliente
  verifica o conteúdo, não o código HTTP.
- **A resposta é HTML, não CSV**, apesar de o endpoint se chamar
  `exportaDados`. O parser usa o `html.parser` da biblioteca padrão, sem
  acrescentar dependência. Ele procura a tabela de 19 colunas em vez de contar
  posição de tabela, e trabalha com pilha, porque o HTML é dos anos 90 e aninha
  tabelas como layout; uma implementação de um nível devolveria zero linhas em
  silêncio.
- **Números vêm em formato brasileiro.** O ponto de milhar sai antes de a
  vírgula decimal virar ponto; só trocar a vírgula transformaria `1.234,56` em
  `1.23456`.
- **Nem toda linha é dado válido.** A coluna de validação da CETESB diz se a
  leitura passou pela crítica do órgão. O padrão devolve só as validadas, e a
  escolha fica exposta em `only_validated` em vez de embutida.
- **O código de estação do QUALAR não é o `ID` do ArcGIS.** Pinheiros é 99 num
  e 42 no outro. As duas numerações hoje não se sobrepõem (ArcGIS usa 1-62,
  QUALAR usa 66-290, conferido ao vivo), então a troca dá erro em vez de
  devolver outra estação, mas isso é propriedade do dado atual e não promessa
  da CETESB. Há teste fixando a disjunção.

Um pedido por par estação/parâmetro, sem chamada em lote: varrer a rede inteira
para seis poluentes são 372 requisições contra um sistema público estadual.
Daí `pause_seconds`, com padrão de 1 segundo, e a exclusão da varredura do
orquestrador bronze, que registra o motivo (exige credencial e lista explícita
de estações) em vez de deixar a fonte cair no ramo de "formato não reconhecido".

**Estado: validado ao vivo em 24/09/2026** (ver a entrada de correção acima).
Os testes offline cobrem o parser, o formato numérico, as datas, as tabelas de
código e os modos de falha. A fonte está declarada no dicionário de dados como
`needs_credential`.

### Added: qualidade do ar da CETESB, e o primeiro publicador estadual do catálogo
Duas fontes novas, `cetesb_qualar` e `cetesb_estacoes`, elevando o catálogo de
109 para 111. A CETESB documenta o QUALAR como sistema de consulta com
cadastro, mas o mesmo banco está exposto sem autenticação nenhuma num ArcGIS
Server em `servicos.cetesb.sp.gov.br/arcgis`, e é por ali que o conector entra:
JSON sobre HTTP, sem chave, sem formulário. É também a primeira fonte estadual
do Guaraci; todas as outras 109 são federais.

**Os valores são ÍNDICE de qualidade do ar, não concentração.** Isso precisa
ficar dito antes de qualquer outra coisa, porque nada no payload avisa e as
magnitudes são plausíveis nas duas leituras. A verificação que resolve: em
2026-09-15 10:00 a camada de MP10 devolveu `M1 = 10` para a estação Americana,
e a camada de estações devolveu `Indice = 10` com `POLUENTE = MP10` para a
mesma estação e hora. Bateu em oito estações seguidas. Concentração em µg/m³ só
pelo QUALAR clássico, com login. O índice é uma transformação por faixas,
definida pela Resolução CONAMA 506/2024, e não pode alimentar modelo
dose-resposta como se fosse concentração.

O aviso aparece onde o usuário lê, não só no código: na descrição do parâmetro
`pollutants` do schema, no título da fonte, no dicionário de dados, no catálogo
do site e em `docs/SOURCES_AND_FILTERS.md` §3.23. Documentação que só vive em
docstring não chega a quem usa.

O que cada fonte entrega:

- `cetesb_qualar`: uma linha por estação, poluente e hora, com as colunas
  `estacao, municipio, latitude, longitude, poluente, datahora, indice`. Seis
  poluentes (CO, MP10, MP2.5, NO2, O3, SO2), 62 estações;
- `cetesb_estacoes`: o cadastro geolocalizado das estações, com endereço,
  município, tipo e situação da rede, e o índice corrente com a mensagem de
  saúde associada.

Três decisões que valem registro:

- **O município é anexado na coleta.** As camadas de poluente identificam a
  estação só pelo nome e nunca dizem em que município ela fica. Sem município
  não há ligação com o dado de saúde, que no Guaraci é indexado por município
  de ponta a ponta. A junção contra o cadastro acontece uma vez, dentro do
  conector, em vez de virar tarefa de quem consome. Se a camada de cadastro
  falhar, a coleta termina assim mesmo, com `municipio` nulo e um aviso: o
  cadastro enriquece a série, não pode derrubá-la.
- **Os carimbos de hora são hora local.** Os campos `TM` vêm em milissegundos
  de época e decodificam para a hora de parede de São Paulo quando lidos como
  UTC. Aplicar deslocamento de fuso desloca a série inteira em três horas sem
  que nada quebre. Há teste dedicado a isso.
- **A janela é móvel, de 48 horas, e não há histórico.** Acumular série exigiria
  instantâneos periódicos concatenados, um padrão append-only que a árvore
  bronze, particionada por ano/mês, não modela. As duas fontes entram no
  orquestrador com `auto=False` e uma nota explicando que ficam fora da
  varredura de propósito, e não por não terem sido reconhecidas. Existe um
  serviço `QA_Hist` com 110.301 linhas horárias, mas ele cobre apenas
  02/03/2021 a 26/10/2021 e parou ali; é um instantâneo morto, também em
  índice, e não é usado.

Respostas truncadas pelo ArcGIS (`exceededTransferLimit`) viram erro explícito
em vez de janela silenciosamente incompleta, que passaria por série real.

Cobertura: 35 testes offline com cliente falso, mais um smoke test opt-in
(`GUARACI_CETESB_SMOKE=1`) que refaz ao vivo a checagem índice versus
concentração. Se a CETESB um dia passar a publicar concentração naquelas
colunas, é ali que se descobre, e não através de um estudo construído na
unidade errada.

Também corrigido de passagem: o site anunciava 17 grupos no contador e 18 no
texto da mesma seção. São 18.

### Added: o catálogo passa a ser navegável por assunto, com temas e presets
O Guaraci registra 109 fontes. Saber que a plataforma tem um dado nunca foi o
mesmo que saber onde ele está: quem procurava "dados de câncer" não tinha como
adivinhar que a resposta mora nos grupos `AQ` e `AR` do SIA, nos grupos `CC` e
`CM` do SISCAN, e num recorte de CID aplicado sobre SIH e SIM. Essa receita
vivia na cabeça de quem já conhece o DATASUS, e era essa barreira, não a
ausência do dado, que mantinha a base inacessível na prática.

Entram duas camadas, com responsabilidades distintas:

- **Temas** (`guaraci/services/themes.py`): vinte etiquetas que respondem
  "onde tem dado desse assunto?". Todas as 109 fontes estão classificadas, e
  uma fonte pode ter mais de um tema, porque é assim que o dado se comporta: o
  SIM responde tanto a `mortalidade` quanto a `oncologia`. A classificação
  fica num mapa central, não espalhada pelos dez módulos de
  `services/sources/`, e é acoplada ao `SourceDescriptor` na leitura. As
  famílias geradas pelo Swagger DEMAS (`sisagua_*`, `saude_indigena_*`,
  `atencao_primaria_*`) caem em regras de prefixo, para que o arquivo não
  nasça desatualizado.
- **Presets** (`guaraci/services/presets.py`): a resposta à pergunta seguinte,
  "com quais parâmetros eu puxo isso?". Um preset é uma receita nomeada que
  atravessa fontes, fixando os parâmetros de cada passo. Nascem dois,
  `oncologia` e `nascimentos`.

O preset `oncologia` cobre o percurso do paciente pelos sistemas do SUS, na
ordem em que ele acontece: rastreamento (SISCAN, grupos `CC` e `CM`),
tratamento ambulatorial de alta complexidade (SIA, grupos `AQ` e `AR`),
consolidado nacional (Painel de Oncologia), internação (SIH) e óbito (SIM). O
recorte do SIA é o caso exemplar do problema: o padrão da fonte é o grupo `PA`,
que não traz APAC nenhuma, então o dado de quimioterapia e radioterapia estava
lá desde 1994 sem que nada no catálogo indicasse o caminho.

Cada passo declara em qual fase o recorte acontece. SISCAN e SIA saem prontos
da coleta; SIH e SIM vêm inteiros, porque o FTP do DATASUS não filtra CID na
origem, e o campo `refine` diz exatamente qual coluna filtrar depois
(`DIAG_PRINC` e `CAUSABAS`, CID-10 C00-C97). Um preset que escondesse essa
distinção entregaria um recorte que o usuário acha pronto e não está.

O preset também declara o que **não** tem: não há dado de incidência. No
Brasil, incidência de câncer vem dos Registros de Câncer de Base Populacional
do INCA, publicados apenas em relatório e tabulador, sem via automatizável que
atenda ao critério de fonte primária do projeto (princípio 20 do
`vogel-stack`). A ausência está em `caveats`, não implícita no silêncio.

Superfícies novas:

- `GET /themes`, `GET /presets` e `GET /presets/{name}` na API;
- `GET /sources` ganha o campo `themes` e o filtro `?theme=<slug>`; um slug
  desconhecido responde 400, em vez de devolver lista vazia;
- `GET /sources/{source}/schema` ganha `themes`;
- `guaraci fetch themes`, `guaraci fetch presets`, `guaraci fetch preset NOME`
  e `guaraci fetch list --theme <slug>` no CLI;
- na interface web, a busca do catálogo passa a casar tema por slug, rótulo e
  descrição, e os cartões mostram os temas da fonte. Casar contra a descrição
  é o que faz "câncer" encontrar o tema cujo rótulo é "Oncologia".

A leitura de `GET /presets/{name}` valida os parâmetros de cada passo contra o
schema vivo da fonte. Um preset é código que descreve parâmetros de terceiros,
então envelhece mal por conta própria; validar na leitura faz a receita
desatualizada falhar ali, e não no meio de um download longo.

Nenhuma fonte foi adicionada, removida ou alterada, e nenhum parâmetro mudou de
nome ou de default. O campo `themes` é aditivo em toda resposta onde aparece.

## [0.7.0] - 2026-09-10

### Removed: backend PySUS, encerrando a migração para o FTP direto
A 0.6.0 tornou a conexão direta ao `ftp.datasus.gov.br` o padrão de SIH, SIM e
SINAN, e manteve o PySUS alcançável por uma release para facilitar o retorno,
conforme registrado no próprio `pyproject.toml`. Essa release passou. Saem:

- o extra `datasus-legacy` e, com ele, o pacote `pysus`;
- a variável `GUARACI_DATASUS_BACKEND` e o módulo `guaraci/datasus/backend.py`,
  que existia só para escolher entre os dois caminhos;
- os ramos `_download_via_pysus` e `_discover_via_pysus` de SIH, SIM e SINAN,
  junto com os guardas `PYSUS_AVAILABLE` e as propriedades `sih`/`sim`/`sinan`
  que só serviam para levantar `ImportError`.

As 109 fontes continuam as mesmas: o que sai é um caminho interno alternativo,
não uma base. SIH, SIM e SINAN seguem coletando pelo FTP direto, que é o que
já faziam por padrão desde a 0.6.0.

Três consequências que valem registro:

- **O teto `loguru<0.7.0` some do resolvedor.** Ele era exigência do PySUS, que
  ainda hoje, na versão 2.11.2, pede `loguru<0.7.0`, `numpy>=2.4.0` e
  `pandas<3.0.0`. Sem ele, a instalação padrão resolve loguru 0.7.3 e não
  impõe teto de pandas a ninguém.
- **A imagem Docker perde as dependências transitivas do PySUS**, cerca de
  vinte pacotes que nenhum caminho ativo importava.
- **`pip install "guaraci[full]"` deixa de arrastar o backend legado.**

### Changed: identificadores públicos deixam de citar a dependência que saiu
O nome da biblioteca aparecia em lugares que o usuário lê. O modo publicado de
`sinan`, `sim` e `sih` era `pysus ftp`, o que anunciava um backend inexistente
e ainda separava as três fontes das outras onze do DATASUS, que já usavam
`datasus ftp`. As catorze passam a compartilhar `datasus ftp`, no catálogo, na
API, no site e na interface web.

Internamente, `PysusDownloadSource` vira `DatasusDownloadSource` (o adaptador
nunca teve nada de PySUS dentro: é o adaptador comum das catorze fontes) e
`guaraci/services/sources/datasus_pysus.py` vira `datasus_curated.py`, que é o
que o módulo sempre foi, as specs curadas à mão de SINAN, SIM e SIH.

Os testes `test_sih_backend_switch.py`, `test_sim_backend_switch.py` e
`test_sinan_backend_switch.py` passam a se chamar `test_*_ftp_path.py`: sem
dois backends, não há chave para testar, e o que resta é a cobertura do
caminho de coleta. Saíram `test_pysus.py`, `test_optional_pysus.py`,
`test_datasus_backend.py`, `test_sih_datasource.py` e
`test_sinan_datasource.py`, que exercitavam apenas o caminho removido. A suíte
fica com 964 testes, todos passando.

### Changed: a versão deixa de estar copiada no User-Agent de sete arquivos
`"guaraci/0.6.0"` estava escrito à mão em dez pontos de sete clientes HTTP
(ANA, IBGE, INMET, INPE, NASA, OpenDataSUS e o portal de arquivos), de modo que
cada release exigia lembrar de todos. Agora derivam de `guaraci.__version__`,
que já era a fonte única declarada no `pyproject.toml`.

### Fixed: quatro defeitos na declaração de dependências
Auditoria dos pacotes importados pelo código contra os declarados no
`pyproject.toml`, com a suíte completa rodada em três ambientes: um venv limpo
sem PySUS, um venv com o extra legado e o ambiente de trabalho do repositório.

- **`loguru` estava com teto `<0.7.0` no núcleo.** A restrição não era nossa:
  vinha do PySUS, dependência opcional do extra `datasus-legacy`, e por estar
  no núcleo travava todo mundo em 0.6.0 e conflitava com qualquer pacote que
  pedisse loguru 0.7 ao lado do Guaraci. O teto saiu, e o piso continua baixo
  de propósito: a instalação padrão resolve 0.7.3, e quem mantiver o PySUS no
  mesmo ambiente por outra razão ainda consegue instalar, porque o PySUS
  prende loguru em 0.6.x. Verificado: a suíte passa nas duas versões, então
  exigir 0.7 excluiria gente sem ganho nenhum.
- **`polars>=0.20.0` era um piso falso.** O código chama `collect_schema()` em
  cinco pontos (`datasus/filtering.py`, `datasus/frames.py`,
  `datasus/sinan.py`), método que só existe a partir do polars 1.0. Quem
  resolvesse para 0.20 instalava sem erro e quebrava em execução. O piso passa
  a `>=1.0.0`.
- **`nest_asyncio` e `numpy` eram usados sem estar declarados.** O primeiro é
  importado em `datasus/ftp/orchestration.py`, no caminho FTP padrão, para
  rodar dentro de um laço de eventos já ativo, o que é o caso de qualquer
  notebook; o segundo é import de topo em `utils/mapping.py` e só funcionava
  de carona no pandas. Ambos agora constam do núcleo.
- **`pandas>=1.5.0` não refletia nada testado.** Uma instalação limpa hoje já
  traz pandas 3.0.5, numpy 2.5.3, polars 1.44.1 e pyarrow 25, combinação que
  nunca havia sido exercitada. Foi, e passa inteira. O piso vai para `>=2.0.0`.

O link `Documentation` do pacote apontava para `guaraci.readthedocs.io`, que
responde 404 e aparece assim na página do PyPI. Passa a apontar para a
documentação publicada em `autoaihub.github.io/guaraci/docs.html`.

### Changed: a matriz vai até o Python mais recente que existe, e a imagem larga os extras legados
O CI passa a cobrir 3.11, 3.12, 3.13 e 3.14, e o job de empacotamento constrói
em 3.13. A imagem Docker sai de `python:3.11-slim` para `python:3.13-slim`.

A 3.14, lançada em outubro de 2025, é a estável mais recente do Python, e o
que impedia de testá-la era o PySUS, que declara `requires-python <3.14`.
Removido o backend legado, a suíte roda inteira nela: verificado em PR próprio
antes de entrar aqui, com os quatro jobs verdes. Todas as dependências
binárias (polars, pyarrow, pydantic-core) já publicam roda para 3.14.

A imagem instalava `.[full]`, que arrasta o PySUS e o stack Google do BigQuery,
cerca de trinta pacotes que nenhum caminho padrão importa e que impõem o teto
de loguru e de pandas descrito acima. Passa a instalar `.[datasus,api,dev]`:
o backend FTP direto, a API web e as ferramentas de teste que o `README.md`
manda executar de dentro do contêiner. Os extras legados seguem instaláveis
por quem precisar deles.

### Fixed: instalação nova imprimia três alarmes falsos sobre o PySUS
Importar o pacote sem a dependência opcional escrevia
`PySUS não está disponível ou falhou ao importar` uma vez por módulo que a
importa (`sih`, `sim`, `sinan`), inclusive ao subir a API. Como o backend
padrão é o FTP direto desde a 0.6.0, a ausência do PySUS é o caso comum e não
um defeito, de modo que o aviso classificava como problema aquilo que é a
instalação recomendada. O registro cai para nível de depuração; quem pede o
backend legado continua recebendo o erro explícito na hora de usá-lo. Na mesma
passagem, `datasus/sim.py` ganhou os símbolos `pysus`/`PySUS` definidos no
ramo de falha, que faltavam ali pelo mesmo motivo já corrigido em `sinan.py`.

### Fixed: README apontava para dois documentos que não existem
`docs/DOCKER_WORKFLOW.md` e `docs/INSTALL.md` estão referenciados na porta de
entrada do repositório e nunca foram versionados, sendo o segundo justamente o
link de instalação. Os dois passam a apontar para `docs/quickstart.md`, que
cobre instalação e operação por Docker. Uma varredura dos links internos de
todos os arquivos Markdown do repositório não encontrou outros quebrados.

### Added: instalação por pip documentada, sem Docker
O README classificava a execução fora do Docker como trabalho em andamento e
não trazia nenhuma linha de `pip install`. Verificado de ponta a ponta num venv
limpo no Windows: a CLI lista as 109 fontes, a API sobe com as 21 rotas e a
suíte roda. A seção nova traz o comando com os extras e o aviso de que o
release publicado no PyPI ainda está na `0.3.2`, três versões menores atrás do
repositório, o que torna `pip install guaraci` uma armadilha até a próxima
publicação. A instalação recomendada é a partir do git.

### Fixed: `guaraci --help` quebrava no Windows fora de um terminal UTF-8
`sys.stdout` assume a codificação do console (cp1252 por padrão no Windows)
sempre que não está ligado a um terminal UTF-8, o que inclui qualquer
redirecionamento para arquivo ou cano. Como a ajuda traz acentos e a bandeira
na descrição do grupo, `guaraci --help | more` e `guaraci --help > ajuda.txt`
terminavam em `UnicodeEncodeError` antes de imprimir qualquer coisa útil, o
mesmo valendo para a ajuda de cada subcomando. A entrada da CLI passa a
reconfigurar a saída para UTF-8 com `errors="replace"`, o que mantém o texto
legível mesmo num console que não dê conta de algum caractere.

### Changed: fonte FTP sem arquivos no período explica a cobertura publicada
Vários sistemas do DATASUS foram descontinuados, e pedir um ano fora da série
devolvia zero arquivos sem motivo, indistinguível de uma falha de coleta. A
descoberta genérica agora lista os anos que a origem publica quando o resultado
sai vazio e devolve o intervalo real no campo `warnings` do resumo. Verificado
ao vivo: CIH publica de 2008 a 2011, SISCAN de 2006 a 2015 e SISPRENATAL de
2012 a 2014, e as fontes com dados no período seguem sem aviso. O intervalo é
lido da origem a cada consulta, e não fixado no código, para não envelhecer.

### Fixed: duas fontes OpenDataSUS estavam inalcançáveis por defeito nosso
Varredura ao vivo das 51 fontes DEMAS registradas (`scripts/smoke_opendatasus_
sources.py`): 42 respondiam, 6 falhavam e 3 dependem de parâmetro de caminho.
Duas das falhas eram defeito do catálogo, e foram corrigidas.

- `prevencao_e_promocao_distribuicao_epi_insumo` apontava para
  `/prevencao-e-promocao/distribuicao_epi_insumo`, com underscore no último
  segmento, e recebia 404. A origem serve `distribuicao-epi-insumo`, com
  hífen; confirmado ao vivo, a fonte agora coleta e exporta normalmente.
- `sindrome_gripal_leve` monta um endpoint por ano (`...-2024`) e pedia
  qualquer ano do intervalo sem consultar a cobertura publicada, terminando
  num 404 opaco. A série vai de 2020 a 2024: anos fora dela são ignorados
  quando o intervalo é mais largo, e um pedido inteiramente fora agora falha
  dizendo qual é a cobertura disponível.

As outras quatro falhas foram investigadas contra o swagger publicado pela
origem e estão tratadas na entrada seguinte.

### Fixed: o orquestrador deixava um diretório de trabalho por unidade coletada
Cada unidade materializada por serviço baixa para `.staging/<run>/<chave>` e
move dali o CSV para a árvore bronze, mas o diretório nunca era removido: o
manifesto e os formatos intermediários ficavam para trás. Uma varredura das 109
fontes deixava 109 diretórios, a cada execução, e o custo crescia com a
frequência do agendamento. A limpeza agora cobre todos os caminhos de saída,
inclusive o de resultado vazio e o de erro, e nunca derruba a coleta.

Verificado no mesmo ciclo que a API HTTP responde como deve: `/sources` lista
as 109 fontes, um intervalo de anos invertido e a falta do filtro obrigatório
do bps voltam como 400 com a mensagem da validação (e não como 500), e um job
real vai de `queued` a `completed`.

### Fixed: a fonte SNIS não coletava nada, e o SINISA abortava por um `.rar`
Varredura ao vivo das fontes que não são da API DEMAS, pelo mesmo caminho do
usuário (`scripts/smoke_non_demas_sources.py`). Três defeitos no crawl de
saneamento no portal do Ministério das Cidades:

- **O SNIS falhava sempre**, inclusive nos parâmetros padrão, com "No SNIS
  files matched the requested filters". A página de diagnósticos anteriores
  que ele raspava saiu do ar sem responder 404: devolve 200 com o layout padrão
  do gov.br e nenhum link de arquivo. Os arquivos passaram para a página de
  produtos, e a fonte volta a encontrar 11 documentos, entre planilhas de água
  e esgoto, resíduos sólidos e águas pluviais de 2022, glossários e atestados.
- **O menu lateral do portal entrava no resultado.** Ele repete arquivos de
  outros programas em toda página, e três planilhas de barragens e emendas
  parlamentares apareciam como se fossem dados de saneamento. Cada fonte passa
  a aceitar apenas o que está sob o seu próprio caminho: dos 52 documentos que
  o crawl do SINISA alcança, 47 estão sob `/saneamento/sinisa/` e os cinco
  restantes são justamente os do menu.
- **Um `.rar` derrubava a coleta inteira do SINISA.** O formato não era
  reconhecido como documento, então o crawler o buscava como se fosse página, e
  o `HTMLParser` da biblioteca padrão levantava `AssertionError` sobre os bytes
  binários, o que nenhum `except` no caminho previa. Reconhecer a extensão
  resolve os dois lados: as planilhas de resíduos e de águas pluviais de 2023,
  publicadas em `.rar`, deixam de ser ignoradas e não são mais abertas como
  HTML. A leitura de página ilegível passa a descartar só aquela página.

O restante da varredura não achou defeito: IBGE (9 de 11 coletando, e as duas
restantes pedem anos que a origem não publica), INPE Queimadas, NASA POWER e
INMET respondem; ANA, NASA FIRMS e NASA GPM pedem credencial e dizem qual
variável de ambiente configurar.

### Changed: resultado vazio do IBGE diz quais anos a tabela publica
As séries do SIDRA têm buracos que não são falha de coleta: a tabela 6579, de
população estimada, não publica 2007, 2010, 2022 nem 2023. Pedir um desses anos
devolvia zero linhas com um "IBGE returned no rows" que não distinguia origem
sem dado de erro nosso. O aviso agora nomeia os anos pedidos que faltam e lista
os disponíveis, no mesmo espírito do que já era feito para as fontes FTP.

### Fixed: recorte por UF era aceito e ignorado, e o resultado saía como recorte
`cadastro-vinculado-programa-previne-brasil` responde 200 a qualquer valor de
UF, sob qualquer um dos nomes de parâmetro que declara, e devolve sempre as
mesmas linhas. Pela CLI, um pedido de SP trazia 200 registros de 11 unidades da
federação, apresentados como o recorte pedido. Duas causas somadas: o nome do
parâmetro dessa família (`sigla_unidade_federacao`) não constava da lista de
nomes de UF reconhecidos, de modo que um `uf=SP` nem chegava a ser enviado à
origem, e o recorte não era reconferido nas linhas devolvidas.

O recorte agora viaja sob o nome que o endpoint publica e é reconferido no
retorno, com uma guarda para os casos em que a conferência não é possível: se
as linhas não trazem uma sigla reconhecível, nada é descartado (filtrar
apagaria tudo em vez de recortar) e o resultado sai com um aviso de que a
origem pode ter ignorado o filtro. O mesmo pedido agora devolve 96 linhas,
todas de SP.

### Added: catálogo passa de 99 para 109 fontes, sincronizado com a origem
O snapshot local do swagger tinha 79 caminhos contra os 87 publicados. A
sincronização traz 12 endpoints novos e remove quatro que a origem retirou
(`/plataformabr/projetos`, sua variante por CAAE e as duas rotas de
autenticação, que nunca foram fonte de dados). Verificado ao vivo em
2026-09-03, endpoint a endpoint:

- **Seis coletam e exportam**, conferidos ponta a ponta pela CLI:
  `arboviroses_febre_amarela_epzootias`, `saude_indigena_sesai_atendimentos`,
  `saude_indigena_sesai_recursos_humanos` e três do módulo PMMB Especialista.
- **Quatro respondem 200 sem publicar linha alguma**, inclusive com filtros:
  os dois sucessores da Plataforma Brasil, `pmmb_especialista_consolidado` e
  `pmmb_relatorio_historico_cadastro_cnes`.
- **Dois respondem 500 na origem**: `ouvidoria_ouvidor2` e `ouvidoria_ouvidor3`.

Os seis últimos ficam registrados assim mesmo, porque o catálogo espelha o que
a origem publica: quando ela passar a responder, funcionam sem mudança nossa.

As arboviroses (dengue, zika, chikungunya) ganharam o filtro `id_municip`, que
a origem passou a aceitar, o que permite recortar por município sem baixar a
unidade da federação inteira.

Dois identificadores deixam de carregar as chaves do parâmetro de caminho:
`cnes_estabelecimentos_{codigo_cnes}` obrigava o usuário a escapar o nome no
shell, onde as chaves são sintaxe de expansão, e passa a ser
`cnes_estabelecimentos_por_codigo_cnes`.

### Fixed: duas fontes do PMMB tinham migrado e o bps paginava errado
A comparação do swagger local com o publicado em
`apidadosabertos.saude.gov.br/static/swagger.json` mostrou que as quatro
falhas restantes tinham três causas distintas, e não uma remoção genérica.

- **`atencao_primaria_pmmb` e `atencao_primaria_pmmb_profissionais_ativos`
  migraram.** A origem renomeou os endpoints para `pmmb-consolidado` e
  `pmmb-relacao-nominal-ativo`, com os mesmos parâmetros de cada um
  (`pmmb-relacao-nominal-ativo` mantém `uf`, `sexo` e `nacionalidade`). Os
  dois voltam a coletar. Como o identificador da fonte é derivado do caminho,
  as fontes passam a se chamar `atencao_primaria_pmmb_consolidado` e
  `atencao_primaria_pmmb_relacao_nominal_ativo`.
- **`economia_da_saude_bps` não estava só sem um parâmetro.** O endpoint
  existe, mas é o único dos 87 publicados que pagina por número de página, e
  ignora `limit`/`offset` em silêncio: verificado ao vivo, `limit=3` e
  `limit=3&offset=3` devolvem as mesmas 100 linhas, enquanto `pagina=2` avança.
  Paginado como os outros, ele renderia a mesma página repetida até esgotar
  `max_pages`, produzindo duplicatas em massa sem nenhum erro visível. Novo
  `guaraci/opendatasus/demas_quirks.py` concentra o esquema de paginação por
  endpoint e a exigência de trazer `codigoCatmat` ou `cnpjInstituicao`, que
  agora falha antes da primeira requisição em vez de virar um 400 da origem
  sem identificação da fonte. O swagger local desse caminho declarava
  `limit`/`offset`, que o endpoint sequer aceita, e foi sincronizado com os 21
  filtros reais.
- **`plataformabr_projetos` foi removida mesmo.** O grupo `/plataformabr`
  inteiro deixou de existir no swagger da origem, sem endpoint sucessor.

O snapshot local do swagger tem 79 caminhos contra 87 publicados, de modo que
há oito endpoints novos ainda não avaliados para inclusão no catálogo.

### Fixed: exportação sqlite apontava para um arquivo inexistente e materializava tudo
O formato `sqlite` é uma das três opções que a CLI oferece, e era o único
caminho de exportação nunca medido sob volume. Dois defeitos independentes:

- **O caminho devolvido não existia.** `write_frame` gravava `{stem}.db` e
  devolvia `{stem}.sqlite`, de modo que o manifesto e o `OK - wrote 1 file(s)`
  da CLI anunciavam um arquivo que o usuário não encontrava em disco. Valia
  para SIM e SIH, que usam `write_frame`, e para o SINAN, que duplicava o
  mesmo trecho.
- **A escrita passava por `to_pandas()` sobre o conjunto inteiro**, o que faz
  as colunas de texto virarem objetos Python. Medido sobre 4 milhões de linhas
  e 10 colunas, num processo que só executa a exportação: pico de 3195 MB
  acima da linha de base, contra 716 MB do parquet equivalente, crescendo com
  o número de linhas e de colunas. Um extrato anual do SINAN tem mais de cem
  colunas. A escrita agora vai em lotes de 50 mil linhas, e o mesmo caso cai
  para 1074 MB e fica um pouco mais rápido (15,4 s contra 18,1 s). O SINAN
  deixa de duplicar o trecho e passa a usar `frames.write_sqlite`.

A medição é reproduzível por `scripts/bench_sqlite_export.py`.

### Fixed: `--format sqlite` era inutilizável nas fontes de arquivo em lote
As 15 fontes que baixam arquivos inteiros (SRAG e as 14 do SISAGUA) abortavam
com `ProgrammingError: type 'decimal.Decimal' is not supported` sempre que se
pedia `sqlite`. Colunas `Decimal` do parquet viram `decimal.Decimal` na
passagem por pandas, e o driver não tem adaptador para esse tipo: os bancos
anuais da SRAG trazem 21 colunas assim, de modo que o formato nunca funcionou
nessa família. A conversão agora é explícita, já que o SQLite não tem tipo
decimal nativo: escala zero vira inteiro, que é exato, e escala maior vira
ponto flutuante. Verificado com o arquivo real de 2025 (336 mil linhas por 194
colunas), que passa a exportar 242 MB de banco.

Trocar a leitura desses arquivos por `scan`/`sink` foi medido e **não**
compensa, então o caminho de csv e parquet segue eager: os parquet da origem
vêm num único row group, abaixo do qual não há streaming possível, e para o
CSV de 288 MB da SRAG de 2024 o caminho lazy custou 832 MB de pico contra
689 MB do eager. Só a exportação sqlite usa o plano lazy, porque ali a escrita
consome o frame em lotes (1403 MB contra 1711 MB).

### Changed: os seis caminhos de exportação sqlite passam pelo mesmo escritor
ANA, IBGE SIDRA, INMET e o backend FTP genérico do DATASUS repetiam cada um o
seu `to_pandas().to_sql()` sobre o conjunto inteiro, o que os deixava sujeitos
aos dois defeitos acima sem que nenhum teste cobrisse isso. Todos passam agora
por `frames.write_sqlite`, herdando a escrita em lotes e a conversão de tipos.
Cada um preserva a extensão que já usava (`.sqlite` nos três primeiros, `.db`
no DATASUS) e passa a falhar de forma explícita em vez de devolver um caminho
sem arquivo quando não há linha alguma.

### Fixed: gravação de `jobs.json` abortava de forma intermitente no Windows
`os.replace` é atômico, mas no Windows falha com `PermissionError` enquanto
qualquer outro processo mantém um handle sobre o destino, ainda que só para
leitura, o que indexador de busca e antivírus fazem por alguns milissegundos.
O efeito era a persistência de jobs da API abortando sem regularidade, com o
trabalho registrado em memória e perdido em disco. Novo
`guaraci/utils/atomic_io.py` refaz a troca até cinco vezes com espera
crescente, cobrindo cerca de 150 ms, e ainda propaga o erro se o bloqueio não
for transitório. Aplicado também à escrita do dicionário de campos, que usava
o mesmo padrão.

### Fixed: coletas do OpenDataSUS estouravam a memória e truncavam em silêncio
A família DEMAS reúne 51 das 99 fontes e é o outro caminho de coleta longa da
plataforma. Medições contra `/arboviroses/dengue`, que tem mais de 4 milhões de
registros só em 2024, mostraram que ela repetia os dois problemas já corrigidos
no DATASUS, por motivos próprios.

- **Registros acumulados em memória.** As páginas eram juntadas numa lista de
  dicionários e só viravam DataFrame no fim. Cada registro custa cerca de 11 KB
  nessa forma, o que projeta cerca de 45 GB para um ano completo: a coleta
  morria por falta de memória depois de horas, sem deixar nada aproveitável.
  Novo `guaraci/opendatasus/buffer.py`: até 5000 registros tudo segue em
  memória, como antes; acima disso a coleta passa a gravar partes parquet e o
  arquivo final é escrito por streaming. Medido sobre 60 000 registros, o pico
  cai de 1696 MB para 593 MB com 12% a mais de tempo. O limiar foi escolhido
  pela curva: 1000 chega a 497 MB, mas custa 47% a mais de tempo.
- **Truncamento reportado como sucesso.** Com `max_pages=250` e
  `batch_size=1000`, o default para em 250 000 registros, cerca de 6% do ano de
  dengue. O aviso de truncamento existia apenas dentro do manifesto em disco, e
  o resultado entregue à CLI e à API dizia `status: success` com
  `warnings: None`. Agora `warnings` e `truncated` acompanham o payload,
  `JobResult` expõe as duas informações, uma coleta truncada passa a valer
  `partial_success`, o `fetch` imprime cada aviso e sai diferente de zero, e o
  serviço de jobs registra os avisos como eventos em vez de anunciar conclusão
  limpa.
- Os recortes por `start_date`, `end_date` e `uf` são **locais**: os endpoints
  DEMAS aceitam apenas `nu_ano`, `limit` e `offset`, então pedir um mês custa a
  mesma varredura que pedir o ano. Isso agora está documentado em
  `docs/SOURCES_AND_FILTERS.md` §3.4, junto do ritmo observado (cerca de 200
  registros por segundo, o que dá cerca de 5 horas para um ano de dengue).

### Fixed: intervalos e datas impossíveis passavam pela validação
Levantamento sobre as 99 fontes: 37 aceitavam `start_year` maior que
`end_year`, 10 aceitavam ano negativo e 10 aceitavam datas como `31/12/2024` ou
`2024-02-30`. A validação existente olhava um parâmetro por vez e não enxergava
relações entre eles, então o pedido só falhava adiante, com a coleta em
andamento, ou era ignorado pela origem, que devolvia o conjunto inteiro no
lugar do recorte pedido. `validate_param_relationships` em
`guaraci/core/contracts.py` passa a checar ordem e limites de anos e datas para
toda fonte, antes de qualquer acesso à rede.

### Fixed: filtros de refinamento de SIH, SIM e SINAN devolviam o conjunto errado
Varredura sistemática dos filtros contra microdados reais (dengue nacional
2014-2024, SIM CID10 AC 2020, SIH RD AC 2023-01). Dos sete filtros oferecidos,
a maioria estava quebrada, e três falhavam em silêncio, entregando dado errado
sem mensagem alguma. A lógica comum foi extraída para
`guaraci/datasus/filtering.py` e `guaraci/datasus/frames.py`, que os três
sistemas passam a compartilhar.

- **`--uf` no SINAN devolvia 2% dos casos.** A coluna era escolhida pela
  primeira que existisse no arquivo, e o SINAN traz `UF` presente porém vazia
  em 96% dos registros (16 822 362 de 17 281 884), enquanto `SG_UF_NOT` está
  completa. Filtrar dengue por São Paulo rendia 103 059 de 5 047 004 casos.
  `resolve_filter_column` agora pula as colunas sem dado, respeitando a ordem
  de preferência entre as que têm.
- **`--uf` no SIM era descartado sem aviso.** Nenhuma das colunas candidatas
  (`UF`, `UF_RES`, `UFRES`, `CODUFRES`) existe nos arquivos: quem pedia um
  estado recebia o país inteiro. A UF vive nos dois primeiros dígitos de
  `CODMUNRES`, que `uf_expr` passa a ler.
- **`--uf` no SIH nunca casava.** `UF_ZI` guarda o código do gestor
  (`120000`), comparado contra a sigla `SP`. `uf_expr` reconhece as três
  representações: sigla, código IBGE de dois dígitos e código de seis dígitos
  de município ou gestor, e aceita que a pessoa informe qualquer uma delas.
- **`--faixa-etaria` e `--ano` morriam com `ComputeError`.** O valor chega da
  interface como texto ou inteiro, sem relação com o tipo inferido do DBF
  (`NU_IDADE_N` é Int64, `NU_ANO` é texto). A comparação passa a ser numérica
  quando os dois lados são números, o que também resolve o zero à esquerda de
  `MES_CMPT` (`--mes 1` contra `"01"`).
- **`--sexo M/F` não casava nada em SIM nem em SIH.** Os dois gravam o campo
  como código, e com codificações diferentes: 1/2 no SIM e 1/3 no SIH, herança
  do layout da AIH. A tradução vive em `SEXO_CODES` de cada datasource.
- **`--ano-obito` no SIM sempre devolvia vazio.** Sem `ANOOBITO` no arquivo, o
  código caía em `DTOBITO` e recortava `slice(0, 4)`, mas o campo é `DDMMAAAA`:
  comparava "2205" com 2020. Passa a ler os quatro últimos dígitos.

### Fixed: colunas de dados clínicos e administrativos eram zeradas no export
A normalização de UF selecionava colunas pelo nome, com um `"UF" in nome` que
varria junto campos sem relação com unidade federativa. Como o valor deles não
corresponde a nenhuma UF, a coluna inteira era substituída por nulo e o dado
sumia do arquivo entregue. Confirmado em `UF_ZI` no SIH (código do gestor) e
`GRAV_INSUF` no SINAN (gravidade e insuficiência clínica). `uf_normalization_
expr` agora amostra a coluna e só a reescreve quando ela de fato carrega UFs;
caso contrário devolve o dado intacto. `SG_UF_NOT`, `SG_UF`, `UF` e `COUFINF`
seguem normalizadas para a sigla, como antes.

### Changed: SIM e SIH ganham o mesmo caminho de memória já aplicado ao SINAN
`scan_dataframe()` lazy, `export()` aceitando `LazyFrame` com escrita em
streaming e carga compartilhada em `guaraci/datasus/frames.py`, no lugar das
três cópias de `_load_as_polars` que liam todos os anos para um
`pl.concat(how="diagonal")` em memória. Os CLIs de sih e sim e o
`DownloadService` passam a usar esse caminho.

### Fixed: coletas longas do DATASUS terminavam em nada (dengue, SINAN)
Relato de usuário: quase uma hora de execução para baixar dengue, seguida de
falha sem dado nenhum. Reproduzido com `sinan download 2014 2024 -d DENG`
(11 arquivos, 757 MB no FTP), que expôs três defeitos independentes.

- **Dependência de decodificação verificada tarde demais.** `pyreaddbc` vem
  do extra opcional `guaraci[datasus]` e só era importado dentro de
  `dbc.read`, isto é, depois de cada arquivo já ter sido transferido. Como
  `download_records` (`guaraci/datasus/ftp/orchestration.py`) capturava
  `Exception` genérica, a falta da biblioteca era contabilizada como falha
  daquele arquivo e o laço seguia baixando os 757 MB restantes para
  descartar tudo. Adicionados `dbc.ensure_available()`, chamado antes do
  primeiro download, e `DbcDependencyError` (subclasse de `ImportError`),
  com o laço reerguendo `ImportError` em vez de tratá-lo como falha
  isolada. Medido: a execução passa de uma hora com 757 MB baixados e
  descartados para 3 segundos, saída 1, mensagem acionável e zero bytes
  transferidos. Vale para SIH, SIM, SINAN e as 11 fontes FTP genéricas,
  que compartilham a mesma orquestração.
- **Pico de memória proporcional ao arquivo inteiro.** `dbc.read`
  materializava todos os chunks e os concatenava, e `SinanDataSource.
  _load_as_polars` lia os parquets de todos os anos para um
  `pl.concat(how="diagonal")`. Um único ano de dengue (DENGBR24, 287 MB
  comprimidos) foi medido em 8,8 GB residentes e crescendo, com 15 minutos
  sem concluir; o concat dos 11 anos nem chegava a acontecer. Novo
  `dbc.decode_to_parquet` escreve cada chunk como parte e faz a junção com
  `pl.concat(..., how="diagonal_relaxed").sink_parquet()`, sem materializar
  o conjunto. `SinanDataSource.scan_dataframe()` devolve o plano lazy,
  `export()` aceita `LazyFrame` e usa `sink_parquet`/`sink_csv`, e CLI e
  `DownloadService` passaram a usar esse caminho quando disponível. A
  execução completa de 2014-2024 agora conclui em 38 minutos com os 11
  anos, 17 281 884 registros e 121 colunas.
- **Sucesso parcial reportado como sucesso.** Com 10 dos 11 anos perdidos, o
  CLI imprimia `SUCCESS ... completed successfully!` e saía com 0, de modo
  que qualquer script a jusante lia a execução como boa; o único sinal era
  um aviso no meio do log e o sufixo `_partial` no arquivo. Novo
  `raise_if_downloads_failed` em `guaraci/cli/_common.py`, aplicado aos três
  CLIs (sih, sim, sinan), faz a falha parcial sair diferente de zero sem
  suprimir o payload JSON do que foi obtido.

Ajustes de apoio na mesma correção:

- `_CHUNK_ROWS` de `dbc` passou de 100 000 para 10 000. Pico medido sobre
  DENGBR23.dbc (62 MB comprimidos), com o tempo estável em 180-200 s nas
  quatro configurações: 100k custa 2815 MB, 25k custa 1408 MB, 10k custa
  960 MB e 5k custa 878 MB, ou seja, o ganho satura perto de 10k.
- A junção das partes usa `diagonal_relaxed` porque um `scan_parquet` sobre
  a lista exigiria schema idêntico entre elas, o que não ocorre: `DT_GRAV`
  é inferida como `Null` num chunk e como `Date` no seguinte. Sem isso a
  junção caía no fallback em memória e o pico voltava a acompanhar o
  arquivo inteiro (1400 MB em streaming contra 4114 MB no fallback).
- `SinanDataSource._apply_uf_mapping` trocou o `map_elements` com callback
  Python, que executava `import pandas` e `pd.isna` uma vez por linha, por
  expressão nativa com `replace_strict`.
- Combinando as duas medidas, o pico de decodificação de um arquivo caiu de
  5091 MB para 960 MB. A saída foi verificada idêntica em conteúdo e schema
  à produzida antes das mudanças (DENGBR17 e DENGBR18, 121 colunas).
- Testes novos em `tests/test_ftp_failfast_and_streaming.py`,
  `tests/test_sinan_lazy_export.py` e `tests/test_cli_exit_codes.py`
  (suíte: 804 → 833).

### Added: 5 fontes IBGE novas (registro civil e saneamento domiciliar, Censo 2022)
- `ibge_casamentos` (SIDRA tabela 4406, variável 4993): casamentos por mês do
  registro, fechando a série de registro civil ao lado de
  `ibge_nascidos_vivos_rc` e `ibge_obitos_rc`. Período anual 2013-2024,
  confirmado ao vivo. Referência: Brasil, 2023, mes=total, 940 799
  casamentos.
- `ibge_divorcios` (SIDRA tabela 5937, variável 231): divórcios concedidos
  em 1ª instância. Período anual 2014-2024, confirmado ao vivo. Referência:
  Brasil, 2023, todas as classificações em total, 360 787 divórcios.
- `ibge_saneamento_agua` (tabela 6803), `ibge_saneamento_esgoto` (tabela
  6805) e `ibge_saneamento_lixo` (tabela 6892): domicílios particulares
  permanentes ocupados por forma de abastecimento de água, tipo de
  esgotamento sanitário e destino do lixo, do Censo 2022 (período único
  2022, confirmado ao vivo). Camada de determinante social que casa com as
  14 fontes SISAGUA já integradas. Referência comum, Brasil 2022, detalhe
  total: 72 456 368 domicílios.
- Todas as cinco seguem o padrão de guarda combinatória já usado em
  `ibge_nascidos_vivos_rc`/`ibge_obitos_rc`: SIDRA rejeita (HTTP 500) o
  cruzamento de nível municipal com a classificação completa em
  `ibge_casamentos` (mês), `ibge_divorcios` (idade/tempo) e
  `ibge_saneamento_agua`/`ibge_saneamento_esgoto` (categorias), confirmado
  ao vivo; a exceção é `ibge_saneamento_lixo`, cujas 8 categorias completas
  cabem mesmo em nível municipal (também confirmado ao vivo), então essa
  fonte não tem a mesma restrição.
- Testes offline novos em `tests/test_ibge_registro_civil_territorio.py`
  (casamentos, divórcios) e `tests/test_ibge_saneamento.py` (as três fontes
  de saneamento), mais 5 casos no smoke ao vivo opt-in
  (`tests/test_ibge_smoke.py`, `GUARACI_IBGE_SMOKE=1`) validando os totais
  nacionais de referência acima.
- Cadência (`guaraci/orchestrator/cadence.py`), catálogo do site
  (`scripts/build_site_catalog.py`, grupo "IBGE · população e economia"),
  dicionário de campos (`guaraci/data/field_dictionary.json`) e
  `docs/SOURCES_AND_FILTERS.md` atualizados. Catálogo do site regenerado:
  94 → 99 fontes.

### Fixed: UX da interface web (botão de estimativa e filtro de lista)
- `DownloadService.discover()` (`guaraci/services/downloads.py`) tinha sua
  regra de despacho duplicada em silêncio: a UI oferecia o botão "Estimar
  volume" em todas as 94 fontes, mas apenas 27 suportam discovery (FTP
  DATASUS, SIH e os adapters `PortalFileDownloadSource` de SISAGUA e
  `srag_arquivos`); nas outras 67 o clique sempre terminava em "falha ao
  estimar", parecendo bug do sistema. Extraído `DownloadService.
  supports_discovery(source) -> bool` com a mesma lógica de despacho, agora
  reutilizado por `discover()` e exposto no contrato de `GET /sources` como
  o campo booleano `supports_discovery`, para que backend e frontend
  consultem uma única fonte de verdade. `guaraci/api/static/app.js`
  esconde `#btn-estimate` quando a fonte selecionada não suporta discovery
  em vez de mostrar um botão que falha; o 400 do backend continua como
  rede de segurança.
- Filtros do tipo `string_list` com `allowed_values` (ex.: UF do FTP
  DATASUS, com 27 opções) trocaram o `<select multiple>` aberto, que
  ocupava muito espaço vertical e dependia de Ctrl+clique pouco descoberto
  para multiseleção, por um dropdown fechado por padrão: um gatilho
  compacto mostra um resumo do estado ("Todos", os valores quando são
  poucos, ou "N selecionados") e abre um painel com checkboxes, mais campo
  de busca quando há mais de 8 opções. Preserva "selecionar tudo" /
  "limpar" e os defaults de `spec.default`. Navegável por teclado (Enter,
  espaço e seta para baixo abrem o painel; Esc fecha), `aria-expanded` no
  gatilho, fecha ao clicar fora ou pressionar Esc. Chaves novas de i18n
  (`ms_all`, `ms_selected_n`, `ms_search_ph`, `ms_no_match`) em pt e en.
  Sem dependências novas; segue as variáveis de `theme.css`.
- Testes novos em `tests/test_services.py` e `tests/test_api.py` cobrem
  `supports_discovery()` e o campo equivalente no `GET /sources` (27 das
  94 fontes retornam `true`, confirmado ao vivo).

### Added — 9 fontes SISAGUA restantes (bulk-file, Fase A follow-up)
- Registradas as 9 fontes SISAGUA que faltavam no transporte
  `PortalFileDataSource`: `sisagua_controle_mensal_demais_parametros`,
  `sisagua_controle_mensal_amostras_fora_do_padrao`,
  `sisagua_controle_mensal_plano_amostragem`,
  `sisagua_controle_mensal_infraestrutura_operacional`,
  `sisagua_vigilancia_demais_parametros`,
  `sisagua_vigilancia_cianobacterias_e_cianotoxinas`,
  `sisagua_pontos_de_captacao`, `sisagua_cadastro_carro_pipa_procedencia`,
  `sisagua_cadastro_carro_pipa_populacao`. Todos os 9 slugs confirmados ao
  vivo 2026-08-18. Apenas `sisagua_controle_mensal_plano_amostragem` é
  ano-segmentado (2014-2026, como `controle_mensal_parametros_basicos`); os
  outros 8 são cumulativos sem particionamento por ano (como
  `tratamento_agua`/`populacao_abastecida`) — confirmado ao vivo parseando
  cada dataset page antes de fixar `min_year`/`cumulative`, não assumido.
  Tamanhos comprimidos verificados ao vivo variam de ~39KB
  (`cadastro_carro_pipa_procedencia`) a ~138MB
  (`controle_mensal_demais_parametros`); `large_dataset_note` adicionada às
  fontes acima de ~35MB. Todas as 14 fontes SISAGUA do portal agora estão
  registradas. Cadência `MONTHLY` via `CADENCE_OVERRIDES`
  (`guaraci/orchestrator/cadence.py`). Discover ao vivo validado para
  `sisagua_pontos_de_captacao` via `DownloadService.discover()` end-to-end.
  Achado colateral: essas 9 fontes já existiam sob o mesmo nome como fontes
  DEMAS auto-geradas (`guaraci/services/opendatasus_registry.py`, a partir do
  swagger DEMAS) — o dedup existente em
  `DownloadService._default_sources()` agora as sombreia corretamente pelo
  transporte bulk-file (mesmo mecanismo que já protegia as 5 fontes SISAGUA
  registradas antes desta rodada).
- `scripts/build_site_catalog.py` rodou de ponta a ponta sem erro nesta
  rodada (94 fontes registradas no total após a reconciliação com o `main`;
  a suposta trava de `SystemExit` por chaves órfãs no `CURATED`, documentada
  no quadro em rodadas anteriores, não reproduziu nesta execução). `site/assets/catalog-data.js` regenerado;
  `?v=` de `index.html`/`docs.html` avançado para `20260818a`.

### Added — categoria/sampler de amostragem para a família `opendatasus files`
- `guaraci/services/dictionary_sampling.py::classify_source` agora reconhece
  a família `opendatasus files` (SRAG + as 14 fontes SISAGUA) e
  `sample_opendatasus_files()` baixa o menor recurso conhecido (via
  `discover(..., fetch_sizes=True)`, sem baixar nada acima de um teto de
  20MB) e lê as colunas reais do arquivo materializado
  (`.zip`→CSV/`.csv`/`.parquet`; CSVs SISAGUA são `;`-delimitados e
  latin-1 — confirmado ao vivo). `scripts/sample_sources.py` foi conectado a
  esse sampler.
- Achado ao rodar a amostragem: os 14 `field_dictionary.json` de SISAGUA já
  existentes eram **incorretos** — relíquias do primeiro commit do
  dicionário (antes de o transporte bulk-file existir), amostrados contra o
  antigo endpoint DEMAS auto-gerado (mesmo nome, schema diferente:
  `codigo_ibge`/`uf` em vez dos parâmetros reais `start_year`/`end_year`/
  `resource_filter`). Corrigidos nesta rodada:
  - Amostradas com sucesso (campos reais, arquivo pequeno o bastante):
    `sisagua_cadastro_carro_pipa_procedencia` (39KB; **CSV sem cabeçalho**,
    verificado ao vivo — colunas ficam `column_1..column_13`),
    `sisagua_cadastro_carro_pipa_populacao` (93KB), e
    `sisagua_vigilancia_cianobacterias_e_cianotoxinas` (2.2MB). `srag_arquivos`
    também ganhou amostra real (um ano histórico pequeno o bastante).
  - Limpas para `status: empty` com nota honesta de tamanho (menor recorte
    real ainda grande demais para o teto de 20MB):
    `sisagua_controle_mensal_parametros_basicos`, `sisagua_controle_semestral`,
    `sisagua_vigilancia_parametros_basicos`, `sisagua_tratamento_agua`,
    `sisagua_populacao_abastecida`, `sisagua_controle_mensal_demais_parametros`,
    `sisagua_controle_mensal_amostras_fora_do_padrao`,
    `sisagua_controle_mensal_infraestrutura_operacional`,
    `sisagua_controle_mensal_plano_amostragem`,
    `sisagua_vigilancia_demais_parametros`, `sisagua_pontos_de_captacao`
    (52.6MB comprimido — acima do teto).
- `docs/DATA_DICTIONARY.md` regenerado via `dictionary_io.py` (mesmo caminho
  de código de sempre — nunca diverge de `field_dictionary.json`).
- Pendência restante (registrada no quadro): INPE/INMET/IBGE novas continuam
  com entrada manual no dicionário; não integradas ao sampler automático
  nesta rodada (fora do escopo mínimo pedido — "pelo menos a família
  opendatasus files").

### Fixed — host CKAN do OpenDataSUS desativado com erro claro
- `OpenDataSUSClient.__init__` agora recusa construir um cliente em modo CKAN
  (`base_url` contendo `/api/3/action`) com um `OpenDataSUSClientError`
  (subclasse de `RuntimeError`) explicando que
  `ckan-dadosabertos.saude.gov.br` não resolve DNS (re-verificado ao vivo
  2026-08-18) e que o portal atual não expõe API CKAN — em vez de deixar a
  primeira chamada de rede falhar com um erro de DNS opaco. Nenhum host CKAN
  substituto foi inventado.
- Investigado: `doses_aplicadas_pni` (único dataset com `ckan_supported=True`)
  já usa DEMAS por padrão (`api_base_url=None` → `OpenDataSUSClient.DEFAULT_BASE_URL`,
  que é DEMAS) — o caminho CKAN só era alcançável se alguém passasse
  explicitamente `api_base_url` apontando para o host morto. Não havia
  necessidade de mover rota nenhuma para DEMAS (já está lá); apenas o guard-rail
  de erro claro foi adicionado. Descrições dos parâmetros `resource_id`/
  `api_base_url` em `guaraci/services/sources/opendatasus.py` atualizadas para
  não anunciar CKAN como um modo utilizável.
### Added — INMET automatic weather stations (Fase B2, ambiental)
- New `inmet_estacoes` source (`guaraci/inmet/`: `client.py` + `parser.py` +
  `datasource.py`) downloading INMET's per-year ZIP archives of every
  automatic weather station (`portal.inmet.gov.br/uploads/dadoshistoricos/
  <AAAA>.zip`, years 2000-present) and parsing the hourly station CSVs (8
  metadata lines + tabular header, `latin-1`, `;`-separated, comma decimals)
  into a tidy table. Params: `start_year`/`end_year` (2000+), `ufs` (filters
  which station CSVs are extracted from the yearly ZIP), `variables`
  (optional column projection). The current year is reconciled by
  `Content-Length` since INMET republishes it as more months land; past years
  are cached and never re-downloaded. Registered in the orchestrator
  (`Kind.API_WINDOW` / `Cadence.ANNUAL`, floor 2000) and in `docs/
  SOURCES_AND_FILTERS.md` §3.15. Offline tests cover the parser (both the
  2000-era `-9999`/`HH:MM` format and the current `""`/`HHMM UTC` format,
  verified against the real archives), the streaming client, the datasource,
  and service registration; a `GUARACI_INMET_SMOKE=1` opt-in test validates
  one live year/UF.
### Added — INPE Queimadas (Fase B1)
- New package `guaraci/inpe/` (`client.py` + `queimadas.py`), same pattern as
  `guaraci/nasa/`: thin urllib client + datasource, registered via
  `ApiDownloadSource` in `guaraci/services/sources/inpe.py` (mode
  `inpe queimadas api`).
- `inpe_queimadas` — fire-spot ("focos de queimada") detections from INPE's
  BDQueimadas program at `dataserver-coids.inpe.br`. Annual reference product
  (`dataset=referencia_anual` → `Brasil_sat_ref`, or `todos_satelites` →
  `Brasil_todos_sats`), years 2003+ confirmed live via directory-index parsing
  (never hardcoded). Optional `months` param switches to the monthly product
  (`mensal/Brasil`, available from 2023 onward, own schema with
  `risco_fogo`/`frp`/`precipitacao`, ignores `dataset`). `states` filters
  post-download on the `estado` column (UF code or full name).
- Complements — does not replace — `nasa_firms`: FIRMS is NASA's global
  near-real-time MODIS/VIIRS feed; INPE Queimadas is Brazil's own national
  program with its own satellite-reference methodology and locally derived
  `bioma`/`municipio` classification.
- Cadence `MONTHLY` registered in `guaraci/orchestrator/cadence.py`
  (`inpe*` name prefix, floor year 2003).
- Offline tests (`tests/test_inpe_queimadas_client.py`,
  `tests/test_inpe_queimadas_datasource.py`, fake HTTP, no network) plus an
  opt-in live smoke test (`GUARACI_INPE_SMOKE=1`,
  `tests/test_inpe_queimadas_smoke.py`) validated against the real server:
  2003 annual reference → 341 237 detections.
- Site catalog gains a new "Ambiental · Brasil" group (`G_AMB`) with the
  `inpe_queimadas` entry; `docs/SOURCES_AND_FILTERS.md` and
  `field_dictionary.json` updated.

### Added — ANA HidroWebService telemetric stations (`ana_hidro`)
- Added `guaraci/ana/client.py` (`AnaHidroClient`, OAuth token acquisition/
  auto-renewal, 30-day-window telemetric series calls) and
  `guaraci/ana/hidro.py` (`AnaHidroDataSource`) plus registration in
  `guaraci/services/sources/ana.py` (`source="ana_hidro"`, mode
  `"ana hidro api"`, `auto=False`). Endpoints and the exact query-parameter
  contract were locked by reading the live OpenAPI document at
  `https://www.ana.gov.br/hidrowebservice/api-docs`. Credentials
  (`GUARACI_ANA_ID`/`GUARACI_ANA_SENHA`) are required and were not yet
  available (operator's ANA e-mail registration pending); the connector
  ships with offline fake-client tests only and an opt-in
  `GUARACI_ANA_SMOKE=1` live smoke test that additionally skips without
  credentials. See `docs/SOURCES_AND_FILTERS.md` §3.15 for the full
  parameter table and the known gaps (response field names unverified live).

### Added — IBGE registro civil + território (Fase C)
- `ibge_nascidos_vivos_rc` (`guaraci/ibge/registro_civil.py`) — live births by
  month/sex, SIDRA table 2680 (variable 218), registro civil; a counterpoint
  to DATASUS SINASC. Reference verified live 2026-08-17: Brasil 2023,
  `mes`/`sexo`=`total` → 2 523 267.
- `ibge_obitos_rc` — deaths by month/sex, SIDRA table 2681 (variable 343),
  registro civil; counterpoint to DATASUS SIM. Reference verified live
  2026-08-17: Brasil 2023, `mes`/`sexo`=`total` → 1 429 575.
- `ibge_area_territorial` (`guaraci/ibge/territorio.py`) — area / density /
  population from SIDRA table 4714 (variables 93/614/6318 bundled in one
  request via SIDRA's `|`-joined variable list), single period 2022 (census
  reference). Reference verified live 2026-08-17: Brasil área territorial
  8 510 417.771 km².
- Both registro-civil sources reject `mes != "total"` at `level="municipio"`
  up front (`ValueError`) — confirmed live that SIDRA returns HTTP 500 for the
  municipal x all-months combination (5570 municipalities x 13 categories
  exceeds the aggregate limit); UF/região/Brasil accept the monthly
  breakdown.
- Registered in `guaraci/services/sources/ibge.py` (mode `ibge api`); backfill
  floors added to `ibge_floor` in `guaraci/orchestrator/cadence.py` (2003 for
  both registro-civil sources, 2022 — census year — for área territorial).
- Offline tests in `tests/test_ibge_registro_civil_territorio.py` (fake SIDRA
  client) plus 3 new opt-in live smoke tests in `tests/test_ibge_smoke.py`
  (`GUARACI_IBGE_SMOKE=1`).
- Site catalog, `docs/SOURCES_AND_FILTERS.md` and `field_dictionary.json` /
  `docs/DATA_DICTIONARY.md` updated for the 3 new sources; source count in
  the site copy updated to the registered total.

### Added — bulk-file transport for dadosabertos.saude.gov.br (SRAG, SISAGUA)
- New transport `PortalFileDataSource` (`guaraci/opendatasus/portal_files.py`)
  for portal "packages" whose resources are whole files (CSV/Parquet/JSON/XML,
  sometimes zipped) hosted on a public S3 bucket, not a CKAN datastore or a
  paginated DEMAS JSON API (the CKAN API on the current portal host is dead —
  `ckan-dadosabertos.saude.gov.br` doesn't resolve and
  `dadosabertos.saude.gov.br/api/3/action/...` returns 404). Discovery is a
  stdlib-only (`html.parser`) 2-hop HTML scrape: dataset page -> resource page
  -> S3 URL. Downloads are cached by basename (idempotent re-runs).
- Registered 6 new sources (mode `opendatasus files`) via
  `guaraci/services/sources/opendatasus_files.py`: `srag_arquivos` (annual
  SRAG "banco vivo" bulk, 2019–2026) and 5 of the 14 SISAGUA packages —
  `sisagua_controle_mensal_parametros_basicos`, `sisagua_controle_semestral`,
  `sisagua_vigilancia_parametros_basicos`, `sisagua_tratamento_agua`,
  `sisagua_populacao_abastecida`. `DownloadService.discover()` now dispatches
  generically to any source adapter exposing its own `discover()` (previously
  hardcoded to DATASUS FTP + `sih`), wiring `guaraci fetch discover` and
  `POST /sources/{s}/discovery` for the new sources.
- Orchestrator: `CADENCE_OVERRIDES` now sets `Cadence.MONTHLY` for the 5
  SISAGUA sources (the generic `opendatasus` mode default of WEEKLY is tuned
  for the DEMAS/CKAN record APIs, not SISAGUA's actual publication rhythm);
  SRAG keeps WEEKLY (its "banco vivo" current year republishes weekly).
- SIOPS was investigated but not registered: the portal dataset only exposes
  a metadata PDF via S3, and the source's own API
  (`siops-consulta-publica-api.saude.gov.br`) does not publish a discoverable
  Swagger/OpenAPI spec. Tracked as a pendency in `docs/handoffs/_QUADRO.md`,
  along with the remaining 9 SISAGUA packages (same transport, trivial specs).
- Docs: new `docs/SOURCES_AND_FILTERS.md` §3.5; `scripts/build_site_catalog.py`
  `CURATED` updated and `site/assets/catalog-data.js` regenerated (`?v=`
  bumped); the source count shown on the site was synced with the registered
  total.
- Incidental fix: removed 5 dead `CURATED` entries in
  `scripts/build_site_catalog.py` (`arboviroses_chikungunya`,
  `arboviroses_dengue`, `arboviroses_febre_amarela_humanos_primatas_nao_humanos`,
  `vigilancia_e_meio_ambiente_mpox`, `vacinacao_esavi`) referencing source
  names that no longer exist in the registry (superseded by the plain
  `dengue`/`chikungunya`/`febre_amarela`/`mpox`/`esavi` entries); this was
  silently blocking `python scripts/build_site_catalog.py` before this change.

### Added — versioned SIH-RD column mapping
- Added `DEFAULT_SIH_RD_COLUMN_MAP` and `apply_sih_column_map()` / `SihDataSource.apply_column_map()` in `guaraci/datasus/sih.py` for standardizing SIH-RD field names (`N_AIH` -> `numero_aih`, `DT_INTER` -> `data_internacao`, `MUNIC_RES` -> `municipio_residencia`, `DIAG_PRINC` -> `diagnostico_principal`, etc.), backed by unit regression tests in `tests/test_sih_column_map.py`.

### Added — Vogel Stack compliance CI workflow
- Added `.github/workflows/vogel_stack_ci.yml` running `check-wikilinks.ps1` and `check-quadro.ps1` on every push/PR for automated Vogel Stack compliance verification.

### Changed — legacy web app structure
- Moved `apps/web` to `legacy/apps/web`, isolating the legacy React frontend out of core installable packages and consolidating CLI-first workflow guidelines.

### Added — public properties on JobResult contract
- Promoted `JobResult.exported_files` and `JobResult.materialized_paths` as explicit, version-stable public properties on `JobResult` (`guaraci/core/results.py`), freezing the interface seam consumed downstream by Monitoramento and external scripts.

### Changed — Polars deprecation sweep
- Replaced all deprecated `df.groupby(...)` calls with `df.group_by(...).len()` in `sih.py`, `sim.py`, and `sinan.py` summary methods.

### Changed — field dictionary & catalog sampling updates
- Successfully sampled and cataloged 5 pending sources (`pni`, `siscan`, `pce`, `cnes_estabelecimentos_{codigo_cnes}`, `cnes_tipounidades_{codigo_tipo_unidade}`), raising the total of fully-sampled sources from 72 to 77 in `guaraci/data/field_dictionary.json` and `docs/DATA_DICTIONARY.md`.

### Changed — web UI restyled with the Guaraci visual identity
- `guaraci/api/static/index.html` now uses the dark "amanhecer de dados" theme
  from the project site (Space Grotesk/Inter/JetBrains Mono, sun-orange +
  teal palette, gradient progress bar, dark log console, inline Guaraci logo).
  Purely presentational: all element ids/classes consumed by the embedded JS
  and every API contract (`/sources`, `/sources/{s}/schema`, `/jobs`,
  `/jobs/{id}/logs`) are unchanged. Verified end-to-end against the live API
  (schema-driven wizard, job creation, progress, logs, history).

### Added — documentation site with the full 91-source catalog
- `site/docs.html` + `site/assets/docs.js`: extensive user guide (install,
  web UI, `guaraci fetch`, output formats, NASA credentials, orchestrator,
  best practices) plus a generated catalog documenting every source — all
  parameters (type, phase, default, allowed values), live-sampled fields, and
  a ready-to-copy CLI example per source.
- `scripts/build_site_catalog.py` generates `site/assets/catalog-data.js` from
  `DownloadService` schemas + `guaraci/data/field_dictionary.json` +
  orchestrator cadence profiles; `--live` adds real FTP discovery counts
  (14 DATASUS systems verified against `ftp.datasus.gov.br`).
- Landing page explorer cards now open a per-source detail modal linking into
  the docs page (single data source: `catalog-data.js` replaces `bases.js`).

### Added — IBGE connectors (SIDRA aggregates API, keyless JSON)
- New `guaraci/ibge/` package with a shared `SidraAggregateSource` base (fetch
  one year at a time, flatten `resultados -> series -> serie` into tidy rows,
  export/manifest) and three curated sources — the denominator / socioeconomic
  layers for turning DATASUS counts into rates:
  - `ibge_populacao` — population estimates by locality x year (table 6579).
  - `ibge_pib_municipios` — municipal GDP / PIB in R$ 1000 (table 5938, 2002+).
  - `ibge_populacao_idade_sexo` — census population by sex and age (table 9514;
    `sexo` and `faixa_etaria` params, default 5-year age groups by sex per UF).
- Output is one row per (locality, year[, classification]); missing markers
  (`-`, `..`) become null; a year with no data is skipped with a warning, not a
  failure. The client decompresses gzip responses (the IBGE CDN sends them
  intermittently) and supports SIDRA classification filters.
- All three are registered in `DownloadService` (mode `ibge api`), reachable
  from the API, `guaraci fetch`, and the orchestrator (annual `api_window`, with
  per-table backfill floors: 2001 / 2002 / 2022). Tests: `tests/test_ibge.py`
  (18, offline) + opt-in live smoke `tests/test_ibge_smoke.py`
  (`GUARACI_IBGE_SMOKE=1`).
- Docs: `README.md`, `docs/SOURCES_AND_FILTERS.md` (§2 + §3.12–3.14),
  `docs/ARCHITECTURE.md` (§1, §3.1, §7.7), `docs/DATA_DICTIONARY.md` (three
  `ibge_*` entries, live-sampled), `guaraci/data/field_dictionary.json`,
  `docs/AI_HANDOFF_OPENDATASUS.md` (§1), `docs/operacao.md` (§2).

### Added — bronze orchestrator (`guaraci orchestrate`)
- New `guaraci/orchestrator/` package + `guaraci orchestrate` CLI that sweeps
  every registered source into a browsable **bronze** tree of raw CSVs at each
  source's **native granularity**, recording one row per partition in an
  append-only CSV **ledger** (`<bronze_root>/_ledger.csv`). This is the
  automation layer that feeds the Sabiá data lake.
- Two bronze tiers, written from a single decode of each file: `raw` (the
  official file as-is, native granularity) and `refined` (the same rows
  repartitioned into the browsable `disease/year/month` tree — annual sources
  split by their event date with an unknown-month bucket, monthly sources pass
  through). `refined` is still bronze (a pure repartition, no harmonisation);
  select with `--tier raw|refined|both` (default both).
- Modes: `orchestrate backfill` (full history, "sair tudo"), `orchestrate
  update` (incremental delta driven by the ledger, with a `src_size` volumetria
  check so a grown current-year file is re-pulled), plus `plan` (dry-run),
  `profiles` (resolved per-source kind/cadence) and `status` (read the ledger).
- Each source resolves to a `SourceProfile` (kind + publication **cadence** +
  backfill floor): SINAN/SIM/SIH + the 11 FTP systems discover at file level
  (1 DATASUS file = 1 bronze CSV); OpenDataSUS sweeps by year; NASA is marked
  on-demand (needs a lat/lon) and skipped by the sweep.
- FTP materialisation downloads a source's whole batch over one connection
  straight from each file's known path (no re-listing), reusing the idempotent
  parquet cache, then writes each raw file out as its own CSV.
- Thin cron entrypoints in `scripts/server/` (`orchestrate.sh` + `orchestrate.ps1`,
  with a lock + per-day log). Docs: `docs/ORCHESTRATOR.md`. Tests:
  `tests/test_orchestrator.py` (22, offline) + opt-in live smoke
  `tests/test_orchestrator_smoke.py` (`GUARACI_FTP_SMOKE=1`).

### Changed — DATASUS sources can now collect the in-progress current year
- The DATASUS microdata sources (SIH, SIM, SINAN, and the 11 spec-driven FTP
  systems) previously capped collection at the last complete year
  (`current_year - 1`), in both the parameter schema (`maximum`) and the
  runtime year resolution. They now accept the current year as well, so a
  surveillance pipeline can pull the in-progress season (e.g. requesting
  `end_year=2026` during 2026). Only genuinely future years are clamped, back
  to the current year (was: silently reduced to `current_year - 1`).
- Defaults are unchanged (`default=last_year`), so callers that don't override
  the range still get the last complete year. Current-year data is logged as
  potentially partial, reflecting the DATASUS publication lag (~2–3 months).
- Other sources (NASA, OpenDataSUS, gov.br) already allowed the current year;
  this aligns the DATASUS FTP layer with them.

## [0.6.0] - 2026-06-28

### Added — source validation + data dictionary (`fetch fields`)
- `scripts/sample_sources.py` samples each source with tiny windows to validate it
  works and capture (a) filter parameters and (b) output field names. Results are
  shipped as `guaraci/data/field_dictionary.json` + `docs/DATA_DICTIONARY.md` (88
  sources cataloged; 19 field-sampled). New `guaraci fetch fields <source>` prints
  the known output field names for a source.
- Findings surfaced by the live sampling (flagged for follow-up): `pni`/`pce`/`siscan`
  return empty with a `group=None` warning in `load_dataframe` (multi-group/national
  load path); `mpox` returned an upstream DEMAS HTTP 500; NASA FIRMS/GPM need
  credentials. The SIH field set was confirmed real (`DT_INTER`/`DT_SAIDA`/`MUNIC_RES`/
  `DIAG_PRINC` present), validating the Monitoramento ingest column map.

### Added — generic `guaraci fetch` CLI (schema-driven, all sources)
- New `guaraci/cli/fetch_cli.py` registering a `fetch` command group: `fetch list`
  (every registered source), `fetch schema <source>` (its parameter schema),
  `fetch run <source> --set KEY=VALUE … [--format csv|parquet|sqlite] [-o DIR]`,
  and `fetch discover <source> --set … [--sizes]` (FTP preflight: file count by
  group/UF, plus the total download size with `--sizes`, without downloading).
  It drives `DownloadService`, so OpenDataSUS, NASA and gov.br sources are now
  reachable from the CLI (previously only via the API/UI) with no per-source code.
  `--set` values are coerced to the schema-declared type; `--format` is optional
  (omit for download-only); NASA credentials stay environment-only. Tests:
  `tests/test_fetch_cli.py`.
- `DownloadService.discover()` now accepts a keyword-only `fetch_sizes` flag and
  forwards it to the FTP datasource, so the preflight can report the total
  download size (backward-compatible; default `False`).

### Changed — legacy SNIS BigQuery deps moved to an optional `snis-legacy` extra
- `google-cloud-bigquery` and `db-dtypes` moved out of the core dependencies (and
  out of `requirements.txt`) into a new optional extra `snis-legacy`, so
  `pip install guaraci` / `guaraci[datasus]` no longer pulls the Google stack.
  They are only needed for the legacy SNIS BigQuery path (`snis download-legacy`),
  which imports them lazily and now points users to `pip install "guaraci[snis-legacy]"`.
  The `full` extra still includes them.

### Added — NASA POWER climate source (`nasa_power`)
- New `guaraci/nasa/` package integrating the NASA POWER API directly
  (`power.larc.nasa.gov`, no authentication), honoring the primary-source
  principle: `NasaPowerClient` (stdlib `urllib`, OpenDataSUS-style error
  taxonomy) and `NasaPowerDataSource` (single-point daily/monthly series).
- Registered the `nasa_power` source (`mode = "nasa power api"`) through a new
  `NasaDownloadSource` adapter in `guaraci/services/downloads.py`, with a
  schema-driven parameter set (`latitude`, `longitude`, `start_date`,
  `end_date`, `parameters`, `temporal`, `community`, `keep_raw`, `timeout`,
  `api_base_url`, `output_dir`, `output_format`) and `_normalize_nasa_power_params`.
- Output is a tidy wide table (one row per period, one column per POWER
  variable) with derived `period`/`date`/`year`/`month`/`day` and point
  columns; the `header.fill_value` sentinel is converted to null and POWER's
  monthly annual aggregate is preserved losslessly as `month=13`.
- Exports to `csv`/`parquet`/`sqlite`, writes a standard `DownloadManifest`,
  and emits `download_start`/`file_completed`/`download_complete` progress
  events compatible with `DownloadJobService`.
- Tests: `tests/test_nasa_power_client.py`, `tests/test_nasa_power_datasource.py`,
  `tests/test_nasa_power_service.py`, plus a NASA POWER schema check in
  `tests/test_api.py` (39 new datasource/client/service tests).
- Docs: `README.md`, `docs/ARCHITECTURE.md` (§3.1, §7.4),
  `docs/SOURCES_AND_FILTERS.md` (§2, §3.9).

### Notes
- No new runtime dependency: the client uses only the standard library.
- `latitude`/`longitude` are the native point inputs; municipality-centroid
  lookup is deferred as future work (needs an IBGE coordinate dataset).
- The curated `parameters` allow-list is a subset of the full POWER catalogue,
  chosen for public-health/environmental cross-analysis and validated live.

### Added — NASA FIRMS active-fire source (`nasa_firms`)
- `NasaFirmsClient` (in `guaraci/nasa/client.py`) and `NasaFirmsDataSource`
  (`guaraci/nasa/firms.py`) integrating the NASA FIRMS active-fire CSV API
  (`firms.modaps.eosdis.nasa.gov`) directly. No new runtime dependency.
- Registered the `nasa_firms` source (`mode = "nasa firms api"`) via the shared
  `NasaDownloadSource` adapter + `_normalize_nasa_firms_params`. Schema:
  `start_date`, `end_date`, `product` (FIRMS source product; curated
  allow-list), `country` (ISO3, default `BRA`), `area` (optional bounding-box
  override), `keep_raw`, `timeout`, `api_base_url`, `output_dir`,
  `output_format`.
- The `[start_date, end_date]` window is chunked into consecutive <=10-day
  FIRMS requests; each CSV is parsed generically (robust to MODIS vs VIIRS
  columns), concatenated, and tagged with a `firms_product` provenance column.
- **Security:** the FIRMS `MAP_KEY` is read only from the
  `GUARACI_FIRMS_MAP_KEY` environment variable — never a job parameter (job
  params are persisted to disk) and never written to the manifest; it is also
  redacted from client error messages.
- The user-facing parameter is named `product` (not `source`) to avoid
  colliding with `DownloadService.run(source, **params)`.
- Tests: `tests/test_nasa_firms_client.py`, `tests/test_nasa_firms_datasource.py`,
  `tests/test_nasa_firms_service.py`, plus a FIRMS schema check in
  `tests/test_api.py` (29 new tests).
- Docs: `README.md`, `docs/ARCHITECTURE.md` (§1, §3.1, §7.5),
  `docs/SOURCES_AND_FILTERS.md` (§2, §3.10).
- Live-unvalidated pending a free MAP_KEY (mock-tested only); endpoint paths and
  CSV handling follow the documented FIRMS API.

### Added — NASA GPM IMERG precipitation source (`nasa_gpm`)
- New `NasaGesDiscClient` (in `guaraci/nasa/client.py`) and `NasaGpmDataSource`
  (`guaraci/nasa/gpm.py`) integrating GES DISC GPM IMERG daily precipitation via
  **OPeNDAP point subsetting** — one grid cell per day through an `.ascii`
  constraint, so it never downloads or parses HDF5/NetCDF and adds **no new
  runtime dependency** (stdlib only), mirroring `nasa_power`'s point-series shape.
- Registered the `nasa_gpm` source (`mode = "nasa gpm api"`) via the shared
  `NasaDownloadSource` adapter + `_normalize_nasa_gpm_params`. Schema:
  `latitude`, `longitude`, `start_date`, `end_date`, `variable` (curated IMERG
  variables), `product` (`daily`), `keep_raw`, `timeout`, `api_base_url`,
  `output_dir`, `output_format`. The window is capped at ~1 year (one request
  per day).
- The client preserves the EDL bearer token across the GES DISC -> URS OAuth
  redirect (urllib drops `Authorization` cross-host by default), converts the
  IMERG fill sentinel to null, and parses the OPeNDAP ASCII grid grammar.
- **Security:** the Earthdata token is read only from the
  `GUARACI_EARTHDATA_TOKEN` environment variable — never a job parameter (job
  params are persisted to disk), never written to the manifest, and redacted
  from client error messages.
- **EXPERIMENTAL / live-data-unvalidated:** the OPeNDAP contract (endpoint,
  granule naming, grid layout, index formula, ASCII grammar) was validated with
  a real Earthdata token, but a successful *data* response also requires the
  account to authorize the "NASA GESDISC DATA ARCHIVE" application at
  urs.earthdata.nasa.gov; until then data returns a clean, actionable HTTP 401.
  The parser/pipeline are covered by tests against the documented ASCII format.
- Tests: `tests/test_nasa_gpm_client.py`, `tests/test_nasa_gpm_datasource.py`,
  `tests/test_nasa_gpm_service.py`, plus jobs-integration and an API schema check
  (30 new tests). Docs: `README.md`, `docs/ARCHITECTURE.md` (§3.1, §7.6),
  `docs/SOURCES_AND_FILTERS.md` (§2, §3.11).

## [0.5.2] - 2026-05-28

### Entradas principais
- Updated `vogel-stack` submodule to VogelStack commit `d54e529`, including the automatic-commit workflow rule and nested-vault README wikilinks.
- Documented Guaraci's closing protocol for generic sync commits in `AGENTS.md`, `docs/versionamento.md`, and `docs/operacao.md`.
- Published the submodule README wikilink adaptation while keeping the new upstream Graphify discovery section.
- Fixed SIH discovery to use the PySUS FTP catalog directly and require `pysus[dbc]` for DBC-to-Parquet conversion in Docker builds.
- Added SIH discovery preflight and made empty SIH `groups`/`months` selections mean unfiltered; removed redundant SIH `mes` from the jobs/UI schema.

### Estado
- Verification: documentation diff reviewed locally; SIH runtime verification is listed below.
- SIH verification: FTP discovery was checked against the JP filter set without downloading the full dataset, and focused unit tests were run locally.
- Still unsupported: local Python execution without Docker remains WIP.
- Operational note: `vogel-stack` commit `d54e529` was pushed before syncing/pushing the Guaraci parent repository.

### DATASUS: direct-FTP backend (phases 1-4)
- Added a direct DATASUS FTP layer under `guaraci/datasus/ftp/` (`client`, `catalog`, `discovery`, `dbc`, shared `orchestration`, and per-source `sih_backend`/`sim_backend`/`sinan_backend`) built on stdlib `ftplib` + `pyreaddbc`/`dbfread`, replacing the ~20 transitive dependencies of `pysus[dbc]` with 2 packages while keeping the same primary source (`ftp.datasus.gov.br`).
- SIH, SIM, and SINAN now select their backend via `GUARACI_DATASUS_BACKEND={ftp|pysus}`, resolved by the shared dependency-free selector `guaraci/datasus/backend.py`.
- **Default backend flipped to `ftp`** (phase 4): the `datasus` extra now installs only `pyreaddbc` + `dbfread`. The legacy PySUS path stays installable for one release via the new `datasus-legacy` extra and selectable via `GUARACI_DATASUS_BACKEND=pysus`. This supersedes the earlier same-version note above about requiring `pysus[dbc]` in Docker builds.
- Bumped the PySUS pin to `pysus>=2.2.0` (the obsolete `[dbc]` extra was folded into the base package upstream and now warns on `uv lock`).
- API/CLI/UI contracts unchanged: the `mode` descriptor for SIH/SIM/SINAN remains `pysus ftp` and the parquet output schema is identical.

### Estado (direct-FTP migration)
- Tests: full suite 319 passed, 3 skipped (opt-in live FTP smoke + Docker-specific). The two failures in `tests/test_sinan_datasource.py` (`test_sinan_download_uses_single_worker`, `test_download_file_safe_closes_ftp_singleton`) are pre-existing — they reference `ThreadPoolExecutor`/`_download_file_safe`, already absent from `sinan.py` before this branch — and are unrelated to this migration; flagged for separate cleanup.
- Gates pendentes: bit-exact parity vs PySUS and 1 week of opt-in production validation were NOT met before the default flip; the flip was authorized anyway and is reversible via a single env var (`GUARACI_DATASUS_BACKEND=pysus`) or by reverting `DEFAULT_BACKEND` in `guaraci/datasus/backend.py`.

### DATASUS: 11 more systems via direct FTP (phase 5)
- Extended the direct-FTP integration beyond SIH/SIM/SINAN to eleven more DATASUS microdata systems: `sinasc`, `sia` (SIA-SUS ambulatorial), `cnes`, `pni` (historical SI-PNI), `ciha`, `cih`, `siscan`, `sisprenatal`, `resp`, `pce`, and `painel_oncologia`. All FTP-only (no PySUS legacy path).
- New spec-driven engine: `guaraci/datasus/ftp/specs.py` (one `SystemSpec` per system — filename regex + FTP paths + dimension flags), a generic `discover_spec`, plain-`.DBF` decoding in `dbc.py` (PNI ships uncompressed DBF), and `generic_backend`. Paths and group sets (SIA's 14 groups, CNES's 13, PNI's CPNI/DPNI) were confirmed by live FTP recon, not guessed.
- One generic `FtpDataSource` (parametrised by spec) plus registration of all eleven as platform sources (`mode = "datasus ftp"`), reachable via `/sources`, `/sources/{source}/schema`, `/jobs`, the UI, and a new generic `guaraci datasus` CLI (`list` / `download` / `discover`).
- Discovery preflight extended to all eleven (file count + by-group/by-state, no download) via `POST /sources/{source}/discovery`, `DownloadService.discover()`, and `guaraci datasus discover` — important before pulling large systems like SIA. `fetch_sizes` is off by default so the preflight never issues thousands of `SIZE` round-trips.
- Tests: ~70 offline tests (specs, discovery layouts/dispatch, DBF decode, generic backend, datasource, registry, CLI, API) plus an opt-in live smoke (`tests/test_ftp_smoke_phase5.py`, `GUARACI_FTP_SMOKE=1`) that downloads+decodes the oncology panel (`.dbc`) and PNI (`.DBF`) against the real server. Full suite is green; the previously-failing stale `tests/test_sinan_datasource.py` tests were rewritten to cover the current legacy path, and the new modules are mypy-clean.
- Scope/exclusions: collection params only for now (no per-field export refinements yet); `CMD` (no accessible microdata on the FTP) and `ANS` (private-insurance, out of public-health-microdata scope) were deliberately excluded.

## [0.5.1] - 2026-05-26

### Fixed
- PySUS 2.x Docker Linux integration by adding `libmagic1` system dependency to `Dockerfile`.
- Confirmed PySUS 2.1.0 compatibility with Guaraci async client functions.

### Changed
- Project version updated to `0.5.1`

## [0.5.0] - 2026-05-22

### Added
- OpenDataSUS sources `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`, and `febre_amarela` elevated to first-class epidemiological sources with start/end year enforcement and local filtering
- Auto-generated DEMAS source registry from local Swagger catalog (`guaraci/services/opendatasus_registry.py`)
- Generic DEMAS download path with query parameter passthrough and path parameter substitution
- `phase` field on `SourceParameterSpec` and `SourceParamResponse` for schema-driven UI grouping
- `error_retryable` flag on `DownloadJob` with non-retryable retry guard
- `DownloadManifest` v1.1 with `materialized_paths`, `exported_files`, `warnings`, and `request.filters` layout
- Support for `%d/%m/%Y` date parsing in OpenDataSUS datasource for sources like `febre_amarela`
- Developer scripts: `scripts/scaffold_opendatasus.py` and `scripts/smoke_opendatasus_sources.py`
- Contract tests for generated registry against Swagger catalog (`tests/test_opendatasus_generated_registry.py`)
- Documentation: `docs/quickstart.md`, `docs/operacao.md`, `docs/versionamento.md`

### Changed
- Project version updated to `0.5.0`
- Manifest schema version bumped from `1.0` to `1.1` (fields now optional, new layout)
- OpenDataSUS generated DEMAS sources now pass declared Swagger query parameters and substitute required path parameters
- `/sources/{source}/schema` now preserves the parameter `phase` field so the UI can group basic, export, refinement, and technical controls correctly
- UI now uses phase-based filter grouping instead of hardcoded field lists
- OpenDataSUS generated-source manifests now include `api_params` and endpoint query parameters for request traceability
- OpenDataSUS client errors now distinguish connectivity, timeout, HTTP, configuration, and response-format failures with actionable hints
- OpenDataSUS datasource failures now include CKAN/DEMAS execution context such as package resolution, endpoint, page, and resource offset when available
- OpenDataSUS export warnings are more precise about preserved artifacts, and manifests now persist warning messages for troubleshooting
- Documentation reorganized: `DOCKER_WORKFLOW.md`, `IMPROVEMENTS.md`, `INSTALL.md` moved to `docs/`
- `docs/README.md` rewritten with structured sections

### Fixed
- SINAN lazy-load guard to prevent redundant initialization

## [0.4.1] - 2026-02-24

### Added
- OpenDataSUS sources `doses_aplicadas_pni` and `zikavirus` integrated into the official pipeline through `/sources`, dynamic schema, jobs, and UI
- isolated HTTP layer for OpenDataSUS in `guaraci/opendatasus/client.py` with error handling
- OpenDataSUS datasource support with base year filters `start_year` and `end_year`, plus optional refinements `start_date`, `end_date`, and `uf`
- `keep_raw` for OpenDataSUS with default `false`
- optional OpenDataSUS export in `csv`, `parquet`, and `sqlite`

### Changed
- project version updated to `0.4.1`
- architecture, API, source, and UI documentation updated to include OpenDataSUS
- UI now separates basic filters from `Advanced Filtering`, while keeping `output_dir` in the basic block
- desktop launcher now centralizes outputs in `Guaraci Downloads` on the Desktop
- default OpenDataSUS client endpoint adjusted to DEMAS at `apidadosabertos.saude.gov.br`
- OpenDataSUS source aliases `opendatasus` and `vacinacao_covid19` removed to avoid ambiguity; canonical names must be used

## [0.4.0] - 2026-02-24

### Added
- jobs API and UI with progress monitoring through percentage, bytes, ETA, and current file
- output endpoints with `host_output_dir`, `exported_files`, `output_format`, and `export_warning`
- PySUS artifact materialization in `raw/` and local manifests
- job retry support for `failed` and `canceled`
- UI with source-schema-driven forms

### Changed
- primary SNIS flow consolidated as a `gov.br` crawler download
- legacy SNIS BigQuery integration moved to `legacy`
- alphabetical source ordering in the UI and API
- removal of the standalone `ano` filter from the jobs/UI schema for SINAN and SIH, keeping `start_year` and `end_year`
- documentation updated for the Docker-first operating model

### Fixed
- unknown parameter validation in `POST /jobs` now returns HTTP `400`
- robustness fixes in export handling and output rendering

### Notes
- local Python execution without Docker remains WIP and is not officially supported

## [0.3.0] - 2025-10-27

### Added
- DATASUS integrations for `SIM` and `SIH`
- dedicated CLIs for `sim` and `sih`
- default CSV, Parquet, and SQLite export for DATASUS sources

## [0.2.0] - 2025-10-27

### Added
- initial functional project base with Docker and modular structure
- first `SINAN` integration
- `core` layer for configuration, datasource, logging, and initial tests

## [0.1.x] - Legacy

### Notes
- initial prototype outside the current structure, without full repository history
