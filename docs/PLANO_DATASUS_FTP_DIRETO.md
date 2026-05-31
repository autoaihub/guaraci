# Plano: Conexão Direta ao DATASUS FTP (sem PySUS)

Status: **fases 1 a 4 implementadas (2026-05-28)**. Camada
`guaraci/datasus/ftp/` é agora o caminho padrão das três fontes DATASUS;
`SihDataSource`, `SimDataSource` e `SinanDataSource` chaveiam via env
`GUARACI_DATASUS_BACKEND={ftp|pysus}` (**default `ftp`** desde a fase 4).
O caminho PySUS legado continua instalável por 1 release via o extra
`datasus-legacy` e selecionável via `GUARACI_DATASUS_BACKEND=pysus`.
Só a Fase 5 (remoção do legado) aguarda.

> **Atenção — gates formais ainda não cumpridos.** O flip de default da
> Fase 4 foi autorizado pelo operador, mas os dois critérios de saída
> originais permanecem **pendentes**: (a) igualdade bit-exata vs PySUS em
> arquivo de referência (§ Fase 1) e (b) 1 semana de validação operacional
> em produção com `backend=ftp` (§ Fase 2). O flip é reversível numa única
> variável — `GUARACI_DATASUS_BACKEND=pysus` — enquanto o extra
> `datasus-legacy` existir. Reverter o default exige apenas trocar
> `DEFAULT_BACKEND` em `guaraci/datasus/backend.py`.

Wikilinks: [[principios|Princípios Gerais]] (princípio 20, fonte
primária), [[operacao-agentes|Operação de Agentes]] (handoff em
coletas pesadas), [[evolucao-produto|Evolução de Produto e Arquitetura]],
[[documentacao-e-versionamento|Documentação e Versionamento]].

## 1. Motivação

O Guaraci hoje consome DATASUS por intermédio do pacote `pysus` (≥2.1.0,
extra `dbc`). PySUS é um wrapper sobre `ftp.datasus.gov.br` que adiciona
descoberta, conversão DBC→parquet e uma API assíncrona. Não é um
intermediário curador — é um cliente — e portanto **não viola o
princípio 20**. Ainda assim, há custos:

- **Superfície indireta** sobre uma fonte primária estável (FTP DATASUS
  responde com `ftplib` sem nenhuma camada extra desde os anos 90).
- **Dependências pesadas**: `pysus[dbc]` arrasta `duckdb`, `duckdb-engine`,
  `fastparquet`, `pyreaddbc`, `python-magic`, `wget`, `boto3`-correlatos.
  Confirmado em `uv sync --extra datasus`: ~20 pacotes transitivos.
- **Surpresas operacionais conhecidas** (registradas em
  `docs/operacao.md §2`): instabilidade de timeout, comportamento de
  retries opaco em quedas FTP.
- **Acoplamento à API interna do PySUS** (`pysus.api.ftp.client`,
  `pysus.api.ftp.databases.SIH`, `pysus.api.ftp.models.File`,
  `PySUS.download_to_parquet`). Mudanças entre versões do PySUS quebram
  o código do Guaraci sem aviso prévio.

A migração para FTP direto remove essa camada de mediação **mantendo a
mesma fonte primária** (`ftp.datasus.gov.br`). É refinamento do
princípio 20, não substituição de fonte.

## 2. Evidência de viabilidade

Smoke test realizado em 2026-05-28 (registrado nesta sessão):

```python
import ftplib
ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=30)
ftp.login()                       # anônimo, sem credencial
ftp.cwd("/dissemin/publicos/SIHSUS/200801_/Dados/")
files = ftp.nlst()                # 22.483 arquivos
size = ftp.size("RDSP2401.dbc")   # 16.65 MB
ftp.quit()
```

Caminhos confirmados:

- `/dissemin/publicos/SIHSUS/199201_200712/Dados/` — 1992–2007 (CID‑9)
- `/dissemin/publicos/SIHSUS/200801_/Dados/` — 2008+ (CID‑10)
- `/dissemin/publicos/SIM/CID10/DORES/` — SIM CID‑10
- `/dissemin/publicos/SINAN/DADOS/FINAIS/` — SINAN consolidado
- `/dissemin/publicos/SINAN/DADOS/PRELIM/` — SINAN preliminar

