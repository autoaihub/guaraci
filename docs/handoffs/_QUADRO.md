# Quadro de Trabalho — Guaraci

> **O que é:** quadro único de trabalho, conciliado a partir das fontes de demanda
> (reuniões, feedback de agentes, decisões registradas na memória do projeto). Cada item
> aberto é reconciliado contra o estado real do repo (git, código, changelog). É uma fila,
> não um arquivo: item aberto sobe pra cá; ✅ é transitório e drena para o `CHANGELOG.md`.
> É o **backlog único** — sem `TODO`/`IMPROVEMENTS` paralelo; spec longa vira doc próprio.
> Substitui a antiga dependência de dezenas de handoffs (os antigos foram arquivados fora
> do repo em `../guaraci-archive/`).
>
> **Drenagem:** ao concluir um item, registre a entrega no `CHANGELOG.md` e remova a linha
> na próxima reconciliação. O quadro mostra o presente em aberto; o passado vive no changelog.
> **Última reconciliação:** 2026-08-11 — Reconciliação do backlog: concluídos sweep de deprecations do Polars, contrato público JobResult, amostragem de 5 novas fontes e default column_map do SIH-RD.
>
> **Legenda:** 🔴 Prioridade · 🟡 Em andamento · ⚪ Pendente (backlog válido) · 🗄️ Defasado (morto, mantido por memória) · ✅ Concluído (transitório → changelog)

## 🔴 Prioridade

_Nada em aberto no momento — os bloqueios (validar `column_map` do SIH; amostrar cada fonte) foram concluídos e drenados ao `CHANGELOG.md`. Ver 🟡 e ⚪._

## 🟡 Em andamento

| Item | Origem | Próxima ação / nota |
|---|---|---|
| Artigo *Data in Brief* sobre o Guaraci | reunião 24/06 | Material em `docs/artigo/for-author/` (untracked). Bruna escreve; 1º draft ~20/07; revisão semana de 6–7/07. Pendências: data object + DOI, grant IDRC, autoria. |

## ⚪ Pendente (backlog válido)

