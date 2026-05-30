# PLANO: integração GPM IMERG (precipitação NASA) — proposta/ADR

> Status: **NÃO IMPLEMENTADO — aguarda aprovação + credenciais Earthdata.**
> Documento no mesmo espírito de `PLANO_DATASUS_FTP_DIRETO.md`: decide a abordagem
> e o caminho conservador antes de escrever código que não pode ser validado nesta
> sessão. Autor: sessão autônoma de 2026-05-29 (após entregar `nasa_power` e
> `nasa_firms`).

## 1. Contexto e objetivo

GPM IMERG (Integrated Multi-satellitE Retrievals for GPM) é o produto de precipitação
da NASA com resolução ~0.1° (~10 km) e passo de 30 min (também diário e mensal),
cobertura global desde 2000. É a terceira fonte climática solicitada (após NASA POWER e
NASA FIRMS), e a de maior valor para cruzamentos de precipitação fina × saúde
(arboviroses × chuva em resolução melhor que o POWER).

Fonte primária: **NASA GES DISC** (`gesdisc.eosdis.nasa.gov`) — publisher oficial,
aderente ao Princípio 20.

## 2. Decisão arquitetural (o ponto central)

Há dois caminhos para obter IMERG, e a escolha é uma **decisão de arquitetura** que NÃO
deve ser tomada sem aprovação (regra dura do modo autônomo):

### Caminho A — granules HDF5/NetCDF (REJEITADO como default)
Baixar os granules IMERG (HDF5) do GES DISC e fazer subsetting local por ponto/região.
- **Custo:** exige dependência pesada nova (`h5py`/`netCDF4`/`xarray` + `numpy` + libs C
  HDF5). Isso **contraria diretamente** a direção de dependências enxutas do projeto —
  a migração `PLANO_DATASUS_FTP_DIRETO` existiu justamente para sair de ~20 deps para ~2.
- **Volume:** granules globais (~30 MB/arquivo half-hourly) → download massivo para
  extrair um ponto. Inviável no loop do agente (ver `operacao.md §5.2`).
- **Veredito:** **não adotar** sem aprovação explícita. Seria uma mudança arquitetural
  relevante (deps + fluxo de dados binário).

### Caminho B — time-series ASCII via GES DISC Data Rods / Giovanni (RECOMENDADO)
Usar o serviço de **time series por ponto** do GES DISC (Data Rods / Giovanni), que
devolve **ASCII/texto** já subsetado para o ponto — **sem dependência pesada**, só HTTP +
parsing de texto. **Arquitetura idêntica à do `nasa_power`** (série temporal por ponto).
- Endpoint moderno: `https://api.giovanni.earthdata.nasa.gov/timeseries`
  (o legado `https://hydro1.gesdisc.eosdis.nasa.gov/daac-bin/access/timeseries.cgi`
  ainda é citado em tutoriais; confirmar qual está ativo).
- Keywords documentadas: `variable`, `location`, `startDate`, `endDate`, `type`.
- `location` no formato `GEOM:POINT(lon, lat)`; `type=asc2` para ASCII.
- **Veredito:** este é o caminho conservador, reversível e coerente com o código já
  existente. **É o recomendado.**

## 3. Bloqueios reais (por que não foi implementado agora)

1. **Autenticação Earthdata obrigatória.** "Access to GES DISC data requires all users to
   be registered with the Earthdata Login system." Eu **não tenho credenciais** nesta
   sessão, então **não consigo validar ao vivo** nenhuma requisição.
2. **Contrato da API não confirmado.** A pesquisa não fixou com certeza: (a) qual endpoint
   está ativo (Giovanni novo vs `timeseries.cgi` legado), (b) o mecanismo exato de auth
   (bearer token vs cookie/.netrc), (c) os identificadores exatos das variáveis IMERG V07
   no Data Rods, (d) o layout exato do ASCII de resposta. Implementar um parser contra um
   formato não confirmado e **sem poder testar** produziria código "verde nos mocks, mas
   possivelmente errado na vida real" — baixa qualidade. Por isso: plano agora, código
   após confirmação.

Diferença em relação ao FIRMS (que foi implementado mesmo sem MAP_KEY): o contrato CSV do
FIRMS é estável/bem documentado e o parser é genérico; o do IMERG/Data Rods é
materialmente mais incerto e o parsing depende do formato exato.

