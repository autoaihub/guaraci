# Versionamento do Projeto

## Política de versionamento

- **Quando atualizar versão**: a versão do Guaraci é incrementada em mudanças arquiteturais significativas (ex.: introdução do modelo de Jobs), adição de novas fontes substanciais (ex.: OpenDataSUS, DATASUS, NASA) ou quebras de contrato de integração/schema. O modelo segue os princípios de SemVer de forma pragmática para a API e a arquitetura interna.
- **Papel do README**: o `README.md` é a porta de entrada. Deve refletir estritamente a versão atual de produção do repositório (atualmente `0.6.0`) e documentar as features presentes nela — sem tratar backlog futuro como pronto.
- **Papel do Changelog**: o `CHANGELOG.md` concentra o detalhamento técnico e o histórico oficial das mudanças por data (`Added`, `Changed`, `Fixed`). Não é um log do git; é um documento legível por humanos, focado em valor de produto e estabilidade da API.

## Workflows com commit automático

Quando o Guaraci for sincronizado por script que executa `git add -A`, `git commit` e `git push` com mensagem genérica (ex.: `sync: <maquina> <data>`), o `CHANGELOG.md` passa a ser o registro funcional da entrega. Nessas rodadas, a entrada no topo do changelog deve ser criada antes do sync e registrar:

- arquivos de documentação, código ou submódulos tocados;
- efeito observável da mudança para usuários, operadores ou agentes;
- verificações executadas;
- o que continua sem suporte oficial ou fora do escopo.

Como este repositório usa o submódulo `vogel-stack`, o commit novo dentro do submódulo precisa existir no remoto antes do sync do Guaraci — senão o repositório pai aponta para um commit que outros clones não conseguem buscar.

## Histórico de Versões e Fases do Produto

### 0.6.x — Ambiente (NASA), FTP direto e CLI unificada
Amplia o Guaraci para além da saúde, adota a aquisição direta do DATASUS e unifica o acesso por linha de comando.

- **0.6.0**: fontes de ambiente da NASA (`nasa_power`, `nasa_firms`, `nasa_gpm`); backend **FTP direto** como padrão do DATASUS (substituindo o PySUS) + 11 sistemas FTP novos (SINASC, SIA, CNES, PNI, CIHA, CIH, SISCAN, SISPRENATAL, RESP, PCE, painel de oncologia); CLI genérica schema-driven `guaraci fetch` (`list`/`schema`/`run`/`discover`/`fields`); dicionário de dados por fonte (`docs/DATA_DICTIONARY.md`); BigQuery (SNIS legado) movido para o extra opcional `snis-legacy`; limpeza do repositório e adoção do quadro de trabalho da Vogel Stack.

### 0.5.x — Expansão massiva de fontes e auto-geração
Transição para geração automática de fontes a partir de catálogos de API, evolução do schema de manifesto e UI dirigida por fases.

- **0.5.0–0.5.2**: 7+ fontes epidemiológicas OpenDataSUS (`febre_amarela`, `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`); auto-geração de fontes DEMAS a partir do catálogo Swagger local; manifesto v1.1; campo `phase` no schema de parâmetros; `error_retryable` em jobs; correções de discovery do SIH.

### 0.4.x — Fase operacional avançada e OpenDataSUS
Consolida o Guaraci como ferramenta estável voltada a fluxos assíncronos.

- **0.4.1**: fontes robustas do OpenDataSUS (`doses_aplicadas_pni`, `zikavirus`), painel de downloads no Desktop e clientes HTTP isolados com tratamento de erro granular.
- **0.4.0**: arquitetura orientada a Jobs (assíncronos, ETA, cancelamento, retentativas), UI baseada em schemas dinâmicos e consolidação do crawler gov.br.

### 0.3.x — Expansão de fontes DATASUS
- **0.3.0**: bases do DATASUS (`SIM`, `SIH`) e exportação padronizada (CSV, Parquet, SQLite).

### 0.2.x — Estabelecimento do baseline
- **0.2.0**: dockerização (Docker-first), estrutura modular e primeira integração (`SINAN`).

### 0.1.x — Legado / experimental
- Scripts locais focados em BigQuery ou downloads manuais, hoje deprecados ou externalizados.

---
[Índice da documentação](README.md) · [Voltar ao projeto](../README.md)
