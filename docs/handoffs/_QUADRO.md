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
> **Última reconciliação:** 2026-08-18 — registradas as 9 fontes SISAGUA restantes (14/14 do portal agora ativas); nova categoria/sampler `opendatasus_files` em `dictionary_sampling.py` (3 SISAGUA pequenas + `srag_arquivos` amostrados com campos reais; 11 SISAGUA grandes corrigidos de "ok" fabricado — relíquia do dicionário pré-bulk-file — para "empty" honesto); host CKAN morto do OpenDataSUS agora falha com erro claro em vez de DNS opaco. `scripts/build_site_catalog.py` rodou de ponta a ponta (91 fontes).
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
| SIOPS — sem integração viável no momento | Plano de novas fontes, Fase A (17/08) | Investigado ao vivo: o dataset `/dataset/siops` do portal só expõe um PDF de metadados via S3 (não são dados tabulares); a API própria `siops-consulta-publica-api.saude.gov.br` não publica Swagger/OpenAPI descobrível (`/swagger-resources` retorna `[]`; `/v3/api-docs`, `/v2/api-docs`, `/swagger-ui/index.html` etc. todos 404). Precisaria de engenharia reversa dos endpoints reais (inspecionar requests do frontend do SIOPS) para virar fonte API — não tentado nesta rodada. |
| Amostragem de campos (`field_dictionary.json`) para as fontes SISAGUA GRANDES (11 de 14) | Agente (18/08) | `sample_opendatasus_files()` já existe e funciona (verificado ao vivo), mas recusa baixar qualquer coisa acima de 20MB. As 11 fontes SISAGUA cujo menor recurso conhecido excede esse teto (39MB-138MB comprimido; `sisagua_controle_semestral`/`sisagua_vigilancia_parametros_basicos` têm tamanho desconhecido — HEAD retorna 403 no S3, mas são análogas em escala) ficam honestamente em `status: empty` com nota de tamanho, sem campos. Para resolver de verdade seria preciso ler só as primeiras linhas via download parcial por Range HTTP (o S3 aceita `Range`?) em vez do arquivo inteiro — não tentado nesta rodada (fora do escopo mínimo pedido). |
| Amostragem de campos (`field_dictionary.json`) para as famílias `inpe queimadas api`/`inmet portal zip`/`ibge api` | Plano de novas fontes, Fases B1/B2/C | `classify_source()` só ganhou categoria nova para `opendatasus files` nesta rodada (pedido explícito: "pelo menos a família opendatasus files"). INPE/INMET/IBGE continuam com entrada manual no dicionário (não degradadas) — não integradas ao sampler automático. |
| **Bug:** `pni`/`pce`/`siscan` retornam vazio (`group=None` no `load_dataframe`) | amostragem 28/06 | Discovery confirma os arquivos no FTP, mas o load multi-grupo/nacional não materializa. Investigar `ftp_source.load_dataframe`/`generic_backend`. |
| **Detalhamento semântico de campos e janelas históricas no site catálogo** | demanda usuário (11/08) | Enriquecer o catálogo com dicionários de dados semânticos (descrição/significado das siglas dos campos) obtidos das fontes oficiais (DATASUS, OpenDataSUS, etc.) e limites de cobertura histórica (anos disponíveis por fonte). |
| Empacotamento durável p/ submódulo (submódulo fixo × `pip install @ git+` × editable) | feedback de agente | Decidir só **depois** do Guaraci estabilizar; por ora, editable-install local serve. |
| `downloads.py` (3113 linhas) — fatiar o registry repetitivo | feedback de agente | Otimização prematura: 90% é schema. Só se doer. |
| Deletar branches stale (`feat/nasa-clima`, `feat/datasus-ftp-direto`) | higiene git | `main` é a viva; manter `archive/*`/`safety/*`. Aguarda ok. |
| Chave órfã `sisagua_tratamento_de_agua` no `CURATED` do site | Agente (18/08) | Distinta de `sisagua_tratamento_agua` (a fonte bulk-file real, registrada). Não é órfã de fato — resolve contra uma fonte DEMAS auto-gerada homônima (`opendatasus_registry.py`, não sombreada porque o nome não bate). Redundante/confuso mas não quebra o gerador; renomear/remover do `CURATED` é limpeza, não bug — fora do escopo desta rodada. |
| **Bug pré-existente:** `scripts/build_site_catalog.py` falha (`SystemExit`) por 5 entradas órfãs no `CURATED` (`arboviroses_chikungunya`, `arboviroses_dengue`, `arboviroses_febre_amarela_humanos_primatas_nao_humanos`, `vacinacao_esavi`, `vigilancia_e_meio_ambiente_mpox`) que não têm mais fonte correspondente em `DownloadService.list_sources()` | Fase B2 (INMET), 2026-08-18 | Não introduzido por esta entrega — confirmado reproduzindo o script no estado do `main` antes de qualquer mudança da Fase B. Bloqueia a regeneração de `site/assets/catalog-data.js` até alguém podar/realinhar essas 5 chaves do `CURATED` (ou os sources correspondentes forem re-registrados). A entrada `inmet_estacoes` foi validada isoladamente (schema/cadência/CURATED resolvem sem erro) mas o `catalog-data.js` não pôde ser regenerado de ponta a ponta por causa deste bug alheio. |
| **ANA HidroWebService (`ana_hidro`) — validação ao vivo pendente de credencial** | Fase B3, plano `PLANO_NOVAS_FONTES.md` (18/08) | Implementado (`guaraci/ana/`) com testes offline (fake client) e endpoints/parâmetros travados via leitura ao vivo do OpenAPI público (`www.ana.gov.br/hidrowebservice/api-docs`). Falta: (1) Luis completar o cadastro por e-mail junto à ANA para obter `GUARACI_ANA_ID`/`GUARACI_ANA_SENHA`; (2) rodar `GUARACI_ANA_SMOKE=1` com uma estação real e um recorte curto; (3) inspecionar o payload real e ajustar o mapeamento de colunas em `guaraci/ana/hidro.py` se os nomes de campo detectados (`Data_Hora_Medicao` etc., hipotéticos) não baterem — o schema de resposta (`Devolucao.items`) é opaco no OpenAPI, não há como travar os nomes sem uma chamada autenticada real. |
| **Bug:** `scripts/build_site_catalog.py` quebra com `SystemExit` (`entradas CURATED sem fonte no serviço`) | Fase C (agente, 17/08) | Pré-existente, não introduzido pela Fase C — reproduzido no `main` antes de qualquer mudança desta rodada. `CURATED` referencia 5 chaves sem fonte registrada no serviço atual (`arboviroses_chikungunya`, `arboviroses_dengue`, `arboviroses_febre_amarela_humanos_primatas_nao_humanos`, `vacinacao_esavi`, `vigilancia_e_meio_ambiente_mpox` — nomes de fontes DEMAS que parecem ter sido renomeadas/removidas). O script também só resolve `guaraci` do worktree correto quando `PYTHONPATH` inclui a raiz do repo (rodar `python arquivo.py` direto pega o `guaraci` instalado em modo editable, que pode divergir do worktree). Contornado nesta rodada com um patch cirúrgico em `site/assets/catalog-data.js` (inserindo só as 3 fontes IBGE novas via JSON, sem tocar nas entradas antigas) em vez de rodar o gerador completo. Corrigir `CURATED` (remover/atualizar as 5 chaves órfãs) antes da próxima regeneração completa do catálogo.
| 9 fontes SISAGUA adicionais pendentes (Fase A, `srag_arquivos`/`sisagua_*` fora do 1º corte) | Fase A (plano `docs/PLANO_NOVAS_FONTES.md`, arquivado) | Mesmo transporte (`PortalFileDataSource`); specs triviais a acrescentar. Fora do escopo da Fase C. |
| `inpe_queimadas` entregue (Fase B1) | Fase B1 (agente, 18/08) | `guaraci/inpe/` (client + datasource, padrão `guaraci/nasa/`), registrado via `ApiDownloadSource`. Anos 2003–2025 confirmados ao vivo (parse do index HTTP, sem hardcode); produto mensal (2023+) tem esquema próprio (`risco_fogo`/`frp`/`precipitacao`) e é tratado como tal, não como recorte fino do anual. `field_dictionary.json` recebeu entrada manual (`dictionary_sampling.py::classify_source` ainda não tem categoria para fontes `ibge api`/`inpe queimadas api` fora da lista `FTP_LEGACY_SOURCES` — mesma lacuna já registrada para `opendatasus files`); rodar `scripts/sample_sources.py` continua pendente para automatizar. Grupo "Ambiental · clima, água e território" criado no catálogo do site — INMET/ANA (Fases B2/B3, em paralelo) devem reaproveitar o mesmo grupo. |

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