Padrão de nome SIH: `<GRUPO><UF><YY><MM>.dbc` (ex.: `RDSP2401.dbc`).
Padrão equivalente em SIM e SINAN, com variações por sistema documentadas
na wiki DATASUS.

## 3. Arquitetura proposta

Novo pacote `guaraci/datasus/ftp/` substituindo paulatinamente a camada
PySUS. Quatro responsabilidades separadas:

```
guaraci/datasus/ftp/
├── client.py          # wrapper fino sobre ftplib (connect, list, size, download)
├── catalog.py         # parsing de nome de arquivo → (grupo, uf, ano, mês)
├── discovery.py       # listagem filtrada por grupo/UF/ano/mês
├── dbc.py             # decodificador DBC → DataFrame (via pyreaddbc OU implementação nativa)
└── source.py          # implementação de SihDataSource/SimDataSource/SinanDataSource
```

Cada módulo é testável isoladamente. `client.py` não conhece SIH/SIM —
só FTP. `catalog.py` não conhece DBC — só regex. `dbc.py` não conhece
FTP — só bytes → DataFrame.

### 3.1 `client.py` — FTP wrapper

```python
class DatasusFtpClient:
    HOST = "ftp.datasus.gov.br"

    async def connect(self) -> None: ...
    async def list_dir(self, path: str) -> list[FtpEntry]: ...
    async def size(self, path: str) -> int: ...
    async def download(self, path: str, dest: Path,
                       progress: Callable[[int, int], None] | None = None) -> Path: ...
    async def close(self) -> None: ...
```

Async via `aioftp` (já no ecossistema do projeto) ou `asyncio.to_thread`
sobre `ftplib`. Retries com backoff exponencial nativos. Não confia em
`aioftp.list()` para parsing — usa `NLST` + `SIZE` explícitos, mais
confiável historicamente no FTP DATASUS.

### 3.2 `catalog.py` — Identidade de arquivo

Regex compilados para cada sistema (SIH, SIM, SINAN) extraindo grupo,
UF, ano e mês a partir do basename. Retorna `FileRecord` imutável,
serializável em JSON. **Single source of truth** para parsing — hoje
está espalhado em `pysus.api.ftp.models` e implícito no código do
Guaraci.

### 3.3 `discovery.py` — Listagem filtrada

```python
async def discover_sih(
    client: DatasusFtpClient,
    *, years: Sequence[int],
    groups: Sequence[str] | None = None,
    states: Sequence[str] | None = None,
    months: Sequence[int] | None = None,
) -> list[FileRecord]:
    ...
```

Lista os 2 diretórios SIH (legado + atual), aplica filtros e devolve
`FileRecord` ordenados. Equivalente ao `_discover_files()` atual em
`guaraci/datasus/sih.py:104`, mas reutilizável para SIM e SINAN.

### 3.4 `dbc.py` — Decodificador DBC

Duas opções, a decidir na fase 1:

**Opção A — manter `pyreaddbc`** (recomendada para reduzir risco)
- Já é dependência transitiva do `pysus[dbc]`, comprovadamente
  funcional.
- Promovê-la para dependência direta do Guaraci.
- `dbc.py` se torna apenas uma fachada de 30 linhas em torno de
  `pyreaddbc.read_dbc()`.
- Remove `pysus`, `wget`, `duckdb`, `boto3`-correlatos das deps.

**Opção B — decodificador DBC nativo Python**
- Especificação DBC é pública (compressão pkware do DBF).
- Existem implementações de referência em C (`blast.c` do zlib) e Python
  (`datasus-dbc`, ~200 LoC).
- Remove a única dependência C/Rust restante do pipeline.
- Risco: corner cases em arquivos antigos DATASUS (1990s) que `pyreaddbc`
  já trata silenciosamente.

A decisão entre A e B é não bloqueante para a fase 1. A interface
`dbc.read(path: Path) -> polars.DataFrame` é a mesma.

### 3.5 `source.py` — Refatoração de `SihDataSource`

`guaraci/datasus/sih.py` hoje (linhas 40–200) mistura: FTP discovery,
download, conversão DBC, carregamento Polars, filtros, export. O plano
divide em:

