# Plano: Conexão Direta ao DATASUS FTP (sem PySUS)

Status: **plano** — nenhuma implementação foi feita. Este documento
descreve a arquitetura proposta, riscos e fases. Aprovação explícita é
necessária antes de iniciar a fase 1.

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
| Dependências adicionadas | ~20 pacotes (`pysus[dbc]` + transitivos)| ~2 pacotes (`aioftp`, `pyreaddbc`)     |
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

### Fase 0 — Aprovação e teste isolado (este documento)
- Aprovação do plano por humano.
- Criação de uma branch `feat/datasus-ftp-direto`.

### Fase 1 — Camada `ftp/` paralela
- Implementar `client.py`, `catalog.py`, `discovery.py`, `dbc.py`.
- Tests: smoke test contra FTP real (1 arquivo SP/2024-01),
  parsing de catalog com fixtures, decodificação DBC contra arquivo
  fixo de regressão.
- Nenhuma mudança em `SihDataSource` ainda.
- Critério de saída: download de 1 arquivo via `ftp/` produz parquet
  idêntico ao PySUS (mesmo número de linhas, mesmo schema, mesmas
  primeiras 100 linhas após sort canônico).

### Fase 2 — Migração de `SihDataSource`
- Adicionar flag interna `GUARACI_DATASUS_BACKEND=ftp|pysus` (default
  `pysus`).
- `SihDataSource` consulta a flag e delega para a camada correta.
- Cobertura paralela: mesma suite de tests roda nos dois backends.
- Critério de saída: jobs reais via UI rodam com `backend=ftp` sem
  regressão funcional por 1 semana operacional.

### Fase 3 — Migração de `SimDataSource` e `SinanDataSource`
- Refatorar para herdarem de `BaseFtpDataSource`.
- Mesma flag, mesmos critérios.

### Fase 4 — Default flip
- `GUARACI_DATASUS_BACKEND=ftp` vira default.
- `pysus[dbc]` sai do extra `datasus` em `pyproject.toml`.
- Caminho legado permanece disponível por 1 release via flag explícita.

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

## 9. Próxima decisão necessária

Antes da fase 1, o operador humano precisa decidir:

1. **Backend default no `pyproject.toml`**: começar com `aioftp` ou
   primeiro validar com `asyncio.to_thread(ftplib)` da stdlib?
2. **Opção A (`pyreaddbc`) ou B (decoder nativo) em `dbc.py`?**
3. **Janela de execução**: alinhar com qual release? (Sugestão: 0.6.0
   pós-empacotamento de launchers desktop.)

Essas decisões devem ser registradas em `docs/versionamento.md` antes
de qualquer código novo entrar.
