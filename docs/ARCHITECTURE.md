# Arquitetura Interna

## 1) Visao geral

O Guaraci usa uma arquitetura em camadas:

1. `datasources`
- Implementam download e leitura dos dados da fonte.
- Exemplos: `SnisDataSource`, `SinisaDataSource`, `SinanDataSource`, `SimDataSource`, `SihDataSource`, `OpenDataSUSDataSource`.

2. `services/downloads`
- Registro de fontes suportadas.
- Schema declarativo de parametros por fonte.
- Validacao e normalizacao de entrada.
- Adaptacao de retorno para `JobResult`.

3. `services/jobs`
- Fila de jobs assincronos.
- Controle de estado/progresso.
- Persistencia em disco.
- Logs estruturados por evento.

4. `api/main`
- Exposicao HTTP dos servicos.
- Entrega de schema para UI dinamica.

5. `api/static/index.html`
- UI web desktop com wizard + monitoramento.

## 2) Modo de execucao

Suporte atual:
- Docker-first: suportado oficialmente.
- Python local sem Docker: WIP.

## 3) Componentes principais

### 3.1 `DownloadService`

Arquivo: `guaraci/services/downloads.py`

Responsabilidades:
- Registrar fontes e expor metadados (`source`, `title`, `mode`).
- Expor schema por fonte (`get_source_schema`).
- Validar params (`validate_source_params`).
- Executar fonte selecionada (`run`).

Tipos de adaptador:
- `GovBrDownloadSource`: para crawler gov.br (`snis`, `sinisa`).
- `PysusDownloadSource`: para PySUS/FTP (`sinan`, `sim`, `sih`).
- `OpenDataSUSDownloadSource`: para API OpenDataSUS (`doses_aplicadas_pni`, `zikavirus`).

### 3.2 `DownloadJobService`

Arquivo: `guaraci/services/jobs.py`

Responsabilidades:
- Criar jobs (`create_job`).
- Executar em thread pool (`_run_job`).
- Cancelar e retry.
- Persistir jobs em `data/jobs/download_jobs.json`.
- Expor logs e output por job.

## 4) Pipeline de execucao de job

1. UI/API envia `POST /jobs` com `source` + `params`.
2. `DownloadJobService` valida params via `DownloadService`.
3. Job entra em `queued`.
4. Worker muda para `running`.
5. `DownloadService.run()` executa a fonte com callback de progresso.
6. Eventos atualizam progresso, bytes, ETA e logs.
7. Finaliza como:
   - `completed` (resultado success/partial_success),
   - `failed` (erro de execucao ou resultado sem sucesso),
   - `canceled`.

## 5) Semantica de status

### 5.1 Status do `JobResult`

Calculado em `guaraci/core/results.py`:
- `success`: sem falhas.
- `partial_success`: com falhas, mas ao menos um download ok.
- `failed`: falhas e nenhum download bem-sucedido.

### 5.2 Status do job assincrono

Em `DownloadJobService`:
- `queued`, `running`, `cancel_requested`, `completed`, `failed`, `canceled`.

Regra importante:
- Se `JobResult.status == failed`, o job final e marcado como `failed` (nao `completed`).

## 6) Modelo de eventos de progresso

Eventos mais relevantes:
- `download_start`
- `file_start`
- `file_progress`
- `file_completed`
- `file_failed`
- `file_skipped`
- `file_extracted`
- `download_complete`

Esses eventos alimentam:
- progresso percentual,
- bytes totais e baixados,
- arquivo atual,
- logs de interface.

## 7) Fontes: diferenca de pipeline

### 7.1 Crawler gov.br (`snis`, `sinisa`)

- Coleta de links HTML.
- Download de arquivos brutos.
- Extracao opcional de zip.
- Manifest gerado no output da fonte.

### 7.2 PySUS (`sinan`, `sim`, `sih`)

- Download via PySUS/FTP.
- Materializacao local de artefatos em `raw/`.
- Exportacao opcional de dataset processado quando `output_format` e informado.
- Resultado inclui `exported_files` e, se vazio, `export_warning`.

### 7.3 OpenDataSUS (`doses_aplicadas_pni`, `zikavirus`)

- Consulta via API OpenDataSUS com cliente HTTP isolado.
- Modo padrao: DEMAS (`https://apidadosabertos.saude.gov.br`) com endpoints anuais `doses-aplicadas-pni-YYYY`.
- Catalogo local (swagger) e usado para resolver endpoints/parametros por fonte quando disponivel.
- `doses_aplicadas_pni` suporta:
  - modo padrao DEMAS,
  - modo opcional CKAN (`.../api/3/action`) via override de `api_base_url`.
- `zikavirus` usa fluxo DEMAS (na pratica, endpoint estatico `/arboviroses/zikavirus`).
- Schema orientado a filtros nativos da API:
  - base: `start_year` + `end_year`,
  - refinamento local opcional: `start_date`, `end_date`, `uf` (quando aplicavel).
- `keep_raw` existe como opcional e tem padrao `false` (gera `raw/` apenas quando habilitado).
- Exportacao opcional `csv|parquet|sqlite` no mesmo fluxo de jobs/UI.

## 8) Persistencia e recuperacao

Jobs sao persistidos em JSON.

Ao reiniciar a API:
- jobs `queued/running/cancel_requested` antigos sao marcados como interrompidos/failed.
- historico permanece consultavel.

## 9) Mapeamento de pasta host (Docker)

Para melhorar UX de "Abrir Pasta":
- launcher injeta:
  - `GUARACI_HOST_APP_ROOT`
  - `GUARACI_CONTAINER_APP_ROOT`
- `jobs.py` converte caminho interno `/app/...` para caminho do host quando possivel (`host_output_dir`).

## 10) Validacao de parametros

Contrato em `guaraci/core/contracts.py`:
- tipo por parametro (`string`, `integer`, `boolean`, `string_list`),
- obrigatoriedade,
- faixa numerica,
- `allowed_values`.

Campos nao suportados sao rejeitados com erro `400` no `POST /jobs`.

## 11) Extensibilidade

Para adicionar nova fonte:
1. implementar datasource,
2. registrar no `DownloadService` com `SourceDescriptor` e schema,
3. adicionar normalizacao/validacao,
4. cobrir com testes,
5. atualizar docs de API/UI/filtros.

## 12) Limitacoes atuais

- Python local sem Docker: WIP.
- Dependencia de disponibilidade de fontes externas (FTP/web).
- UX ainda em evolucao para diferencas entre fontes crawler e fontes tabulares.
