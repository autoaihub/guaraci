# Melhorias do Projeto

Este documento registra o progresso ja implementado e os proximos focos tecnicos.

## 1) Progresso consolidado

### 1.1 Camada de fontes

- `snis` e `sinisa` via crawler gov.br com manifest.
- `sinan`, `sim` e `sih` via PySUS/FTP.
- OpenDataSUS com fontes canonicas:
  - `doses_aplicadas_pni`
  - `zikavirus`
- `snis` legado BigQuery isolado em `guaraci/snis/legacy/`.

### 1.2 Camada de servicos

- Registro de fontes com schema declarativo por parametro.
- Validacao de parametros com rejeicao de campos desconhecidos.
- Separacao de parametros de coleta vs pos-processamento (PySUS).
- OpenDataSUS com contrato orientado a filtros nativos:
  - base: `start_year`, `end_year`
  - refinamento local opcional: `start_date`, `end_date`, `uf`
  - `keep_raw` com padrao `false`
- Remocao de aliases de source OpenDataSUS para reduzir ambiguidade.
- Materializacao de artefatos PySUS para pasta local (`raw/`).
- Exportacao opcional (`csv`, `parquet`, `sqlite`) para fontes PySUS e OpenDataSUS.

### 1.3 Jobs assincronos

- Fila de jobs com execucao em background.
- Estados, cancelamento e retry.
- Persistencia de historico de jobs em JSON.
- Progresso com percentual, bytes, arquivo atual e ETA.
- Logs estruturados por evento.

### 1.4 API e UI

- API FastAPI com endpoints para schema, jobs, logs e output.
- UI web com formulario dinamico por fonte.
- UI com separacao de filtros basicos e bloco `Filtragem avancada`.
- `output_dir` no bloco basico antes de `output_format`.
- Monitoramento de jobs e saida no painel.
- Exibicao de `exported_files` e `export_warning` no output.

## 2) Pontos de atencao atuais

1. Execucao local sem Docker
- Status: WIP.
- Risco: inconsistencias de dependencias/ambiente.

2. UX entre fontes heterogeneas
- Fontes crawler e PySUS tem semanticas diferentes.
- OpenDataSUS adiciona variacao entre filtros nativos e refinamentos locais.
- Necessario continuar refinando linguagem e agrupamento de filtros para usuarios leigos.

3. Confiabilidade externa
- Fontes FTP/web podem oscilar.
- Precisamos ampliar observabilidade e estrategias de reprocessamento.

## 3) Direcao recomendada (proximas etapas)

### 3.1 Curto prazo

- Refinar UX da UI por tipo de fonte (crawler x API/FTP).
- Melhorar mensagens de erro orientadas ao usuario final.
- Expandir cobertura de testes para cenarios de falha de exportacao e rede.
- Ampliar cobertura de regressao para comportamento de progresso/log em fontes API.

### 3.2 Medio prazo

- Catologo de fontes plugavel com metadata mais rica (descricao funcional por campo).
- Melhorar classificacao de filtros por fase:
  - coleta,
  - transformacao,
  - exportacao.
- Expandir integracao OpenDataSUS para novos datasets mantendo filtros basicos nativos por fonte.
- Padronizar manifest para todas as fontes.

### 3.3 Longo prazo

- Estrategia de distribuicao desktop para usuario final nao tecnico.
- Fluxo de instalacao simplificado com foco em operacao assistida.
- Eventual suporte local sem Docker quando estabilidade for comprovada.

## 4) Criterios de pronto para novas fontes

Uma nova fonte deve entrar com:

- schema declarativo de parametros,
- validacao forte de entrada,
- retorno padronizado `JobResult`,
- preferencia por filtros basicos nativos da fonte (evitando aliases opacos),
- cobertura minima de testes,
- documentacao atualizada em:
  - `README.md`
  - `CHANGELOG.md`
  - `AGENTS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/SOURCES_AND_FILTERS.md`
  - `docs/API_REFERENCE.md`
  - `docs/UI_GUIDE.md` (quando houver impacto de UX)
  - `docs/AI_HANDOFF_OPENDATASUS.md`

## 5) Observacao de suporte

A base funcional atual e **Docker-first**.
Qualquer passo fora desse fluxo deve ser tratado como experimental ate que haja validacao formal.
