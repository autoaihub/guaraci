# Fontes e Filtros

Documento de referencia dos parametros expostos via schema/API/UI.

## 1) Conceito de fases

Para fontes PySUS, parametros podem atuar em fases diferentes:

- **Coleta/download**: quais arquivos buscar.
- **Exportacao/filtro**: como filtrar dataset final antes de exportar.

Na UI esses campos aparecem juntos, mas semanticamente sao fases distintas.

## 2) Fontes suportadas

- `snis` (modo `gov.br crawl`)
- `sinisa` (modo `gov.br crawl`)
- `doses_aplicadas_pni` (modo `opendatasus api`)
- `zikavirus` (modo `opendatasus api`)
- `sinan` (modo `pysus ftp`)
- `sim` (modo `pysus ftp`)
- `sih` (modo `pysus ftp`)

Convencao:
- use sempre o `source` canonico retornado por `GET /sources`.

## 3) Parametros por fonte (schema de jobs/UI)

### 3.1 SNIS (`snis`)

| Parametro | Tipo | Fase | Observacao |
|---|---|---|---|
| `output_dir` | string | download | Pasta de saida (padrao: `Guaraci Downloads` na Area de Trabalho) |
| `results_url` | string | download | URL customizada da pagina base |
| `file_kinds` | string_list | download | `planilhas`, `relatorios`, `glossarios`, `atestados`, `all` |
| `modules` | string_list | download | `gestao_municipal`, `agua`, `esgoto`, `residuos`, `aguas_pluviais` |
| `extract_archives` | boolean | download | Extrair zip |
| `overwrite` | boolean | download | Sobrescrever arquivos existentes |
| `timeout` | integer | download | Timeout HTTP |

### 3.2 SINISA (`sinisa`)

Mesmo schema base do SNIS (gov.br crawler).

### 3.3 OpenDataSUS (`doses_aplicadas_pni`)

| Parametro | Tipo | Fase | Observacao |
|---|---|---|---|
| `output_dir` | string | download | Pasta de saida (padrao: `Guaraci Downloads` na Area de Trabalho) |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Ano inicial da consulta (filtro base) |
| `end_year` | integer | download | Ano final da consulta (filtro base) |
| `uf` | string | download/refino | UF opcional (ex.: `SP`) |
| `start_date` | string | refino local | Data inicial opcional (`YYYY-MM-DD`) dentro da janela de anos |
| `end_date` | string | refino local | Data final opcional (`YYYY-MM-DD`) dentro da janela de anos |
| `keep_raw` | boolean | download | Salvar `raw/*.jsonl` (padrao: `false`) |
| `batch_size` | integer | download | Paginacao da API |
| `max_pages` | integer | download | Limite de paginas por ano (controle de volume/tempo) |
| `resource_id` | string | download | Override opcional do recurso CKAN |
| `api_base_url` | string | download | Override opcional da base API |

### 3.4 OpenDataSUS (`zikavirus`)

| Parametro | Tipo | Fase | Observacao |
|---|---|---|---|
| `output_dir` | string | download | Pasta de saida (padrao: `Guaraci Downloads` na Area de Trabalho) |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Ano inicial da consulta (filtro base) |
| `end_year` | integer | download | Ano final da consulta (filtro base) |
| `start_date` | string | refino local | Data inicial opcional (`YYYY-MM-DD`) dentro da janela de anos |
| `end_date` | string | refino local | Data final opcional (`YYYY-MM-DD`) dentro da janela de anos |
| `uf` | string | refino local | UF opcional (ex.: `SP`) |
| `keep_raw` | boolean | download | Salvar `raw/*.jsonl` (padrao: `false`) |
| `batch_size` | integer | download | Paginacao da API |
| `max_pages` | integer | download | Limite de paginas (controle de volume/tempo) |
| `api_base_url` | string | download | Override opcional da base API |

Observacoes OpenDataSUS:
- Diretriz atual: filtros basicos devem privilegiar parametros nativos da API.
- Refinos locais (ex.: `start_date`, `end_date`, `uf` em fontes sem suporte direto) ficam no bloco avancado da UI.

### 3.5 SINAN (`sinan`)

| Parametro | Tipo | Fase | Observacao |
|---|---|---|---|
| `output_dir` | string | download | Pasta de saida |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Ano inicial |
| `end_year` | integer | download | Ano final |
| `diseases` | string_list | download | Lista de doencas suportadas |
| `uf` | string | exportacao | Filtro por UF |
| `municipio` | string | exportacao | Filtro textual |
| `sexo` | string | exportacao | `M` ou `F` |
| `faixa_etaria` | string | exportacao | Codigo de faixa |
| `evolucao` | string | exportacao | Filtro evolucao |
| `classificacao` | string | exportacao | Filtro classificacao |

Observacao:
- O campo `ano` foi removido do schema de jobs/UI.
- O recorte temporal no fluxo de jobs/UI e feito por `start_year` + `end_year`.

### 3.6 SIM (`sim`)

| Parametro | Tipo | Fase | Observacao |
|---|---|---|---|
| `output_dir` | string | download | Pasta de saida |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Ano inicial |
| `end_year` | integer | download | Ano final |
| `groups` | string_list | download | Grupos SIM |
| `states` | string_list | download | Lista de UFs na coleta |
| `uf` | string | exportacao | UF no dataset final |
| `municipio` | string | exportacao | Filtro textual |
| `sexo` | string | exportacao | `M` ou `F` |
| `causa_basica` | string | exportacao | Causa basica |
| `ano_obito` | integer | exportacao | Ano de obito |

### 3.7 SIH (`sih`)

| Parametro | Tipo | Fase | Observacao |
|---|---|---|---|
| `output_dir` | string | download | Pasta de saida |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Ano inicial |
| `end_year` | integer | download | Ano final |
| `groups` | string_list | download | Grupos SIH |
| `states` | string_list | download | Lista de UFs na coleta |
| `months` | string_list | download | Meses na coleta (1-12) |
| `uf` | string | exportacao | UF no dataset final |
| `municipio` | string | exportacao | Filtro textual |
| `sexo` | string | exportacao | `M` ou `F` |
| `mes` | integer | exportacao | Mes no dataset final |

Observacao:
- `ano` nao faz parte do schema de jobs/UI de SIH.

## 4) Diferencas relevantes UI/API x CLI

A UI/API de jobs segue estritamente o schema de `DownloadService`.

A CLI direta por fonte (`sinan_cli`, `sim_cli`, `sih_cli`) pode expor opcoes adicionais historicas.
Exemplo atual:
- `sih_cli` ainda possui `--ano` para filtro local de dataframe.

## 5) Legacy SNIS (BigQuery)

O fluxo legado existe na CLI:
- `python -m guaraci.cli.snis_cli download-legacy`
- `python -m guaraci.cli.snis_cli schema-legacy`

Codigo legado:
- `guaraci/snis/legacy/bigquery.py`

Nao e o fluxo principal recomendado para SNIS atual.

## 6) Boas praticas de uso

1. Sempre comece com periodo e filtros de menor escopo.
2. Defina `output_format` apenas quando realmente precisar exportacao final.
3. Para crawler, use `modules` + `file_kinds` para reduzir ruido.
4. Acompanhe `export_warning` para detectar exportacao sem resultado.