## 4. Design proposto (quando aprovado + com credenciais)

Seguir o padrão NASA já estabelecido nesta branch:

- `guaraci/nasa/client.py`: adicionar `NasaGesDiscClient` (ou estender) com um método
  `timeseries(variable, longitude, latitude, start, end, type="asc2") -> str` que faz GET
  autenticado e devolve o texto. **Neste ponto (3º client NASA) vale extrair uma base HTTP
  compartilhada** entre POWER/FIRMS/GES DISC (a duplicação da plumbing de erro foi mantida
  de propósito até o 3º client — ver decisão registrada no handoff).
- `guaraci/nasa/gpm.py`: `NasaGpmDataSource(DataSource)` espelhando `NasaPowerDataSource`:
  - entrada: `latitude`, `longitude`, `start_date`, `end_date`, `product`
    (ex.: `GPM_3IMERGHH.07` half-hourly, `GPM_3IMERGDF.07` diário), `output_format`,
    `keep_raw`, `timeout`, `api_base_url`.
  - parse do ASCII → tabela larga (`period`/`date`/`datetime`/`precipitation`), sentinela
    de no-data → null (confirmar o valor do sentinela no header do ASCII).
  - manifest, export csv/parquet/sqlite, eventos de progresso — idênticos ao POWER.
- `guaraci/services/downloads.py`: registrar `nasa_gpm` (mode `"nasa gpm api"`) via
  `NasaDownloadSource` + `_normalize_nasa_gpm_params`.

## 5. Segredo / credencial (padrão já adotado no FIRMS)

- Token Earthdata lido **apenas** de `GUARACI_EARTHDATA_TOKEN` (env), **nunca** como
  parâmetro de job (jobs são persistidos em disco). Não entra no manifest e é redigido de
  mensagens de erro. Mesma política do `GUARACI_FIRMS_MAP_KEY`.
- Token gerado em `urs.earthdata.nasa.gov` (User Profile → Generate Token); enviado como
  `Authorization: Bearer <token>` (confirmar que o endpoint Giovanni aceita esse fluxo).

## 6. Plano de implementação (fase-a-fase)

- **Fase 0 (validação de viabilidade, precisa de credencial):** com um token Earthdata,
  rodar UM GET pequeno (1 ponto, 1 dia) contra o endpoint candidato e **capturar o ASCII
  real** — exatamente como fiz os probes ao vivo do POWER. Isso fixa endpoint+auth+formato.
  Análogo ao `scripts/discover_sih_rd.py` da migração FTP.
- **Fase 1:** `NasaGesDiscClient` + parser do ASCII (com base no formato real capturado na
  Fase 0) + testes com mocks do ASCII real.
- **Fase 2:** `NasaGpmDataSource` + registro `nasa_gpm` + testes service/datasource/api,
  no mesmo molde de POWER/FIRMS.
- **Fase 3:** extrair `BaseNasaClient` (plumbing de erro compartilhada) e refatorar
  POWER/FIRMS/GPM para reusá-la (agora justificado pelo 3º client).
- **Fase 4:** docs (README, CHANGELOG, ARCHITECTURE §7.6, SOURCES_AND_FILTERS §3.11).

## 7. Riscos e mitigações

| Risco | Mitigação |
| --- | --- |
| Endpoint/auth/formato diferentes do suposto | Fase 0 captura o real antes de codar o parser |
| Earthdata muda fluxo de auth | Token via env, isolado no client; troca em 1 lugar |
| Caminho leve não expõe a variável desejada | Fallback documentado para o Caminho A (HDF5) **com aprovação explícita de deps** |
| Volume/limites do serviço de time-series | Janela pequena por requisição + (se preciso) fatiamento, como no FIRMS |

## 8. Recomendação

Aprovar o **Caminho B** (time-series ASCII, sem dep pesada) e fornecer um token Earthdata
para a Fase 0. Com isso, a implementação segue rápida e no mesmo padrão de POWER/FIRMS.
**Não** adotar o Caminho A (HDF5 + xarray/h5py) sem decisão explícita sobre dependências.

---
Referências: NASA Earthdata "Data Rods for Hydrology"; GES DISC Hydrology Data Rods;
Giovanni time-series API (`api.giovanni.earthdata.nasa.gov/timeseries`).