- `BaseFtpDataSource` em `guaraci/datasus/ftp/source.py` — orquestração
  comum (discover → download → decode → filter → export).
- `SihDataSource`, `SimDataSource`, `SinanDataSource` — apenas declaram
  `ROOT_PATHS`, `ALL_GROUPS`, `FILENAME_PATTERN`. Resto é herdado.

Resultado: SIH passa de ~250 linhas para ~40. SIM e SINAN ganham
funcionalidade gratuita (descoberta paralela, retry uniforme, filtro
por mês que hoje só SIH tem).

## 4. Contratos preservados

- **API HTTP**: `GET /sources/{source}/schema`, `POST /jobs`,
  `GET /jobs/{id}` — sem mudança. Schema `SourceParameterSpec` continua
  igual.
- **CLI**: `guaraci sih download`, `guaraci sim download`,
  `guaraci sinan download` — flags inalteradas.
- **UI**: `apps/web/` e `guaraci/api/static/index.html` não precisam
  saber da migração. Apenas o `mode` retornado por `GET /sources` muda
  de `pysus ftp` para `datasus ftp` (não-quebrante, descritivo).
- **Manifest e formato de saída**: parquet com schema idêntico.

## 5. Comparativo PySUS × FTP direto

| Dimensão                 | PySUS (atual)                          | FTP direto (proposta)                  |
|--------------------------|----------------------------------------|----------------------------------------|
| Dependências adicionadas | ~20 pacotes (`pysus[dbc]` + transitivos)| 2 pacotes (`pyreaddbc`, `dbfread`); FTP via `ftplib` da stdlib |
| Tamanho do env (`uv sync`)| ~280 MB                                | ~30 MB (estimativa)                    |
| Controle sobre retries   | Indireto (config do PySUS)             | Direto (config do projeto)             |
| Auditoria do que é baixado| Logs do PySUS                          | Logs do próprio Guaraci                |
| Bus factor               | 1 mantenedor externo (PySUS)           | Stdlib + 1 pacote pequeno (`pyreaddbc`)|
| Curva de aprendizado     | Conhecer API PySUS                     | Conhecer protocolo FTP (RFC 959)       |
| Risco de breakage        | Mudança em release do PySUS            | Mudança no FTP DATASUS (raríssima)     |
| Suporte a paralelismo    | Limitado pelo `_fetch_content` interno | Total — abrir N conexões FTP em pool   |

## 6. Fases de migração

Cada fase é incremental, reversível e mantém o caminho PySUS
funcionando até o fim.

### Fase 0 — Aprovação e teste isolado (este documento) ✅
- Aprovação do plano por humano. ✅ (2026-05-28)
- Criação de uma branch `feat/datasus-ftp-direto`. ✅

### Fase 1 — Camada `ftp/` paralela ✅
- Implementar `client.py`, `catalog.py`, `discovery.py`, `dbc.py`. ✅
- Tests: smoke test contra FTP real (1 arquivo SP/2024-01),
  parsing de catalog com fixtures, decodificação DBC contra arquivo
  fixo de regressão. ✅
- Nenhuma mudança em `SihDataSource` ainda. ✅
- Critério de saída: download de 1 arquivo via `ftp/` produz parquet
  idêntico ao PySUS (mesmo número de linhas, mesmo schema, mesmas
  primeiras 100 linhas após sort canônico).
  - **Status (2026-05-28)**: smoke test
    `tests/test_ftp_smoke.py::test_smoke_download_and_decode_rdsp2401`
    baixou `RDSP2401.dbc` (~16,7 MB) e decodificou para `pl.DataFrame`
    não-vazio com colunas UF. **Igualdade bit-exata vs PySUS ainda não
    foi verificada** — `pysus==2.2.0` removeu o extra `[dbc]` e
    refatorou o pipeline de conversão, então a comparação direta exige
    pinar PySUS 2.1.x num venv separado. Recomendação: registrar como
    pré-requisito da Fase 2 antes do flip da flag em produção.

### Fase 2 — Migração de `SihDataSource` ✅
- Adicionar flag interna `GUARACI_DATASUS_BACKEND=ftp|pysus` (default
  `pysus`). ✅
