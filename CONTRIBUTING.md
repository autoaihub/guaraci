# Contribuindo para o Guaraci

Guia pratico para contribuicao tecnica.

## Regra principal de ambiente

- Desenvolvimento e validacao devem ser feitos em **Docker**.
- Execucao local sem Docker esta em **WIP** e nao deve ser baseline para aprovar mudanca.

## Setup rapido

```bash
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
docker build -t guaraci .
```

## Fluxo recomendado de desenvolvimento

1. Criar branch de trabalho.
2. Implementar mudanca pequena e isolada.
3. Rodar testes relevantes no container.
4. Atualizar documentacao impactada.
5. Abrir PR com descricao objetiva e comandos usados para validacao.

## Estrutura atual (alto nivel)

- `guaraci/core/`: contratos, configuracao, resultado e base de datasource.
- `guaraci/snis/`: fontes crawler (`snis`, `sinisa`) + legado BigQuery em `legacy/`.
- `guaraci/datasus/`: fontes PySUS (`sinan`, `sim`, `sih`).
- `guaraci/services/`: orquestracao de download e jobs assincronos.
- `guaraci/api/`: FastAPI + UI web estatica.
- `guaraci/cli/`: CLIs por fonte.

## Padroes de codigo

- Python 3.11+
- Formatacao: `black`
- Imports: `isort`
- Tipagem: `mypy`
- Testes: `pytest`

Comandos:

```bash
# testes
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# formatacao
docker run --rm -v "$(pwd):/app" guaraci python -m black guaraci/ tests/
docker run --rm -v "$(pwd):/app" guaraci python -m isort guaraci/ tests/

# tipagem
docker run --rm -v "$(pwd):/app" guaraci python -m mypy guaraci/
```

## Convencoes

- Modulos/funcoes: `snake_case`
- Classes: `CamelCase`
- Constantes: `UPPER_SNAKE_CASE`
- API publica em ingles (nomes de classes/metodos/params).
- Mensagens para usuario e logs podem estar em portugues.

## Testes por area

### Alterou API/UI/jobs

Rode ao menos:

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_api.py tests/test_jobs.py -v
```

### Alterou schemas/validacao de fontes

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_services.py -v
```

### Alterou datasource especifico

Rode testes do datasource e relacionados.

## Regras de documentacao

Sempre atualize docs quando houver mudanca de:
- parametros de fonte,
- comportamento de exportacao,
- estados de job,
- endpoints da API,
- UX da UI.

Arquivos principais:
- `README.md`
- `CHANGELOG.md`
- `AGENTS.md`
- `INSTALL.md`
- `DOCKER_WORKFLOW.md`
- `docs/ARCHITECTURE.md`
- `docs/API_REFERENCE.md`
- `docs/UI_GUIDE.md`
- `docs/SOURCES_AND_FILTERS.md`
- `docs/AI_HANDOFF_OPENDATASUS.md`

## Pull Request

Inclua no PR:
- contexto/problema,
- o que foi alterado,
- riscos e trade-offs,
- comandos de teste executados,
- impacto em docs.

PRs com mudanca funcional sem atualizacao de documentacao serao considerados incompletos.
