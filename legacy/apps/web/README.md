# Guaraci Web (apps/web)

UI nova do Guaraci, baseada em **React 18 + Vite + TypeScript**. Consome a
API FastAPI existente (`guaraci.api.main`) e substitui aos poucos o front
monolítico em `guaraci/api/static/index.html` (que permanece como fallback).

## Por que existe

A UI antiga é um único `index.html` com ~1.6 mil linhas de HTML + CSS + JS
vanilla. Cada novo filtro exige manipulação imperativa de DOM
(`document.getElementById`, `innerHTML`), o que produz a UX inconsistente
relatada pelo time.

A nova UI:

- Renderiza filtros a partir do **schema retornado por `/sources/{source}/schema`**
  (sem JS hardcoded por fonte).
- Separa filtros **básicos** (phase `basico`/`coleta`) e **avançados** automaticamente.
- Usa componentes acessíveis (multi-select dropdown, date range com presets).
- Reaproveita componentes acessíveis (`CheckboxDropdown`, `DateRangeDropdown`).

## Como rodar (dev)

1. Subir o backend FastAPI (em outro terminal):

   ```powershell
   uv run uvicorn guaraci.api.main:app --reload --port 8000
   ```

2. Instalar dependências e rodar o Vite:

   ```powershell
   cd apps\web
   npm install
   npm run dev
   ```

3. Abrir `http://localhost:5173`. Requisições `/api/*` são proxiadas para
   `http://127.0.0.1:8000` (config em `vite.config.ts`).

Para apontar para outro backend:

```powershell
$env:GUARACI_API_URL = "http://localhost:8000"; npm run dev
```

## Build

```powershell
npm run build
```

Saída em `apps/web/dist/`. O FastAPI pode passar a servir esses arquivos
via `StaticFiles` quando a migração estiver completa.

## Estrutura

```
src/
  api/client.ts            # fetch wrapper para o backend
  components/
    CheckboxDropdown.tsx   # multi-select com "Todos / Limpar"
    DateRangeDropdown.tsx  # date range com presets (1m/3m/12m)
    JobStatus.tsx          # polling de status com barra de progresso
    SchemaField.tsx        # renderiza 1 campo a partir do SourceParam
    SchemaForm.tsx         # split básico/avançado + render do form
    SourcePicker.tsx       # busca e filtro de fontes
  pages/
    DownloadPage.tsx       # fluxo principal de coleta
  types.ts                 # tipos derivados do schema FastAPI
  App.tsx
  main.tsx
  styles.css               # paleta Guaraci (laranja #c84a02 + verde #0a7a70)
```

## O que falta

- Cobertura de todos os tipos de campo (lista de listas, datas, intervalos).
- Tela de discovery/preview antes de submeter o job.
- Testes unitários (Vitest + Testing Library).
- Servir o build do FastAPI quando estável; manter o `index.html` legacy
  até esta UI atender todos os fluxos.
