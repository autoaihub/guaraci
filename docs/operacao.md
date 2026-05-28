# Operação do Projeto

Este documento condensa o modelo de operação diária do **Guaraci**, definindo limites de suporte, modos de diagnóstico de execuções assíncronas e os guardrails na operação automatizada (por IAs) ou humana.

## 1. Caminho Oficialmente Suportado

- **Fluxo Oficial**: O Guaraci opera **Docker-first**. O ponto de entrada principal suportado e testado pelo projeto é a conteinerização (gerida via `docker-compose.yml` e `dockerfile`) que expõe a API HTTP e hospeda as filas de Jobs no background.
- **Interfaces Primárias**: 
  - UI Web em `http://localhost:8002` (iniciada pelos launchers de Desktop, apontando resultados para `Guaraci Downloads`).
  - Execução de CLI delegada via container Docker.
- **Fluxo Experimental/WIP**: Executar a stack ou CLI em Python nu localmente (`python -m guaraci...` fora de um contêiner configurado) é um *Work In Progress* e **não possui suporte oficial ou garantias** de funcionamento em todos os sistemas operacionais do projeto base. 

## 2. Pré-requisitos e Limites Conhecidos

- **Ambiente Mínimo**: Motor Docker rodando. No Windows, o PowerShell é a interface padronizada para os *launchers* visuais.
- **Limitações e Comportamentos Conhecidos**:
  - Algumas fontes legadas governamentais como FTPs do DATASUS (PySUS) podem sofrer instabilidade inerente de upstream (quedas de conexão, timeout ou falha de disco em nuvem pública). O projeto adota `retries` assíncronos no job worker para acomodar essas oscilações.
  - Grandes volumes de dados OpenDataSUS podem consumir memória extensa ou levar minutos. A interface expõe _previews_ por este motivo explícito.

## 3. Execuções Recorrentes

O coração operacional do projeto se apoia no `guaraci/services/jobs.py`:
- Solicitações via API `/jobs` (ou UI) criam operações em *background* não-bloqueantes.
- O ciclo de vida do job pode estar em: `pending`, `running`, `completed`, `failed` e `canceled`.
- Os operadores utilizam os *launchers* na pasta `scripts/desktop/` rotineiramente para controlar o ciclo do serviço.

## 4. Registry e Evidências

Para manter a rastreabilidade (fundamental para diagnóstico por agentes IAs e debugging humano):
- **Registro de Jobs**: Os estados e metadados vitais de todas as requisições ativas ou concluídas persistem em `data/jobs/download_jobs.json`.
- **Manifestos de Output**: Ao fim da extração bem-sucedida, arquivos resultantes vivem sob uma estrutura de `output_dir` do usuário com um respectivo `manifest.json`.
- Estes dois artefatos garantem que nenhum "run" ocorra sem registro de intenção e evidência de conclusão/falha.

## 5. Diagnóstico e Handoff

Quando a operação falhar, a fonte primária de diagnóstico será buscar os rastros do job correspondente e logs baseados em container.

### 5.1 Logs e Diagnóstico
- Logs de estado de progresso estruturados da API podem ser acessados em `/jobs/{job_id}/logs`.
- Logs profundos do container docker podem ser visualizados rodando `docker logs <container-id>` (comumente delegável ao usuário).
- Casos de erro do OpenDataSUS e Crawler tendem a estar bem formatados no próprio frontend, listando `Timeout`, `HTTP Error` ou `Configuration Issue`. 

### 5.2 Handoff e Execuções Custosas (AI Guardrails)
- Agentes atuando no código **não devem tentar assumir downloads gigantes ou bater builds caros** em ambiente de execução bloqueante dentro do seu loop.
- O Agente deve adotar a política de **Handoff Manual**: empacotar comandos Docker (`docker run --rm ...`) ou de PowerShell e **entregar ao usuário humano** instruindo que este rode em sua própria máquina host e devolva o extrato principal dos logs/erros finais.
- Comandos destrutivos, cancelamentos em massa, ou mudanças diretas e longas em pacotes locais devem ser sempre executados pelo **Usuário (Operator)** com comandos explícitos dados pelo Agente.

## 6. Guardrails de UI e Filtros

- Ao expandir fontes, filtros intrínsecos de API sempre devem estar no topo do formulário (ex: `ano`, `doença`).
- Refinamentos ou opções de engenharia (como blocagem de paginação de API ou logs brutos como `keep_raw`) **devem ficar sob Filtros Avançados**, preservando o objetivo principal do projeto de priorizar UX limpa.
- O operador final nunca deve precisar inspecionar as estruturas internas de `guaraci` ou descobrir o destino sozinho: o path resultante (privilegiando *Host Path*, como Desktop) é mandatório na exibição final da operação.


## 7. Encerramento com Sync Automatico

Quando a rodada for finalizada por script de sincronizacao com commit automatico e mensagem generica, o historico legivel da entrega deve estar no `CHANGELOG.md`, nao no `git log`.

Antes do sync, o agente ou operador deve confirmar:

- existe uma entrada nova no topo do `CHANGELOG.md`;
- a entrada lista arquivos tocados, efeito observavel, verificacoes executadas e limitacoes que permanecem;
- mudancas de contrato tambem foram refletidas em docs de arquitetura, API, fontes, UI ou handoff quando aplicavel;
- se o submodule `vogel-stack` foi atualizado, o commit correspondente ja foi publicado no remoto do submodule antes do push do Guaraci.

Essa regra evita que o repositorio pai registre apenas `sync: <maquina> <data>` sem preservar o significado operacional da entrega.
---
? [�ndice da documenta��o](README.md) � [Voltar ao projeto](../README.md)
