# Graph Report - guaraci  (2026-05-17)

## Corpus Check
- 84 files · ~63,970 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1863 nodes · 4075 edges · 132 communities (97 shown, 35 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 292 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1e54bfd3`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 106|Community 106]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 109|Community 109]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 111|Community 111]]
- [[_COMMUNITY_Community 112|Community 112]]
- [[_COMMUNITY_Community 113|Community 113]]
- [[_COMMUNITY_Community 114|Community 114]]
- [[_COMMUNITY_Community 115|Community 115]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]
- [[_COMMUNITY_Community 118|Community 118]]
- [[_COMMUNITY_Community 119|Community 119]]
- [[_COMMUNITY_Community 120|Community 120]]
- [[_COMMUNITY_Community 121|Community 121]]
- [[_COMMUNITY_Community 122|Community 122]]
- [[_COMMUNITY_Community 123|Community 123]]
- [[_COMMUNITY_Community 124|Community 124]]
- [[_COMMUNITY_Community 125|Community 125]]
- [[_COMMUNITY_Community 126|Community 126]]
- [[_COMMUNITY_Community 127|Community 127]]
- [[_COMMUNITY_Community 128|Community 128]]
- [[_COMMUNITY_Community 129|Community 129]]
- [[_COMMUNITY_Community 130|Community 130]]
- [[_COMMUNITY_Community 131|Community 131]]

## God Nodes (most connected - your core abstractions)
1. `DownloadService` - 70 edges
2. `DownloadJobService` - 54 edges
3. `DownloadService` - 42 edges
4. `paths` - 41 edges
5. `JobResult` - 40 edges
6. `get` - 38 edges
7. `OpenDataSUS DataSource` - 36 edges
8. `OpenDataSUSDataSource` - 34 edges
9. `SourceDescriptor` - 32 edges
10. `PysusDownloadSource` - 32 edges

## Surprising Connections (you probably didn't know these)
- `OpenDataSUS Source Parameters` --references--> `OpenDataSUS DataSource`  [INFERRED]
  docs/SOURCES_AND_FILTERS.md → guaraci/opendatasus/datasource.py
- `Guaraci Project Context` --conceptually_related_to--> `DownloadService`  [INFERRED]
  AGENTS.md → guaraci/services/downloads.py
- `AI Agent Guidelines` --references--> `DownloadService`  [EXTRACTED]
  AGENTS.md → guaraci/services/downloads.py
- `test_validate_source_params_accepts_valid_payload()` --calls--> `SourceParameterSpec`  [INFERRED]
  tests/test_contracts.py → guaraci/core/contracts.py
- `test_validate_source_params_rejects_unknown_and_invalid_values()` --calls--> `SourceParameterSpec`  [INFERRED]
  tests/test_contracts.py → guaraci/core/contracts.py

## Communities (132 total, 35 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (53): DownloadManifest, Shared contracts for download sources and manifest serialization., Standardized manifest persisted by download-based sources., Standardized manifest persisted by download-based sources., Standardized manifest persisted by download-based sources., Declarative parameter schema for a download source., Declarative parameter schema for a download source., Validate source input params against a declarative schema. (+45 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (60): content, description, post, application/json, text/csv, parameters, produces, responses (+52 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (26): Guaraci Project Context, AI Agent Guidelines, DownloadService, Gov.br Crawler (SNIS, SINISA), PySUS DataSources (SINAN, SIM, SIH), Facade with source registry and normalized `JobResult` responses., Facade with source registry and normalized `JobResult` responses., Facade with source registry and normalized `JobResult` responses. (+18 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (51): OpenDataSUS Static Catalog, OpenDataSUS DataSource, _annotate_client_error(), _build_dataset_specs(), _build_export_failure_warning(), _candidate_uf_param_names(), _combine_warnings(), DemasEndpointPlan (+43 more)

### Community 4 - "Community 4"
Cohesion: 0.1
Nodes (40): from_payload(), JobResult, Guaraci Download Results ========================  Shared result objects returne, Standard outcome for download jobs., status(), RuntimeError, Human-readable metadata for supported sources., Human-readable metadata for supported sources. (+32 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (37): ABC, DataSource, download(), load_dataframe(), Guaraci Core DataSource ======================  Abstract base class for all data, Abstract base class for all Guaraci data sources., Initialize the data source.          Parameters         ----------         name, Get metadata about this data source. (+29 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (31): 1. Health, 2. Sources, 3. Jobs, 4. Logs and Output, 5. Direct Download Endpoints, 6. Status Semantics, 7. Request Examples, 8. Common Errors (+23 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (49): download(), filter(), info(), Guaraci SIH CLI ===============  CLI interface for SIH (Hospital Information, Filter SIH data with specified criteria., Filter SIH data with specified criteria., Generate summary statistics for SIH data., Generate summary statistics for SIH data. (+41 more)

### Community 8 - "Community 8"
Cohesion: 0.05
Nodes (40): download(), filter(), info(), Guaraci SINAN CLI ================  Modern CLI interface for SINAN data opera, Filter SINAN data with specified criteria., Generate summary statistics for SINAN data., Show information about available fields for a disease., SINAN data operations for Guaraci platform. (+32 more)

### Community 9 - "Community 9"
Cohesion: 0.22
Nodes (23): DownloadService, _CustomSource, Tests for download service orchestration., test_download_sinisa_normalizes_payload(), test_download_snis_normalizes_payload(), test_get_source_schema_rejects_unknown(), test_get_source_schema_returns_common_params(), test_get_source_schema_returns_doses_aplicadas_pni_fields() (+15 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (31): Tests for Guaraci utility functions., Test utility mapping functions., Test mapping of numeric UF codes., Test mapping of string numeric codes., Test that valid UF abbreviations pass through unchanged., Test handling of invalid inputs., Test handling of float inputs., Test UF validation function. (+23 more)

### Community 11 - "Community 11"
Cohesion: 0.32
Nodes (28): cancel_job(), create_job(), download_sinisa(), download_snis(), DownloadResponse, get_job(), get_job_logs(), get_job_output() (+20 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (17): BaseSettings, ensure_log_dir_exists(), ensure_path_exists(), GuaraciConfig, Guaraci Configuration Management ===============================  Centralized co, Main configuration class for Guaraci platform., Get path for specific DATASUS source., Tests for Guaraci configuration system. (+9 more)

### Community 13 - "Community 13"
Cohesion: 0.26
Nodes (24): client(), Tests for Guaraci HTTP API endpoints., Sanity-check a few new sources from each major group., test_cancel_job_endpoint(), test_create_job_endpoint(), test_create_job_endpoint_rejects_invalid_params(), test_download_snis_endpoint(), test_get_job_endpoint_not_found() (+16 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (19): _clean_municipios(), _clean_ufs(), _normalize_field(), _parse_table_id(), _quote_identifier(), Guaraci SNIS Legacy BigQuery Integration =======================================, Download SNIS data for a given year and save to CSV., Export BigQuery schema info to CSV for the SNIS table. (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.16
Nodes (18): OpenDataSUS Client, _classify_http_error(), _classify_url_error_reason(), _decode_json_payload(), _extract_api_error(), _extract_http_error_message(), OpenDataSUSClient, OpenDataSUSClientError (+10 more)

### Community 16 - "Community 16"
Cohesion: 0.1
Nodes (23): load_catalog(), Loader for the OpenDataSUS static source catalog (catalog.yaml)., Load and return all entries from the OpenDataSUS catalog YAML.      Parameters, The catalog must surface every static OpenDataSUS source via the API., test_list_sources_endpoint_includes_all_catalog_sources(), Tests for the OpenDataSUS YAML catalog and its loader., Each catalog entry must produce an OpenDataSUSDatasetSpec., zikavirus has been migrated from manual to catalog-driven. (+15 more)

### Community 17 - "Community 17"
Cohesion: 0.08
Nodes (25): api_base_url, dataset, details, api_mode, batch_size, endpoints, max_pages, pages_scanned (+17 more)

### Community 18 - "Community 18"
Cohesion: 0.33
Nodes (11): Invoke-Start(), Invoke-Status(), Invoke-Stop(), Open-UI(), pause_prompt(), Show-Logs(), Show-Menu(), show_status() (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (20): artifacts, documents_found, extracted_dirs, failed_urls, filters, extract_archives, file_kinds, modules (+12 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (22): generate_source_block(), get_phase_and_type(), main(), Returns (param_type, phase, allowed_values_code) for a given parameter., Tests for local OpenDataSUS swagger catalog helpers., test_discover_get_params_by_path_reads_get_parameters(), test_discover_pni_endpoints_extracts_year_and_uf_params(), test_load_local_get_params_catalog() (+14 more)

### Community 21 - "Community 21"
Cohesion: 0.3
Nodes (13): download(), download_legacy(), Guaraci SNIS CLI ================  CLI for SNIS via gov.br (default) and legacy, Download SNIS from legacy BigQuery integration., Export legacy SNIS BigQuery schema to CSV., List SINISA documents available on the selected results page., SNIS data operations for the Guaraci platform., Download raw SINISA files directly from official gov.br source. (+5 more)

### Community 22 - "Community 22"
Cohesion: 0.06
Nodes (31): 10. Troubleshooting, 11. Development in Docker, 12. Note About Local Python Without Docker, 1. Build the Image, 2.1 Desktop launcher (recommended), 2.2 Manual execution, 2. Execution Modes, 3. Launcher Internal Behavior (+23 more)

### Community 23 - "Community 23"
Cohesion: 0.06
Nodes (31): 10. Template de concepção, 11. Template de wireframe textual, 1. Template de `AGENTS.md`, 2. Template de `quickstart.md`, 3. Template de `docs/arquitetura.md`, 4. Template de `docs/versionamento.md`, 5. Template de `docs/changelog.md`, 6. Template de `docs/fontes-e-filtros.md` (+23 more)

### Community 24 - "Community 24"
Cohesion: 0.06
Nodes (30): Additional Documentation, Architecture Summary, Citation, code:powershell (# 1. Build), code:bash (# General help), code:text (<output_dir>/), code:text (<output_dir>/), code:text (<output_dir>/) (+22 more)

### Community 25 - "Community 25"
Cohesion: 0.18
Nodes (14): SinisaDataSource, _infer_kind(), Guaraci SNIS Integration (gov.br) =================================  Primary SNI, Primary SNIS datasource backed by direct gov.br downloads., Download SNIS raw files from gov.br historical pages., _snis_page_sort_key(), SnisDataSource, Tests for primary SNIS datasource (gov.br direct download). (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.07
Nodes (26): API is up but the UI has no data, Basic Verification, code:bash (git clone https://github.com/autoaihub/guaraci.git), code:bash (# Version), code:powershell (.\scripts\desktop\start-guaraci.ps1), code:powershell (.\scripts\desktop\launcher.ps1), code:bash (./scripts/desktop/start-guaraci.sh), code:bash (./scripts/desktop/launcher.sh) (+18 more)

### Community 27 - "Community 27"
Cohesion: 0.63
Nodes (8): _load_pyproject(), Version consistency checks across project metadata., _repo_root(), test_citation_metadata_matches_current_version_and_author_order(), test_dockerfile_version_label_matches_pyproject(), test_package_version_matches_pyproject(), test_pyproject_authors_are_in_expected_order(), test_readme_mentions_current_version()

### Community 28 - "Community 28"
Cohesion: 0.31
Nodes (4): Tests for shared source contracts and manifest model., test_download_manifest_contains_standard_and_legacy_fields(), test_validate_source_params_accepts_valid_payload(), test_validate_source_params_rejects_unknown_and_invalid_values()

### Community 29 - "Community 29"
Cohesion: 0.53
Nodes (8): Tests for SINISA raw extractor utilities., test_build_manifest_includes_standard_schema(), test_extract_links_only_downloadables(), test_extract_zip_blocks_path_traversal(), test_extract_zip_keeps_only_csv_xlsx(), test_infer_kind_and_module(), test_invalid_filters_raise(), test_list_documents_filters()

### Community 30 - "Community 30"
Cohesion: 0.07
Nodes (26): 1. Current Progress, 2.1 Product direction, 2.2 Technical base, 2.3 OpenDataSUS progress, 2. Main Strengths, 3.1 The repository still has too much diff noise risk, 3.2 The frontend still depends on heuristics, 3.3 Preview quality is uneven across sources (+18 more)

### Community 31 - "Community 31"
Cohesion: 0.15
Nodes (12): documents_found, downloaded_files, extracted_dirs, failed_urls, filters, extract_archives, file_kinds, modules (+4 more)

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (12): documents_found, downloaded_files, extracted_dirs, failed_urls, filters, extract_archives, file_kinds, modules (+4 more)

### Community 34 - "Community 34"
Cohesion: 0.09
Nodes (21): 1. Começar pelas respostas, não pelos widgets, 2. Método recomendado para dashboards, 3. Padrão de leitura recomendado para dashboards operacionais, 4. Triage, diagnóstico e auditoria, 5. Evolução arquitetural em fases, 6. Preservar o fluxo atual durante a transição, 7. Cores, identidade e status, 8. Critério para não desperdiçar tempo com solução legada (+13 more)

### Community 35 - "Community 35"
Cohesion: 0.36
Nodes (5): app(), info(), Guaraci Main CLI ===============  Main command-line interface for the Guaraci pl, 🇧🇷 Guaraci - Brazilian Public Data Integration Platform      A comprehensive too, Show platform information and available data sources.

### Community 36 - "Community 36"
Cohesion: 0.1
Nodes (20): 10. Parameter Validation, 11. Extensibility, 12. Current Limitations, 1. Overview, 2. Execution Mode, 3.1 `DownloadService`, 3.2 `DownloadJobService`, 3. Main Components (+12 more)

### Community 37 - "Community 37"
Cohesion: 0.55
Nodes (5): Tests for standardized download result objects., test_job_result_from_mapping_payload(), test_job_result_from_path_payload(), test_job_result_from_payload_rejects_unknown_type(), test_job_result_statuses()

### Community 38 - "Community 38"
Cohesion: 0.1
Nodes (20): 1. Interface Goal, 2. Layout, 3. Creating a Job, 4. Real-Time Monitoring, 5. Jobs Table, 6. Output and Traceability, 7. Logs, 8.1 SNIS and SINISA (+12 more)

### Community 39 - "Community 39"
Cohesion: 0.24
Nodes (10): Docker-first Principle, Jobs API Endpoints, Sources API, DownloadService, DownloadJobService, DownloadJobService, Guaraci API (FastAPI), Job Creation Form (+2 more)

### Community 40 - "Community 40"
Cohesion: 0.36
Nodes (3): Guaraci Logging System =====================  Centralized logging configurati, Configure logging for Guaraci., setup_logging()

### Community 41 - "Community 41"
Cohesion: 0.22
Nodes (8): generated_at_utc, materialized_paths, output_dir, source, summary, failed_downloads, successful_downloads, total_files

### Community 42 - "Community 42"
Cohesion: 0.22
Nodes (8): generated_at_utc, materialized_paths, output_dir, source, summary, failed_downloads, successful_downloads, total_files

### Community 43 - "Community 43"
Cohesion: 0.1
Nodes (20): 1. Conjunto mínimo de documentos, 2.1 Registry, manifests e evidência operacional, 2. Papel de cada documento, 3. Quando a documentação deve ser atualizada, 4. Distinção entre estado atual, experimental e futuro, 5. Política prática de versionamento, 6. Convenção para versões, 7. Template de versão (+12 more)

### Community 45 - "Community 45"
Cohesion: 0.29
Nodes (7): AI Handoff: OpenDataSUS and Agent Guidelines, API Reference, Internal Architecture, Guaraci Downloader UI, Sources and Filters, UI Guide, Guaraci Project Review

### Community 55 - "Community 55"
Cohesion: 0.1
Nodes (19): 1. Clonar o repositório, 2. Build da imagem Docker, 3. Iniciar o Guaraci, 4. Verificar se está funcionando, 5. Parar o container, 6. Comandos úteis, 7. Problemas comuns, code:powershell (git clone https://github.com/autoaihub/guaraci.git) (+11 more)

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (3): Internal Architecture Overview, Docker Execution Model, Guaraci v0.4.1

### Community 58 - "Community 58"
Cohesion: 0.67
Nodes (3): Operação do Projeto, Operação de Agentes (Vogel Stack), Registro e Evidências Operacionais (Vogel Stack)

### Community 117 - "Community 117"
Cohesion: 0.11
Nodes (17): [0.1.x] - Legacy, [0.2.0] - 2025-10-27, [0.3.0] - 2025-10-27, [0.4.0] - 2026-02-24, [0.4.1] - 2026-02-24, Added, Added, Added (+9 more)

### Community 118 - "Community 118"
Cohesion: 0.11
Nodes (17): Code Standards, code:bash (git clone https://github.com/autoaihub/guaraci.git), code:bash (# Tests), code:bash (docker run --rm -v "$(pwd):/app" guaraci python -m pytest te), code:bash (docker run --rm -v "$(pwd):/app" guaraci python -m pytest te), Contributing to Guaraci, Conventions, Current Structure at a High Level (+9 more)

### Community 119 - "Community 119"
Cohesion: 0.11
Nodes (17): 10. Produto deve ser pensado pelas respostas que precisa entregar, 11. Modos de execução suportados devem ser explícitos, 12. Contratos declarativos são melhores que comportamento implícito, 13. Identificadores canônicos devem prevalecer, 14. UX de filtros deve separar intenção de negócio e refinamento técnico, 15. Semântica de saída deve ser estável e auditável, 16. Evidência operacional deve ser persistida, 1. O comportamento documentado deve refletir o sistema real (+9 more)

### Community 120 - "Community 120"
Cohesion: 0.12
Nodes (16): 1. Fluxo operacional padrão, 2. Política de custo e uso de recursos, 3. Quando o agente deve executar por conta própria, 4. Quando o agente deve preparar para o usuário, 5.1 Matriz de suporte antes de executar, 5.2 Padrão de handoff para execução custosa, 5. Convenção para comandos, 6. Atualizações de progresso (+8 more)

### Community 121 - "Community 121"
Cohesion: 0.12
Nodes (15): 10) Checklist antes de qualquer alteracao, 11) Checklist para novas fontes ou evolucoes relevantes, 12) Comandos de validacao (Docker), 1) Contexto do projeto, 2) Principios obrigatorios do projeto, 3) Regras de arquitetura, 4) Diretrizes de produto (filtros e UX), 5) OpenDataSUS (estado atual) (+7 more)

### Community 122 - "Community 122"
Cohesion: 0.13
Nodes (14): 1. Execution Phases, 2. Supported Sources, 3.1 SNIS (`snis`), 3.2 SINISA (`sinisa`), 3.3 OpenDataSUS (`doses_aplicadas_pni`), 3.4 OpenDataSUS (`zikavirus`), 3.5 SINAN (`sinan`), 3.6 SIM (`sim`) (+6 more)

### Community 123 - "Community 123"
Cohesion: 0.14
Nodes (13): 1.1 Source layer, 1.2 Service layer, 1.3 Asynchronous jobs, 1.4 API and UI, 1. Consolidated Progress, 2. Current Attention Points, 3.1 Short term, 3.2 Medium term (+5 more)

### Community 124 - "Community 124"
Cohesion: 0.14
Nodes (13): 10. Template mínimo de registry, 1. O que este documento cobre, 2. Changelog não substitui registry, 3. Quando um registry é recomendado, 4. Campos mínimos de um registro de execução, 5. Manifesto por run, 6. Estrutura prática recomendada, 7. Relação com agentes (+5 more)

### Community 125 - "Community 125"
Cohesion: 0.17
Nodes (11): 1. Current State (`0.4.1`), 2.1 `doses_aplicadas_pni`, 2.2 `zikavirus`, 2. Current OpenDataSUS Contract, 3. Implementation Principles for AI Agents, 4. Key Files for Evolution, 5. Quick Checklist for OpenDataSUS Changes, 6. Useful Validation Commands (Docker) (+3 more)

### Community 126 - "Community 126"
Cohesion: 0.17
Nodes (11): Boas praticas para aplicar melhorias localmente, Checklist antes de codar, Estado de partida observado localmente, Ideias de branches futuras, Melhorias prioritarias, P0. Confiabilidade e manutencao operacional, P1. Evolucao de produto e UX, P2. Expansao funcional (+3 more)

### Community 127 - "Community 127"
Cohesion: 0.2
Nodes (9): 1. Caminho Oficialmente Suportado, 2. Pré-requisitos e Limites Conhecidos, 3. Execuções Recorrentes, 4. Registry e Evidências, 5.1 Logs e Diagnóstico, 5.2 Handoff e Execuções Custosas (AI Guardrails), 5. Diagnóstico e Handoff, 6. Guardrails de UI e Filtros (+1 more)

### Community 128 - "Community 128"
Cohesion: 0.2
Nodes (9): 1. Scope, 2. Upstream Data Sources, 3. Legal and Ethical Use, 4. Data Quality and Fitness, 5. No Government Affiliation, 6. Attribution and Citation, 7. Warranty Disclaimer, 8. Limitation of Responsibility (+1 more)

### Community 129 - "Community 129"
Cohesion: 0.22
Nodes (8): Arquitetura e API, Contexto geral do projeto, Contexto para IA, Histórico e planejamento, Legais, Primeiros passos, Technical Documentation, UI e UX

### Community 130 - "Community 130"
Cohesion: 0.25
Nodes (7): 0.1.x - Legado / Experimental, 0.2.x - Estabelecimento do Baseline, 0.3.x - Expansão de Fontes DATASUS, 0.4.x - Fase Operacional Avançada e OpenDataSUS, Histórico de Versões e Fases do Produto, Política de versionamento, Versionamento do Projeto

### Community 131 - "Community 131"
Cohesion: 0.33
Nodes (5): Como usar, Escopo, Estrutura, Propósito, Vogel Stack

## Knowledge Gaps
- **617 isolated node(s):** `🇧🇷 Guaraci - Brazilian Public Data Integration Platform      A comprehensive too`, `Show platform information and available data sources.`, `SIH data operations for Guaraci platform.`, `Download SIH data for specified years, groups, states and months.`, `Filter SIH data with specified criteria.` (+612 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **35 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SnisDataSource` connect `Community 25` to `Community 0`, `Community 2`, `Community 4`, `Community 5`, `Community 9`, `Community 21`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `DownloadService` connect `Community 2` to `Community 0`, `Community 3`, `Community 4`, `Community 39`, `Community 9`, `Community 11`, `Community 25`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `SinanDataSource` connect `Community 8` to `Community 12`, `Community 5`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `DownloadService` (e.g. with `SourceParameterSpec` and `DownloadManifest`) actually correct?**
  _`DownloadService` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `DownloadJobService` (e.g. with `JobResult` and `DownloadService`) actually correct?**
  _`DownloadJobService` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `DownloadService` (e.g. with `DownloadManifest` and `SourceParameterSpec`) actually correct?**
  _`DownloadService` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `JobResult` (e.g. with `SourceDescriptor` and `DownloadSource`) actually correct?**
  _`JobResult` has 29 INFERRED edges - model-reasoned connections that need verification._