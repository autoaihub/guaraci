# AGENTS: Diretrizes de Trabalho no Guaraci

Este arquivo define direcionamento tecnico para agentes de IA que atuam neste repositorio.

## 1) Contexto do projeto

- Versao atual: `0.6.0`
- Caminho suportado oficialmente: **Docker-first**
- Execucao Python local sem Docker: **WIP** (nao tratar como caminho principal)
- Familia de operacao Vogel Stack: **leve** (sem Graphify/Obsidian versionado; `graphify-out/` e gitignored). Backlog unico em `docs/handoffs/_QUADRO.md`.

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

- Fontes OpenDataSUS: `doses_aplicadas_pni`, `zikavirus`, `dengue`, `chikungunya`, `febre_amarela`, `mpox`, `esavi`, `srag_demas`, `sindrome_gripal_leve` + ~60 fontes DEMAS geradas. (Catalogo completo das 88 fontes: `docs/DATA_DICTIONARY.md` / `guaraci fetch list`.)
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
6. Registrar o backlog no quadro unico `docs/handoffs/_QUADRO.md` (sem `IMPROVEMENTS.md`/`TODO` paralelo; spec longa vira doc proprio linkado).
7. Se a entrega for finalizada por sync automatico com mensagem generica, registrar o significado funcional no topo de `CHANGELOG.md` antes do sync.
8. Se `vogel-stack` for atualizado, garantir que o commit do submodule ja existe no remoto antes de sincronizar o repositorio pai.

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

### 7.1) Orcamento de tokens e alerta antecipado

1. Antes de mergulhar numa tarefa, estimar o custo aproximado de tokens.
2. Se a projecao passar de ~70k tokens, **avisar o usuario logo no inicio** (antes de comecar a executar), explicar o porque e oferecer recortes menores. O usuario decide se vale o gasto.
3. Referencia de calibracao: tarefas bem escopadas (uma feature, um bug, um conjunto de edicoes) custam tipicamente 3k-10k tokens. Estouro muito acima disso quase sempre indica escopo grande demais OU atrito de ambiente (ver 7.2), nao trabalho util.
4. Para reduzir o custo, o usuario pode: declarar a barra de aceitacao logo no pedido (ex.: "build verde basta, sem screenshot"), apontar os arquivos/caminhos relevantes, e fatiar entregas grandes.

### 7.2) Resiliencia a instabilidade de runtime

1. Se as ferramentas comecarem a falhar de forma intermitente (ex.: `ERR_DLOPEN_FAILED`, flush de chamadas duplicadas, saidas repetidas em bloco), **parar cedo e avisar o usuario** em vez de insistir.
2. NAO re-disparar comandos pesados (build completo, `grep`/scan de pasta inteira, leitura de arquivos grandes) durante a instabilidade. Cada saida grande fica no contexto e e **re-cobrada em todo turno seguinte** — re-execucao cega multiplica o custo.
3. Preferir buscas estreitas (arquivo ou linhas especificas) a varreduras de diretorio. Ex.: `grep` em `jobs.py` em vez da pasta `services/` inteira.
4. Quando o usuario souber que o ambiente esta instavel, sinalizar — o agente muda a tatica e para de tentar furar a "janela" de execucao.

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
6. Confirmar se ha submodule envolvido e se o ponteiro novo sera publicavel por quem clonar o repositorio pai.

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
