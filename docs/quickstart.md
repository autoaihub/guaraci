# Quickstart e Operação Docker — Guaraci

Este projeto adota uma arquitetura **Docker-first**. A execução local em Python fora do Docker é um caminho em desenvolvimento (WIP) e não tem suporte oficial.

## 1. Pré-requisitos e Clonagem

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e **ativo** (em Windows/macOS) ou Docker Engine (Linux)
- Git

```powershell
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
```

## 2. Build da Imagem Docker

Execute uma única vez (ou quando houver atualização de dependências):

```powershell
docker build -t guaraci .
```

> **Atenção (Dependências como PySUS):** Se você instalar dependências localmente via `pip install`, isso NÃO terá efeito dentro do Docker. Você precisará reconstruir a imagem Docker (`docker build -t guaraci .` ou `docker compose build --no-cache`) para garantir que bibliotecas como o **PySUS** estejam atualizadas e disponíveis.

*Dica: Se suspeitar de cache quebrado após muitas mudanças, adicione `--no-cache`.*

## 3. Iniciar o Guaraci

### Forma recomendada — Launcher (Windows)

O script cuida de subir o container em background (`guaraci-desktop`), aguardar o health check e abrir a UI automaticamente no browser.

```powershell
.\scripts\desktop\start-guaraci.ps1
```

A UI abrirá em **http://localhost:8002/**.
*(O terminal retornará imediatamente, mas o servidor continua rodando no Docker).*

### Forma manual (sem launcher ou em Linux/macOS)

Útil para debug. O terminal fica preso exibindo logs — pressione `Ctrl+C` para parar.

**PowerShell / Windows:**
```powershell
docker run --rm -it -p 8002:8000 -v "${PWD}:/app" guaraci `
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

**Bash / Linux ou macOS:**
```bash
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

> **Atenção sobre Volumes:** Sempre monte o volume (`-v "${PWD}:/app"`). Sem isso, os dados gerados (bancos de dados, downloads, manifestos) são perdidos quando o container encerra.

## 4. Verificar o Funcionamento

```powershell
# Health check (esperado: {"status": "ok", "version": "0.5.2"})
Invoke-RestMethod http://localhost:8002/health

# Listar fontes disponíveis
Invoke-RestMethod http://localhost:8002/sources
```

## 5. Parar o Container

**Se usou o Launcher:**
```powershell
.\scripts\desktop\stop-guaraci.ps1
```

**Se iniciou manualmente:**
Basta pressionar `Ctrl+C` no terminal.

## 6. Operações Frequentes e Comandos Úteis

| Ação | Script/Comando |
|---|---|
| Iniciar UI | `.\scripts\desktop\start-guaraci.ps1` (ou `.sh` no Linux/Mac) |
| Verificar status | `.\scripts\desktop\status-guaraci.ps1` |
| Parar | `.\scripts\desktop\stop-guaraci.ps1` |
| Rodar testes completos | `docker run --rm -v "${PWD}:/app" guaraci python -m pytest tests/ -v` |
| Shell interativo | `docker run --rm -it -v "${PWD}:/app" guaraci bash` |

## 7. Troubleshooting e Problemas Comuns

### Porta 8002 ocupada
*Erro: `Bind for 0.0.0.0:8002 failed: port is already allocated`*
**Solução:** O container antigo pode estar preso. Pare com `stop-guaraci.ps1` ou rode o launcher em outra porta: `.\scripts\desktop\start-guaraci.ps1 -HostPort 8003`.

### "Guaraci UI not found" ou UI sem dados
**Solução:** Verifique se o volume está montado corretamente (`-v "${PWD}:/app"`) e se a pasta `data/` possui permissões de escrita.

### "PySUS is required for SIH functionality"
**Solução:** Essa mensagem ocorre se a imagem Docker não foi construída com a versão correta do PySUS ou se o volume do host está conflitando sem a instalação completa. Reconstrua a imagem Docker com `--no-cache`. Você pode verificar se o PySUS está acessível internamente via:
`docker run --rm -it guaraci python -c "import pysus; print('PySUS OK')"`

### Container encerra imediatamente sem logs
**Solução:** Se rodando manualmente, garanta que usou a flag `-it`. Um `docker run` vazio sem terminal interativo fecha imediatamente.

### O botão "Abrir Pasta" não funciona no Docker
**Solução:** Dentro do container isolado, não há como abrir o explorador de arquivos nativamente. Copie o caminho `host_output_dir` (exibido na interface) e cole no seu sistema local.

### Exportação solicitada mas nenhum arquivo gerado
**Solução:** Isso costuma acontecer quando os filtros aplicados excluem 100% dos registros originais baixados. Cheque os logs e a variável `export_warning`.

---
← [Índice da documentação](README.md) · [Voltar ao projeto](../README.md)
