# Guia da UI

Painel web desktop em `http://localhost:8002/` (launcher padrao).

## 1) Objetivo da interface

Permitir que usuarios criem e monitorem downloads sem depender de CLI.

A UI cobre:
- selecao de fonte,
- preenchimento de filtros dinamicos,
- criacao de jobs,
- monitoramento de progresso,
- consulta de logs,
- acesso ao caminho de saida,
- cancelamento/retry.

## 2) Layout

A UI tem dois blocos principais:

1. **Novo Job** (wizard 3 passos)
- `1. Fonte`
- `2. Filtros`
- `3. Revisao`

2. **Monitoramento**
- resumo do job selecionado,
- barra de progresso,
- painel de output,
- logs,
- tabela de jobs.

## 3) Passo a passo: criar job

### Passo 1 - Fonte

- Escolha a fonte no select.
- A UI chama `GET /sources/{source}/schema`.
- Mostra modo da fonte (`gov.br crawl` ou `pysus ftp`).

### Passo 2 - Filtros

- Campos sao gerados dinamicamente pelo schema.
- `Diretorio do Download` fica no bloco basico e vem antes de `output_format`.
- Parametros tecnicos/especificos ficam no bloco expansivel `Filtragem avancada`.
- Tipos de campo:
  - `integer` -> input numerico,
  - `boolean` -> checkbox,
  - `string` + `allowed_values` -> select,
  - `string_list` + `allowed_values` -> multi-select,
  - outros -> input texto.
- Icone `?` mostra dica de preenchimento.

### Passo 3 - Revisao

- Mostra fonte, modo e parametros escolhidos.
- Ao confirmar, envia `POST /jobs`.

## 4) Monitoramento em tempo real

A cada intervalo de refresh, a UI consulta:
- `GET /jobs?limit=40`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/logs?limit=120`
- `GET /jobs/{job_id}/output`

Indicadores exibidos:
- status + percentual,
- tentativa,
- arquivos completos / total,
- bytes transferidos,
- tempo decorrido e ETA,
- arquivo atual.

## 5) Tabela de jobs

Acoes por linha:
- `Selecionar`
- `Cancelar`
- `Retry`

Regras:
- `Cancelar` so habilitado para jobs nao terminais.
- `Retry` habilitado apenas para `failed` e `canceled`.

## 6) Output e rastreabilidade

Painel de output mostra:
- pasta de saida,
- formato de exportacao (quando aplicavel),
- quantidade/lista de arquivos exportados,
- aviso de exportacao (`export_warning`) quando nenhum arquivo foi gerado.

Botoes:
- `Copiar Caminho`
- `Abrir Pasta`

Observacao Docker:
- em container, `Abrir Pasta` pode retornar apenas instrucoes.
- use o caminho `host_output_dir` quando fornecido.

## 7) Logs

Formato:
- `[YYYY-MM-DD HH:MM:SS] [LEVEL] mensagem`

Os logs da UI sao eventos da pipeline de job, nao apenas logs de servidor HTTP.

## 8) Dicas por tipo de fonte

### 8.1 SNIS/SINISA (crawler)

- Comece com `file_kinds = planilhas`.
- Use `modules` para reduzir volume.
- `extract_archives = true` para descompactar zip automaticamente.

### 8.2 OpenDataSUS (API)

- Fontes disponiveis: `doses_aplicadas_pni` e `zikavirus`.
- Comece pelos filtros basicos nativos da API: `start_year` e `end_year`.
- Para gerar arquivo final, informe `output_format`.
- Em `Filtragem avancada` ficam os refinamentos/opcoes tecnicas, como:
  - `start_date`, `end_date`,
  - `keep_raw` (padrao desativado),
  - `api_base_url`, `batch_size`, `max_pages`, `resource_id`.
- Para `zikavirus`, o `uf` e tratado como refinamento local e aparece no bloco avancado.
- Se a API retornar HTML ao inves de JSON, ajuste `api_base_url` para um endpoint valido:
  - `https://apidadosabertos.saude.gov.br` (DEMAS)
  - `https://ckan-dadosabertos.saude.gov.br/api/3/action` (CKAN, quando disponivel)

### 8.3 SINAN/SIM/SIH (PySUS)

- Primeiro defina periodo (`start_year`, `end_year`).
- Use grupos/doencas/UF para reduzir cardinalidade.
- Se quiser arquivo final, preencha `output_format`.

## 9) Problemas comuns

### Job fica `running` por muito tempo

- Pode ser rede/FTP lento.
- Verifique logs do job para progresso real.

### Download concluido, mas sem CSV

- Confira `output_format` no payload.
- Verifique `exported_files` e `export_warning` no painel de output.

### Porta 8002 indisponivel

- Suba em outra porta no script de start.

### UI nao carrega fontes

- Verificar `GET /health` e `GET /sources`.
- Verificar container/API ativos.
