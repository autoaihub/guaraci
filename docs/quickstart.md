# Quickstart — Guaraci

## Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e **ativo**
- Git

---

## 1. Clonar o repositório

```powershell
git clone https://github.com/autoaihub/guaraci.git
Set-Location .\guaraci
```

---

## 2. Build da imagem Docker

Execute uma única vez (ou quando houver atualização de dependências):

```powershell
docker build -t guaraci .
```

---

## 3. Iniciar o Guaraci

### Forma recomendada — Launcher (Windows)

O script cuida de tudo: sobe o container em background, aguarda o health check e abre o browser automaticamente.

```powershell
.\scripts\desktop\start-guaraci.ps1
```

A UI abre automaticamente em **http://localhost:8002/**

> **Nota:** o container fica rodando em background com o nome `guaraci-desktop`. O terminal retorna imediatamente.

---

### Forma manual (sem launcher)

Útil para debug ou quando o launcher não está disponível. O terminal fica preso enquanto o servidor roda — pressione `Ctrl+C` para parar.

```powershell
docker run --rm -it -p 8002:8000 -v "${PWD}:/app" guaraci `
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Acesse manualmente: **http://localhost:8002/**

> **Atenção:** não use `docker run --rm` sem `-it` e sem `-d` — o container encerra imediatamente sem interatividade.

---

## 4. Verificar se está funcionando

```powershell
# Health check
Invoke-RestMethod http://localhost:8002/health

# Listar fontes disponíveis (82 no total)
Invoke-RestMethod http://localhost:8002/sources
```

Resposta esperada do health:
```json
{"status": "ok", "version": "0.4.1"}
```

---

## 5. Parar o container

```powershell
.\scripts\desktop\stop-guaraci.ps1
```

Ou se iniciou manualmente: `Ctrl+C` no terminal.

---

## 6. Comandos úteis

| Ação | Comando |
|---|---|
| Iniciar | `.\scripts\desktop\start-guaraci.ps1` |
| Verificar status | `.\scripts\desktop\status-guaraci.ps1` |
| Parar | `.\scripts\desktop\stop-guaraci.ps1` |
| Rodar testes | `docker run --rm -v "${PWD}:/app" guaraci python -m pytest tests/ -q` |
| Shell interativo | `docker run --rm -it -v "${PWD}:/app" guaraci bash` |

---

## 7. Problemas comuns

**Container encerra imediatamente**
→ Use `.\scripts\desktop\start-guaraci.ps1` (launcher) ou adicione `-it` ao `docker run` manual.

**Porta 8002 ocupada**
→ Use uma porta diferente: `.\scripts\desktop\start-guaraci.ps1 -HostPort 8003`

**Docker não está ativo**
→ Abra o Docker Desktop e aguarde o ícone ficar verde antes de rodar.

**"Guaraci UI not found"**
→ Verifique se o volume está montado corretamente (`-v "${PWD}:/app"`).

---

## Próximos passos

- [Arquitetura do sistema](ARCHITECTURE.md)
- [Referência da API](API_REFERENCE.md)
- [Fontes de dados e filtros](SOURCES_AND_FILTERS.md)
- [Fluxo Docker detalhado](DOCKER_WORKFLOW.md)