- `SihDataSource` consulta a flag e delega para a camada correta. ✅
- Cobertura paralela: mesma suite de tests roda nos dois backends. ✅
  - PySUS path: `tests/test_sih_datasource.py` (default, sem mudanças).
  - FTP path: `tests/test_sih_backend_ftp.py` (orquestrador com fakes)
    e `tests/test_sih_backend_switch.py` (dispatch via env var).
- Critério de saída: jobs reais via UI rodam com `backend=ftp` sem
  regressão funcional por 1 semana operacional.
  - **Status (2026-05-28)**: 16 testes da fase 2 verdes, suite cheia
    275 passed. Validação operacional em produção ainda **pendente** —
    é o gating real para a Fase 4 (flip default).

### Fase 3 — Migração de `SimDataSource` e `SinanDataSource` ✅
- Rotear SIM/SINAN pelo backend FTP atrás da mesma flag. ✅
  - **Nota de implementação**: em vez da herança de `BaseFtpDataSource`
    esboçada em §3.5, seguiu-se o padrão já validado em SIH — módulos
    `guaraci/datasus/ftp/sim_backend.py` e `sinan_backend.py` + dispatch
    por env no `download()` de cada fonte. Menos refator, mesma cobertura.
- Mesma flag, mesmos critérios. ✅
- Seletor compartilhado extraído para `guaraci/datasus/backend.py` (leaf
  sem dependências) para que as três fontes consultem o mesmo contrato. ✅

### Fase 4 — Default flip ✅
- `GUARACI_DATASUS_BACKEND=ftp` vira default
  (`DEFAULT_BACKEND = BACKEND_FTP` em `guaraci/datasus/backend.py`). ✅
- `pysus[dbc]` sai do extra `datasus` em `pyproject.toml`; o extra passa a
  declarar apenas `pyreaddbc` + `dbfread`. ✅
- Caminho legado permanece disponível por 1 release via o novo extra
  `datasus-legacy` (`pysus>=2.2.0`) e a flag `GUARACI_DATASUS_BACKEND=pysus`. ✅
- **Gates de saída ainda pendentes** (ver alerta no topo): igualdade
  bit-exata e validação operacional de 1 semana não foram cumpridas; o flip
  foi autorizado mesmo assim, com reversão de uma variável.

### Fase 5 — Remoção do legado
- Remoção do código PySUS-specific após 2 releases sem reclamação.
- `extras.datasus` passa a depender apenas de `aioftp` e `pyreaddbc`.

## 7. Riscos e mitigações

| Risco                                              | Probabilidade | Impacto | Mitigação                                                                                  |
|----------------------------------------------------|---------------|---------|--------------------------------------------------------------------------------------------|
| FTP DATASUS quebra protocolo (improvável)          | Muito baixa   | Alto    | Manter caminho PySUS como fallback por 2 releases pós-flip                                 |
| `pyreaddbc` deprecated/abandonado                  | Baixa         | Médio   | Opção B (decoder nativo) já mapeada; fork mantido em última instância                      |
| Encoding latin-1 vs utf-8 em arquivos antigos      | Alta          | Baixo   | Testes de regressão cobrem 1992–2026 com 1 arquivo por década                              |
| Performance pior em paralelismo agressivo (rate-limit DATASUS) | Média | Médio   | Pool com tamanho configurável (default 4); telemetria de tempo por arquivo                 |
| Refatoração esconde regressão silenciosa em filtros| Média         | Alto    | Critério de saída da fase 1 é igualdade bit-exata pós-sort em 1 arquivo de referência       |
| Migração compete com a release de v0.6.0           | Alta          | Médio   | Plano não bloqueia roadmap — fase 0 e 1 podem rodar em paralelo a outras frentes           |

## 8. O que NÃO está em escopo

- **Filtro server-side por CID** — impossível no FTP DATASUS. Continua
  sendo stream-filter local (baixa → filtra → mantém só o relevante).
- **Substituir OpenDataSUS** — esse caminho já é HTTP REST direto, sem
  PySUS, sem mudança.
- **Substituir o crawler gov.br (SNIS/SINISA)** — mesmo motivo.
- **Cache distribuído de arquivos baixados** — discussão separada,
  ligada a `docs/operacao.md §5.2` (handoff em coletas pesadas).