| Item | Origem | Nota |
|---|---|---|
| Registrar os 9 SISAGUA restantes (mesmo transporte `PortalFileDataSource`) | Plano de novas fontes, Fase A (17/08) | Slugs confirmados no portal, faltando registrar: `sisagua-controle-mensal-amostras-fora-do-padrao`, `sisagua-controle-mensal-plano-amostragem`, `sisagua-controle-mensal-infraestrutura-operacional`, `sisagua-vigilancia-demais-parametros`, `sisagua-vigilancia-cianobacterias-e-cianotoxinas`, `sisagua-pontos-de-captacao`, `sisagua-cadastro-carro-pipa-procedencia`, `sisagua-cadastro-carro-pipa-populacao`. Especs triviais análogas às 5 já registradas em `guaraci/services/sources/opendatasus_files.py` — confirmar ao vivo se cada uma é ano-segmentada (como `controle_mensal`/`controle_semestral`/`vigilancia_parametros_basicos`, `min_year=2014`) ou cumulativa sem ano (como `tratamento_agua`/`populacao_abastecida`) antes de fixar `min_year`/`cumulative`. |
| SIOPS — sem integração viável no momento | Plano de novas fontes, Fase A (17/08) | Investigado ao vivo: o dataset `/dataset/siops` do portal só expõe um PDF de metadados via S3 (não são dados tabulares); a API própria `siops-consulta-publica-api.saude.gov.br` não publica Swagger/OpenAPI descobrível (`/swagger-resources` retorna `[]`; `/v3/api-docs`, `/v2/api-docs`, `/swagger-ui/index.html` etc. todos 404). Precisaria de engenharia reversa dos endpoints reais (inspecionar requests do frontend do SIOPS) para virar fonte API — não tentado nesta rodada. |
| Amostragem de campos (`field_dictionary.json`) para as 6 novas fontes `opendatasus files` | Plano de novas fontes, Fase A (17/08) | `guaraci/services/dictionary_sampling.py::classify_source` não reconhece o mode `opendatasus files` (cairia em `demas_generic`, que chama `svc.run(..., batch_size=..., max_pages=...)` — parâmetros que essas fontes não declaram). Precisa de uma categoria/sampler novo (ex.: baixar 1 ano pequeno e ler colunas do parquet/csv) antes de rodar `scripts/sample_sources.py`. Até lá, ficam sem campos no catálogo do site (honesto) e `docs/DATA_DICTIONARY.md` continua com a contagem antiga (91 fontes catalogadas/77 amostradas) — não atualizado nesta rodada porque é gerado por aquele script. |
| **Bug:** `pni`/`pce`/`siscan` retornam vazio (`group=None` no `load_dataframe`) | amostragem 28/06 | Discovery confirma os arquivos no FTP, mas o load multi-grupo/nacional não materializa. Investigar `ftp_source.load_dataframe`/`generic_backend`. |
| **Detalhamento semântico de campos e janelas históricas no site catálogo** | demanda usuário (11/08) | Enriquecer o catálogo com dicionários de dados semânticos (descrição/significado das siglas dos campos) obtidos das fontes oficiais (DATASUS, OpenDataSUS, etc.) e limites de cobertura histórica (anos disponíveis por fonte). |
| Empacotamento durável p/ submódulo (submódulo fixo × `pip install @ git+` × editable) | feedback de agente | Decidir só **depois** do Guaraci estabilizar; por ora, editable-install local serve. |
| `downloads.py` (3113 linhas) — fatiar o registry repetitivo | feedback de agente | Otimização prematura: 90% é schema. Só se doer. |
| Deletar branches stale (`feat/nasa-clima`, `feat/datasus-ftp-direto`) | higiene git | `main` é a viva; manter `archive/*`/`safety/*`. Aguarda ok. |
| **Bug:** `scripts/build_site_catalog.py` quebra com `SystemExit` (`entradas CURATED sem fonte no serviço`) | Fase C (agente, 17/08) | Pré-existente, não introduzido pela Fase C — reproduzido no `main` antes de qualquer mudança desta rodada. `CURATED` referencia 5 chaves sem fonte registrada no serviço atual (`arboviroses_chikungunya`, `arboviroses_dengue`, `arboviroses_febre_amarela_humanos_primatas_nao_humanos`, `vacinacao_esavi`, `vigilancia_e_meio_ambiente_mpox` — nomes de fontes DEMAS que parecem ter sido renomeadas/removidas). O script também só resolve `guaraci` do worktree correto quando `PYTHONPATH` inclui a raiz do repo (rodar `python arquivo.py` direto pega o `guaraci` instalado em modo editable, que pode divergir do worktree). Contornado nesta rodada com um patch cirúrgico em `site/assets/catalog-data.js` (inserindo só as 3 fontes IBGE novas via JSON, sem tocar nas entradas antigas) em vez de rodar o gerador completo. Corrigir `CURATED` (remover/atualizar as 5 chaves órfãs) antes da próxima regeneração completa do catálogo.
| 9 fontes SISAGUA adicionais pendentes (Fase A, `srag_arquivos`/`sisagua_*` fora do 1º corte) | Fase A (plano `docs/PLANO_NOVAS_FONTES.md`, arquivado) | Mesmo transporte (`PortalFileDataSource`); specs triviais a acrescentar. Fora do escopo da Fase C. |
| `inpe_queimadas` entregue (Fase B1) | Fase B1 (agente, 18/08) | `guaraci/inpe/` (client + datasource, padrão `guaraci/nasa/`), registrado via `ApiDownloadSource`. Anos 2003–2025 confirmados ao vivo (parse do index HTTP, sem hardcode); produto mensal (2023+) tem esquema próprio (`risco_fogo`/`frp`/`precipitacao`) e é tratado como tal, não como recorte fino do anual. `field_dictionary.json` recebeu entrada manual (`dictionary_sampling.py::classify_source` ainda não tem categoria para fontes `ibge api`/`inpe queimadas api` fora da lista `FTP_LEGACY_SOURCES` — mesma lacuna já registrada para `opendatasus files`); rodar `scripts/sample_sources.py` continua pendente para automatizar. Grupo "Ambiental · Brasil" criado no catálogo do site — INMET/ANA (Fases B2/B3, em paralelo) devem reaproveitar o mesmo grupo. |

## 🗄️ Defasado (morto — mantido por memória)

- Dezenas de `docs/handoff-*.md` → substituídos por **este quadro**; histórico em `../guaraci-archive/`.
- Co-autoria do Claude nos commits → removida do histórico (reescrita + force-push, 27/06).

## Reconciliação por fonte → legado

| Fonte | Veredito | Itens abertos (já no quadro acima) |
|---|---|---|
| Reunião AutoAI-Pandemics (24/06) | Ativo | UI→legado; artigo Data in Brief |
| Feedback de agente (28/06) | Ativo | contrato público; sweep Polars; default column_map; empacotamento |
| Amostragem de fontes (28/06) | Ativo | bug pni/pce/siscan (o resto — dicionário, `fetch fields`, validação SIH — drenado ao changelog) |
| `docs/handoff-2026-05-*.md` + migração FTP/NASA | Legado-concluído | — (na `main`, no changelog) |
