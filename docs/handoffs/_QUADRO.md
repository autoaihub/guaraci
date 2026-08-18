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
| **Bug:** `pni`/`pce`/`siscan` retornam vazio (`group=None` no `load_dataframe`) | amostragem 28/06 | Discovery confirma os arquivos no FTP, mas o load multi-grupo/nacional não materializa. Investigar `ftp_source.load_dataframe`/`generic_backend`. |
| **Detalhamento semântico de campos e janelas históricas no site catálogo** | demanda usuário (11/08) | Enriquecer o catálogo com dicionários de dados semânticos (descrição/significado das siglas dos campos) obtidos das fontes oficiais (DATASUS, OpenDataSUS, etc.) e limites de cobertura histórica (anos disponíveis por fonte). |
| Empacotamento durável p/ submódulo (submódulo fixo × `pip install @ git+` × editable) | feedback de agente | Decidir só **depois** do Guaraci estabilizar; por ora, editable-install local serve. |
| `downloads.py` (3113 linhas) — fatiar o registry repetitivo | feedback de agente | Otimização prematura: 90% é schema. Só se doer. |
| Deletar branches stale (`feat/nasa-clima`, `feat/datasus-ftp-direto`) | higiene git | `main` é a viva; manter `archive/*`/`safety/*`. Aguarda ok. |
| **ANA HidroWebService (`ana_hidro`) — validação ao vivo pendente de credencial** | Fase B3, plano `PLANO_NOVAS_FONTES.md` (18/08) | Implementado (`guaraci/ana/`) com testes offline (fake client) e endpoints/parâmetros travados via leitura ao vivo do OpenAPI público (`www.ana.gov.br/hidrowebservice/api-docs`). Falta: (1) Luis completar o cadastro por e-mail junto à ANA para obter `GUARACI_ANA_ID`/`GUARACI_ANA_SENHA`; (2) rodar `GUARACI_ANA_SMOKE=1` com uma estação real e um recorte curto; (3) inspecionar o payload real e ajustar o mapeamento de colunas em `guaraci/ana/hidro.py` se os nomes de campo detectados (`Data_Hora_Medicao` etc., hipotéticos) não baterem — o schema de resposta (`Devolucao.items`) é opaco no OpenAPI, não há como travar os nomes sem uma chamada autenticada real. |
| **Bug pré-existente:** `scripts/build_site_catalog.py` falha com `SystemExit` (`entradas CURATED sem fonte no serviço`) | achado durante Fase B3/D (18/08) | 5 entradas do `CURATED` (`arboviroses_chikungunya`, `arboviroses_dengue`, `arboviroses_febre_amarela_humanos_primatas_nao_humanos`, `vacinacao_esavi`, `vigilancia_e_meio_ambiente_mpox`) referenciam fontes que não existem mais em `DownloadService.list_sources()` — confirmado pré-existente via `git stash` (falha idêntica sem as mudanças da B3). Bloqueia a regeneração de `site/assets/catalog-data.js` até alguém remover/atualizar essas 5 entradas (provável resquício de uma geração antiga do registry OpenDataSUS). A entrada `ana_hidro` já está no `CURATED`, pronta para entrar na próxima regeneração bem-sucedida. |

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