## 9. Decisões da fase 0 (registradas 2026-05-28)

Decididas pelo operador após revisão deste plano:

1. **Backend FTP da fase 1**: `asyncio.to_thread(ftplib)` da stdlib.
   - Motivação: o smoke test em `scripts/discover_sih_rd.py` já comprova
     que `ftplib` funciona contra o DATASUS sem ajustes. Adicionar
     `aioftp` na fase 1 mistura validação de protocolo com validação de
     dependência nova.
   - Critério para migrar para `aioftp` em fase posterior: se o pool de
     N conexões serializadas em threads encontrar contention real (perfil
     mostrar tempo em GIL > tempo em rede) ou se o DATASUS aceitar mais
     conexões simultâneas do que threads práticas no event loop.

2. **Decoder DBC**: **Opção A** — `pyreaddbc` promovido a dependência
   direta.
   - Motivação: já é dependência transitiva comprovadamente funcional,
     trata corner cases históricos (1992–1997) que um decoder nativo
     novo precisaria aprender. Reduz risco da fase 1 sem nos prender ao
     PySUS — `pyreaddbc` é um pacote isolado, pequeno, mantido.
   - Critério para reconsiderar Opção B: se `pyreaddbc` for arquivado
     pelo mantenedor ou se aparecerem regressões em release nova.

3. **Janela de execução**: alinhar com release **0.6.0**.
   - Fase 1 (scaffold paralelo) pode rodar antes do corte da 0.6.0 sem
     bloquear features.
   - Fase 2 (flag de backend em SIH) entra como feature opt-in da 0.6.0.
   - Fase 4 (flip default para FTP) só após 0.6.0 sair com a flag opt-in
     validada em produção.

Essas decisões serão refletidas em `docs/versionamento.md` quando a
fase 1 começar.

## 10. Execução da fase 1 (2026-05-28)

Pacote `guaraci/datasus/ftp/` entregue na branch
`feat/datasus-ftp-direto`:

| Arquivo                                       | Linhas | Função                                                      |
|-----------------------------------------------|--------|-------------------------------------------------------------|
| `guaraci/datasus/ftp/__init__.py`             | 42     | Exports públicos da camada                                  |
| `guaraci/datasus/ftp/client.py`               | 215    | `DatasusFtpClient` async sobre `ftplib` via `to_thread`     |
| `guaraci/datasus/ftp/catalog.py`              | 150    | `FileRecord` + regex de parsing SIH/SIM/SINAN               |
| `guaraci/datasus/ftp/discovery.py`            | 120    | `discover_sih(...)` filtrado e ordenado                     |
| `guaraci/datasus/ftp/dbc.py`                  | 75     | Façade `pyreaddbc.dbc2dbf` + `dbfread.DBF` → `pl.DataFrame` |

Cobertura de testes — 52 testes, todos verdes:

- `tests/test_ftp_catalog.py` (38 testes) — parsing de basenames válidos
  e inválidos para os 3 sistemas; igualdade JSON; imutabilidade.
- `tests/test_ftp_discovery.py` (8 testes) — filtros, traversal seletiva
  por janela de anos, ordenação canônica, enriquecimento com SIZE.
- `tests/test_ftp_dbc.py` (4 testes) — DBC→DBF→records→Polars com fakes
  de `pyreaddbc`/`dbfread`; fallback pandas; erro útil quando o arquivo
  não existe.
- `tests/test_ftp_smoke.py` (2 testes, opt-in via `GUARACI_FTP_SMOKE=1`)
  — `RDSP2401.dbc` real: conectar/NLST/SIZE e fim-a-fim (download +
  decode).

`pyproject.toml`: `pyreaddbc>=2.0.0` promovido a dependência direta dos
extras `datasus` e `full`. Caminho PySUS legado intacto.

## 11. Execução da fase 2 (2026-05-28)

`SihDataSource` agora delega para o backend escolhido por env:

- `GUARACI_DATASUS_BACKEND=pysus` (default) — caminho legado intacto.
- `GUARACI_DATASUS_BACKEND=ftp` — novo caminho via
  `guaraci/datasus/ftp/sih_backend.py`.

