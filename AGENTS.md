# AGENTS: Diretrizes de Trabalho no Guaraci

Este arquivo define direcionamento tecnico para agentes de IA que atuam neste repositorio.

## 1) Contexto do projeto

- Versao atual: `0.5.0`
- Caminho suportado oficialmente: **Docker-first**
- Execucao Python local sem Docker: **WIP** (nao tratar como caminho principal)

## 2) Principios obrigatorios do projeto

1. Preservar o fluxo oficial Docker-first como baseline de desenvolvimento e validacao.
2. Nao quebrar fontes existentes ao evoluir schema, jobs, API ou UI.
3. Toda mudanca relevante deve atualizar testes e documentacao no mesmo ciclo.
4. Mudancas devem ser pequenas, isoladas e preferencialmente feitas em branch de trabalho propria.
5. Quando houver custo operacional alto ou tarefa mecanica pesada, o agente deve preferir preparar os comandos para o usuario executar localmente e devolver a saida relevante.

## 3) Regras de arquitetura

1. Respeitar `DownloadService` + `DownloadJobService`.
2. Toda fonte deve ter:
   - `SourceDescriptor`,
   - schema declarativo com `SourceParameterSpec`,
   - validacao de parametros desconhecidos.
3. Retorno de execucao deve ser compativel com `JobResult`.
4. UI deve continuar dirigida por schema (`/sources/{source}/schema`).

## 4) Diretrizes de produto (filtros e UX)

1. Filtros basicos devem privilegiar parametros nativos da API/fonte.
2. Parametros tecnicos e refinamentos locais devem ir para `Filtragem avancada`.
3. `output_dir` deve permanecer no bloco basico, antes de `output_format`.
4. No launcher desktop, priorizar UX com pasta `Guaraci Downloads`.

## 5) OpenDataSUS (estado atual)

- Fontes: `doses_aplicadas_pni`, `zikavirus`
- Contrato atual:
  - base: `start_year`, `end_year`
  - refinamento opcional: `start_date`, `end_date`, `uf`
  - `keep_raw`: padrao `false`
  - exportacao opcional: `csv|parquet|sqlite`

Regra de nomenclatura:
- nao introduzir aliases para `source`; use apenas nomes canonicos no `DownloadService`.

## 6) Fluxo recomendado de trabalho

1. Confirmar a branch-base e o estado atual do workspace antes de editar.
2. Abrir branch de trabalho para uma melhoria pequena e coerente.
3. Implementar a mudanca preservando contratos existentes.
4. Rodar os testes relevantes em Docker.
5. Atualizar documentacao impactada.
6. Registrar em `IMPROVEMENTS.md` apenas direcoes oficiais do projeto, nao backlog pessoal local.

## 7) Uso eficiente de creditos e execucao local

1. Evitar gastar creditos com tarefas mecanicas, pesadas ou demoradas quando o usuario puder executa-las localmente.
2. Instalacoes, downloads grandes, fetch remoto, build demorado, execucoes longas de teste e comandos dependentes de credenciais podem ser delegados ao usuario com comandos exatos.
3. O agente deve concentrar trabalho em:
   - arquitetura
   - codigo
   - documentacao
   - diagnostico
   - definicao de comandos
4. Quando depender de saida operacional do ambiente do usuario, o fluxo preferencial e:
   - o agente prepara o comando
   - o usuario executa localmente
   - o usuario devolve a saida relevante
   - o agente interpreta e corrige

## 8) Convencoes para comandos PowerShell para o usuario

1. Quando o usuario estiver em Windows ou interoperando com o repositorio local, preferir comandos em PowerShell para tarefas manuais.
2. Os comandos devem ser curtos, copiados em bloco unico e prontos para colar.
3. Sempre que houver diferenca relevante entre `bash` e PowerShell, explicitar a versao em PowerShell.
4. Para tarefas delegadas ao usuario, priorizar:
   - verificacao de estado Git
   - fetch remoto
   - execucao de testes
   - coleta de logs

## 9) Qualidade minima em cada mudanca

1. Nao quebrar fontes existentes.
2. Cobrir com testes (service, API, jobs, datasource quando aplicavel).
3. Atualizar documentacao no mesmo ciclo:
   - `CHANGELOG.md`
   - `README.md`
   - `CONTRIBUTING.md`
   - `docs/ARCHITECTURE.md`
   - `docs/API_REFERENCE.md`
   - `docs/UI_GUIDE.md`
   - `docs/SOURCES_AND_FILTERS.md`
   - `docs/AI_HANDOFF_OPENDATASUS.md`

## 10) Checklist antes de qualquer alteracao

1. Confirmar se a mudanca afeta `DownloadService`, `DownloadJobService`, contratos ou UI schema-driven.
2. Verificar se a fonte usa filtros nativos no bloco basico e refinamentos tecnicos em `Filtragem avancada`.
3. Verificar se a mudanca exigira atualizacao de documentacao.
4. Confirmar se a mudanca altera testes, artefatos ou comportamento de output.
5. Garantir que nao ha segredo, caminho local pessoal ou arquivo temporario sendo introduzido em codigo ou docs.

## 11) Checklist para novas fontes ou evolucoes relevantes

1. Definir `SourceDescriptor`.
2. Declarar schema com `SourceParameterSpec`.
3. Rejeitar parametros desconhecidos pela validacao padrao.
4. Garantir retorno compativel com `JobResult`.
5. Preservar UI dirigida por schema.
6. Cobrir com testes de service, API, jobs e datasource quando aplicavel.
7. Atualizar documentacao impactada.

## 12) Comandos de validacao (Docker)

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v
```

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest \
  tests/test_opendatasus_swagger_catalog.py \
  tests/test_opendatasus_datasource.py \
  tests/test_services.py \
  tests/test_api.py \
  tests/test_jobs.py \
  tests/test_config.py -q
```
