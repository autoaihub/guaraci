# Changelog

## [0.4.1] - 2026-02-24

### Added
- Fontes OpenDataSUS `doses_aplicadas_pni` e `zikavirus` integradas ao pipeline oficial (`/sources`, schema dinamico, jobs e UI).
- Camada HTTP isolada para OpenDataSUS (`guaraci/opendatasus/client.py`) com tratamento de erros.
- Datasource OpenDataSUS com filtros base por ano (`start_year`, `end_year`) e refinos opcionais (`start_date`, `end_date`, `uf`).
- Parametro `keep_raw` para OpenDataSUS com padrao `false`.
- Exportacao opcional OpenDataSUS em `csv|parquet|sqlite`.

### Changed
- Versao do projeto atualizada para `0.4.1`.
- Documentacao de arquitetura/API/fontes/UI atualizada para incluir OpenDataSUS.
- UI separa filtros basicos e `Filtragem avancada`; `output_dir` fica no bloco basico.
- Launcher desktop passa a centralizar saidas em `Guaraci Downloads` na Area de Trabalho.
- Endpoint default do cliente OpenDataSUS ajustado para DEMAS (`apidadosabertos.saude.gov.br`).
- Aliases de fonte OpenDataSUS (`opendatasus`, `vacinacao_covid19`) removidos para evitar ambiguidade; usar nomes canonicos de source.

## [0.4.0] - 2026-02-24

### Added
- API/UI de jobs com monitoramento de progresso (percentual, bytes, ETA, arquivo atual).
- Endpoints de output com `host_output_dir`, `exported_files`, `output_format` e `export_warning`.
- Materializacao de artefatos PySUS em `raw/` e manifest local.
- Retry de jobs para estados `failed` e `canceled`.
- UI com formulario dinamico por schema de fonte.

### Changed
- Fluxo SNIS principal consolidado em download gov.br (crawler).
- Integracao BigQuery SNIS movida para `legacy`.
- Ordenacao alfabetica de fontes na UI/API.
- Remocao do filtro `ano` do schema de jobs/UI para SINAN/SIH (mantendo `start_year` e `end_year`).
- Documentacao atualizada para Docker-first.

### Fixed
- Validacao de parametros desconhecidos no `POST /jobs` retornando erro `400`.
- Correcoes de robustez no pipeline de exportacao e exibicao de saida.

### Notes
- Execucao Python local sem Docker permanece em WIP (nao suportado oficialmente).

## [0.3.0] - 2025-10-27

### Added
- Integracoes DATASUS para `SIM` e `SIH`.
- CLI dedicada para `sim` e `sih`.
- Exportacao padrao em CSV/Parquet/SQLite para fontes DATASUS.

## [0.2.0] - 2025-10-27

### Added
- Primeira base funcional do projeto com Docker e estrutura modular.
- Integracao inicial de `SINAN`.
- Camada `core` (config, datasource, logging) e testes iniciais.

## [0.1.x] - Legacy

### Notes
- Prototipo inicial fora da estrutura atual, sem historico completo no repositorio.