Refator no `guaraci/datasus/sih.py`:

| Antes                              | Depois                                              |
|------------------------------------|-----------------------------------------------------|
| `download()` com PySUS inline      | `download()` valida + dispacha por backend          |
| `discover()` com PySUS inline      | `discover()` valida + dispacha por backend          |
| —                                  | `_download_via_pysus()` (caminho legado preservado) |
| —                                  | `_discover_via_pysus()` (caminho legado preservado) |
| —                                  | `_download_via_ftp()` (delega para sih_backend)     |
| —                                  | `_discover_via_ftp()` (delega para sih_backend)     |
| —                                  | `_ftp_cache_dir()` honra `GUARACI_FTP_CACHE_DIR`    |

Novo módulo `guaraci/datasus/ftp/sih_backend.py` (~190 linhas):

- `discover_sih_summary(...)` — preflight com payload no formato esperado
  pela API (`source`, `documents_found`, `by_group`, `by_state`,
  `sample`, `filters`).
- `download_sih(...)` — discover → download `.dbc` → decode →
  `write_parquet` → cleanup do `.dbc`. Idempotente (pula arquivos que
  já existem como `.parquet` no cache). Retorna `paths_by_group` para
  `SihDataSource` popular `self.data`.

Cobertura nova (16 testes, todos verdes):

- `tests/test_sih_backend_ftp.py` (6) — fluxo completo, idempotência,
  falha por arquivo, progress callback.
- `tests/test_sih_backend_switch.py` (10) — leitura da env var, valor
  inválido cai no default, dispatch correto em download() e discover(),
  validação preservada (groups/months), clamp do ano corrente,
  filtros do payload, cache dir custom vs default.

## 12. Execução da fase 3 (2026-05-28)

SIM e SINAN passam a rotear pelo backend FTP atrás da mesma flag. Em vez
da herança de `BaseFtpDataSource` esboçada em §3.5, o "tail" comum (loop
asyncio, download → decode → parquet → cleanup, idempotência, formato do
summary) foi extraído para um módulo síncrono compartilhado, deixando os
três `*_backend` finos. O seletor de backend também saiu de dentro do SIH
para um leaf sem dependências consultado pelas três fontes.

| Arquivo                                       | Linhas | Função                                                              |
|-----------------------------------------------|--------|---------------------------------------------------------------------|
| `guaraci/datasus/backend.py`                  | 43     | Seletor compartilhado `get_datasus_backend()` + constantes          |
| `guaraci/datasus/ftp/orchestration.py`        | 154    | Tail comum: `run_coro`, `download_records`, `safe_unlink`, `build_summary` |
| `guaraci/datasus/ftp/sim_backend.py`          | 97     | `discover_sim_summary(...)` + `download_sim(...)`                    |
| `guaraci/datasus/ftp/sinan_backend.py`        | 97     | `discover_sinan_summary(...)` + `download_sinan(...)` (dedup FINAIS/PRELIM) |
| `guaraci/datasus/ftp/discovery.py` (+)        | 236    | Acrescido de `discover_sim(...)` e `discover_sinan(...)`            |

`sih_backend.py` (fase 2) foi refatorado para reusar `orchestration.py`;
`sim.py` e `sinan.py` ganharam dispatch por env espelhando o SIH.
Descoberta segue exposta só no SIH na camada de serviço — SIM/SINAN
precisam apenas do dispatch de `download()`.

Dedup SINAN: `discover_sinan` varre FINAIS + PRELIM e, em colisão de
basename, **FINAIS vence** (`seen = {r.basename for r in finais}`;
`finais + [r for r in prelim if r.basename not in seen]`) — mantém o
download idempotente e deixa PRELIM preencher só as lacunas.

Cobertura nova — 44 testes, todos verdes:

- `tests/test_datasus_backend.py` (7) — contrato do seletor compartilhado
  num único lugar: valor default (`ftp` pós-fase 4), env-unset → default,
  ftp/pysus via env, valor desconhecido → default, case-insensitive +
  trim, arg `default` explícito honrado.
