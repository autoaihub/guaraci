# Versionamento do Projeto

## PolÃ­tica de versionamento

- **Quando atualizar versÃ£o**: A versÃ£o do Guaraci deve ser incrementada em mudanÃ§as arquiteturais significativas (ex: introduÃ§Ã£o do modelo de Jobs), adiÃ§Ã£o de novas fontes substanciais (ex: OpenDataSUS, DATASUS) ou em quebras de contrato de integraÃ§Ã£o/schema. O modelo segue os princÃ­pios de SemVer de forma pragmÃ¡tica para a API e arquitetura interna.
- **Papel do README**: O `README.md` age como a porta de entrada. Ele DEVE refletir estritamente a versÃ£o `tag` atual de produÃ§Ã£o do repositÃ³rio (atualmente `0.5.1`) e documentar as features presentes nela. NÃ£o deve conter promessas de backlog futuro tratadas como jÃ¡ prontas.
- **Papel do Changelog**: O `CHANGELOG.md` concentra o detalhamento tÃ©cnico e histÃ³rico oficial das mudanÃ§as separadas por data, contendo entradas sobre `Added`, `Changed` e `Fixed`. O changelog nÃ£o Ã© um log do git; Ã© um documento legÃ­vel para humanos e focado em valor de produto e estabilidade da API.

## HistÃ³rico de VersÃµes e Fases do Produto

### 0.5.x - ExpansÃ£o Massiva de Fontes e Auto-GeraÃ§Ã£o
A fase `0.5.x` marca a transiÃ§Ã£o para geraÃ§Ã£o automÃ¡tica de fontes a partir de catÃ¡logos de API, evoluÃ§Ã£o do schema de manifesto, e UI dirigida por fases.

- **0.5.1**: ExpansÃ£o para 7+ fontes epidemiolÃ³gicas OpenDataSUS (`febre_amarela`, `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`), auto-geraÃ§Ã£o de fontes DEMAS a partir do catÃ¡logo Swagger local, evoluÃ§Ã£o do manifest para v1.1, adiÃ§Ã£o de `phase` ao schema de parÃ¢metros, UI dirigida por `phase`, `error_retryable` em jobs, e reorganizaÃ§Ã£o completa da documentaÃ§Ã£o.

### 0.4.x - Fase Operacional AvanÃ§ada e OpenDataSUS
A fase `0.4.x` consolida o Guaraci como uma ferramenta estÃ¡vel voltada a fluxos assÃ­ncronos, estabilizando UI de operadores e acoplando conectores HTTP mais complexos.

- **0.4.1**: IntroduÃ§Ã£o de fontes robustas do OpenDataSUS (`doses_aplicadas_pni`, `zikavirus`), estabilizaÃ§Ã£o do painel de downloads no Desktop (`Guaraci Downloads`) e clientes isolados com tratamento de erro granular.
- **0.4.0**: LanÃ§amento da Arquitetura Orientada a Jobs (assÃ­ncronos, ETA, cancelamento e retentativas). LanÃ§amento da UI baseada em schemas dinÃ¢micos e consolidaÃ§Ã£o do crawler governamental (gov.br).

### 0.3.x - ExpansÃ£o de Fontes DATASUS
Foco na captaÃ§Ã£o padronizada de dados tabulares (PySUS) com filtros especÃ­ficos de coorte e espacial.

- **0.3.0**: IncorporaÃ§Ã£o das bases do DATASUS (`SIM`, mortalidade, e `SIH`, morbidade/hospitalar), alÃ©m da introduÃ§Ã£o de utilitÃ¡rios de exportaÃ§Ã£o padronizada (CSV, Parquet, SQLite).

### 0.2.x - Estabelecimento do Baseline
Fase fundacional do projeto, saindo de scripts isolados para um mÃ³dulo operÃ¡vel.

- **0.2.0**: DockerizaÃ§Ã£o do fluxo principal (Docker-first), estrutura modular e primeira integraÃ§Ã£o de caso de uso com `SINAN` (agravos de notificaÃ§Ã£o).

### 0.1.x - Legado / Experimental
- Trabalhos locais focados em BigQuery ou downloads puramente manuais, atualmente deprecados ou externalizados.


---
? [Índice da documentação](README.md) · [Voltar ao projeto](../README.md)
