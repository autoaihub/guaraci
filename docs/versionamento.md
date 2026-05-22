# Versionamento do Projeto

## Política de versionamento

- **Quando atualizar versão**: A versão do Guaraci deve ser incrementada em mudanças arquiteturais significativas (ex: introdução do modelo de Jobs), adição de novas fontes substanciais (ex: OpenDataSUS, DATASUS) ou em quebras de contrato de integração/schema. O modelo segue os princípios de SemVer de forma pragmática para a API e arquitetura interna.
- **Papel do README**: O `README.md` age como a porta de entrada. Ele DEVE refletir estritamente a versão `tag` atual de produção do repositório (atualmente `0.5.0`) e documentar as features presentes nela. Não deve conter promessas de backlog futuro tratadas como já prontas.
- **Papel do Changelog**: O `CHANGELOG.md` concentra o detalhamento técnico e histórico oficial das mudanças separadas por data, contendo entradas sobre `Added`, `Changed` e `Fixed`. O changelog não é um log do git; é um documento legível para humanos e focado em valor de produto e estabilidade da API.

## Histórico de Versões e Fases do Produto

### 0.5.x - Expansão Massiva de Fontes e Auto-Geração
A fase `0.5.x` marca a transição para geração automática de fontes a partir de catálogos de API, evolução do schema de manifesto, e UI dirigida por fases.

- **0.5.0**: Expansão para 7+ fontes epidemiológicas OpenDataSUS (`febre_amarela`, `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`), auto-geração de fontes DEMAS a partir do catálogo Swagger local, evolução do manifest para v1.1, adição de `phase` ao schema de parâmetros, UI dirigida por `phase`, `error_retryable` em jobs, e reorganização completa da documentação.

### 0.4.x - Fase Operacional Avançada e OpenDataSUS
A fase `0.4.x` consolida o Guaraci como uma ferramenta estável voltada a fluxos assíncronos, estabilizando UI de operadores e acoplando conectores HTTP mais complexos.

- **0.4.1**: Introdução de fontes robustas do OpenDataSUS (`doses_aplicadas_pni`, `zikavirus`), estabilização do painel de downloads no Desktop (`Guaraci Downloads`) e clientes isolados com tratamento de erro granular.
- **0.4.0**: Lançamento da Arquitetura Orientada a Jobs (assíncronos, ETA, cancelamento e retentativas). Lançamento da UI baseada em schemas dinâmicos e consolidação do crawler governamental (gov.br).

### 0.3.x - Expansão de Fontes DATASUS
Foco na captação padronizada de dados tabulares (PySUS) com filtros específicos de coorte e espacial.

- **0.3.0**: Incorporação das bases do DATASUS (`SIM`, mortalidade, e `SIH`, morbidade/hospitalar), além da introdução de utilitários de exportação padronizada (CSV, Parquet, SQLite).

### 0.2.x - Estabelecimento do Baseline
Fase fundacional do projeto, saindo de scripts isolados para um módulo operável.

- **0.2.0**: Dockerização do fluxo principal (Docker-first), estrutura modular e primeira integração de caso de uso com `SINAN` (agravos de notificação).

### 0.1.x - Legado / Experimental
- Trabalhos locais focados em BigQuery ou downloads puramente manuais, atualmente deprecados ou externalizados.