- `tests/test_ftp_discovery.py` (+12, total 20) — discovery SIM (filtro
  ano/grupo/UF, visita só o dir do grupo pedido, sem grupos visita CID9 +
  CID10, ordenação, enriquecimento SIZE, vazio sem anos) e SINAN (filtro
  ano/doença, varre FINAIS + PRELIM, FINAIS vence em duplicata, ordenação,
  sem grupos retorna tudo, vazio sem anos).
- `tests/test_sim_backend_ftp.py` (6) — fluxo completo, idempotência,
  falha por arquivo, progress callback, formato do summary.
- `tests/test_sinan_backend_ftp.py` (6) — idem; `by_state == {}` (SINAN
  é nacional, sem recorte por UF).
- `tests/test_sim_backend_switch.py` (7) — wiring via env, dispatch,
  default de grupos = `CID10`, validação de grupo, clamp do ano corrente,
  cache dir custom vs default.
- `tests/test_sinan_backend_switch.py` (6) — idem, com default de doenças
  = `SinanDataSource.NEGLECTED_DISEASES` (SINAN não valida lista de doenças).

## 13. Execução da fase 4 (2026-05-28)

Flip do default para o caminho direto-FTP, reversível numa variável.

Mudança comportamental única em `guaraci/datasus/backend.py`:
`DEFAULT_BACKEND = BACKEND_PYSUS` → `DEFAULT_BACKEND = BACKEND_FTP`. As
três fontes herdam o novo default automaticamente por consultarem o leaf.

Reorganização de extras em `pyproject.toml` (versão segue `0.5.2`):

| Extra            | Antes                          | Depois                                  |
|------------------|--------------------------------|-----------------------------------------|
| `datasus`        | `pyreaddbc`, `dbfread`, `pysus[dbc]` | `pyreaddbc`, `dbfread` (enxuto)   |
| `datasus-legacy` | —                              | `pysus>=2.2.0` (novo; escape hatch)     |
| `full`           | `pysus[dbc]>=2.1.0`            | `pysus>=2.2.0` (extra `[dbc]` obsoleto removido) |

`pysus[dbc]` foi descontinuado upstream (o `[dbc]` virou base no PySUS
2.2.0, e pedir o extra dispara warning no `uv lock`); por isso o pin
passou a `pysus>=2.2.0`. `dbfread` é declarado explicitamente no extra
enxuto porque `guaraci/datasus/ftp/dbc.py` importa `dbfread.DBF`
diretamente.

Ajustes de teste para o novo default (sem mudar a lógica testada):

| Arquivo                          | Ajuste                                                              |
|----------------------------------|--------------------------------------------------------------------|
| `tests/test_sih_datasource.py`   | Fixture autouse fixa `GUARACI_DATASUS_BACKEND=pysus` (testa o legado) |
| `tests/test_sih_backend_switch.py`| Default agora `ftp`; novo teste do escape hatch `=pysus`           |
| `tests/test_datasus_backend.py`  | Asserção do valor default vira `BACKEND_FTP`                        |

**Gates formais ainda pendentes** (ver alerta no topo do documento):
igualdade bit-exata vs PySUS e 1 semana de validação operacional não
foram cumpridas. O flip foi autorizado mesmo assim; rollback =
`GUARACI_DATASUS_BACKEND=pysus` (enquanto o extra `datasus-legacy`
existir) ou reverter `DEFAULT_BACKEND`.

## 14. Execução da fase 5 — expansão de cobertura (2026-05-30)

> **Nota de nomenclatura.** Esta "fase 5" é uma frente **nova**, autorizada
> pelo operador ("integre isso tudo do ftp"): estende a conexão direta-FTP
> para **além** de SIH/SIM/SINAN. É ortogonal à "Fase 5 — Remoção do legado"
> do §6 (que continua pendente e seria melhor numerada como Fase 6). Código
> e commits chamam esta expansão de `phase 5`.

Recon ao vivo em `ftp.datasus.gov.br/dissemin/publicos/` (2026-05-30)
mapeou 25 diretórios; os caminhos, padrões de nome e conjuntos de grupos
(14 do SIA, 13 do CNES, CPNI/DPNI do PNI) foram **confirmados no servidor,
não chutados**. Onze sistemas de microdados foram integrados:

| source | Caminho FTP | Padrão | Dimensões |
|--------|-------------|--------|-----------|
| `sinasc` | `/SINASC/NOV/DNRES` | `DN<UF><AAAA>.dbc` | UF, anual |
| `sia` | `/SIASUS/{199407_200712,200801_}/Dados` | `<GRP><UF><AAMM>.dbc` | 14 grupos, UF, mensal |
| `cnes` | `/CNES/200508_/Dados/<GRP>` | `<GRP><UF><AAMM>.dbc` | 13 grupos (subdir), UF, mensal |
| `pni` | `/PNI/DADOS` | `CPNI\|DPNI<UF><AA>.DBF` | 2 grupos, UF, anual, **.DBF** |
| `ciha` | `/CIHA/201101_/Dados` | `CIHA<UF><AAMM>.dbc` | UF, mensal |
| `cih` | `/CIH/200801_201012/Dados` | `CR<UF><AAMM>.dbc` | UF, mensal (legado) |
| `siscan` | `/SISCAN/{SISCOLO4,SISMAMA}/Dados` | `CC\|CM<UF><AAMM>.dbc` | 2 grupos, UF, mensal |
| `sisprenatal` | `/SISPRENATAL/201201_/Dados` | `PN<UF><AAMM>.dbc` | UF, mensal |
| `resp` | `/RESP/DADOS` | `RESP<UF><AA>.dbc` | UF, anual |
| `pce` | `/PCE/Dados` | `PCE<UF><AA>.dbc` | UF, anual |
| `painel_oncologia` | `/painel_oncologia/Dados` | `POBR<AAAA>.dbc` | nacional, anual |

**Excluídos** (registrado como decisão): `CMD` (diretório `Dados` vazio —
sem microdados acessíveis via FTP) e `ANS` (saúde suplementar/privada,
fora do escopo de microdados de saúde pública). `TABNET/TABWIN/TABDOS`,
`IBGE`, `Pesquisas`, `Dados_Abertos` são ferramentas/denominadores, não
microdados.

Em vez de um módulo bespoke por sistema (como SIH/SIM/SINAN nas fases
1–3), os onze viram **specs declarativas** consumidas por um motor
genérico:

| Arquivo | Função |
|---------|--------|
| `guaraci/datasus/ftp/specs.py` | `SystemSpec` (regex + paths + flags) + as 11 specs |
| `guaraci/datasus/ftp/discovery.py` (+`discover_spec`) | discovery genérico (layout `roots` ou `group_dirs`) |
| `guaraci/datasus/ftp/dbc.py` (+`.DBF`) | lê `.DBF` direto (PNI), pulando `pyreaddbc` |
| `guaraci/datasus/ftp/generic_backend.py` | `discover_summary`/`download` por spec |
| `guaraci/datasus/ftp_source.py` | `FtpDataSource(spec)` — DataSource único FTP-only |
| `guaraci/services/downloads.py` (+`_build_ftp_source`) | registra os 11 (`mode="datasus ftp"`) |
| `guaraci/cli/datasus_cli.py` | CLI genérico `guaraci datasus list\|download` |

Os onze nascem **FTP-only** (não há legado PySUS a preservar, então sem
flag de backend). Ficam acessíveis por `/sources`, `/sources/{source}/schema`,
`/jobs`, UI e CLI. **56 testes** offline novos + um smoke de discovery ao
vivo que confirmou todos os 11 specs contra o servidor (ex.: 27 arquivos
UF para SINASC 2020, 324 = 27×12 para sistemas mensais, 1 arquivo nacional
no painel de oncologia). Suíte cheia verde exceto as 2 falhas pré-existentes
do `test_sinan_datasource.py`.

**Escopo MVP**: apenas parâmetros de coleta (sem refinamentos de export
por campo como `causa_basica` do SIM); o parquet bruto + manifesto são
materializados e há export genérico para csv/parquet/sqlite. Refinamentos
por campo, discovery via serviço para esses sources, e centróides
municipais ficam como follow-up.

**Branch/worktree**: feito em `feat/datasus-ftp-direto`. O trabalho NASA
(POWER/FIRMS) do operador vive em `feat/nasa-clima`; para não tocar nessa
working tree, a fase 5 foi finalizada via `git worktree` isolado.
