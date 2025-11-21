# Contribuindo para o Guaraci

Obrigado por contribuir com o Guaraci! Este guia resume como escrever código e abrir contribuições de forma consistente com o restante do projeto.

## Visão geral do fluxo de desenvolvimento

- Sempre desenvolva usando o ambiente Docker fornecido no repositório.
- Rode testes, formatadores e checagem de tipos dentro do container.
- Mantenha novas funcionalidades pequenas, bem isoladas e com testes quando fizer sentido.

```bash
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
docker build -t guaraci .
```

## Estilo de código e ferramentas

O projeto segue o estilo PEP 8 com formatação automática.

- **Formatação**: use `black`.
- **Imports**: use `isort`.
- **Lint**: use `flake8` (quando configurado em pre-commit).
- **Tipos**: use `mypy` com type hints sempre que razoável.

Comandos recomendados (dentro do diretório do projeto):

```bash
# Rodar testes
docker run --rm guaraci python -m pytest tests/ -v

# Formatação
docker run --rm -v "$(pwd):/app" guaraci python -m black guaraci/
docker run --rm -v "$(pwd):/app" guaraci python -m isort guaraci/

# Checagem de tipos
docker run --rm -v "$(pwd):/app" guaraci python -m mypy guaraci/
```

Antes de abrir um PR, certifique-se de que:

- O código está formatado com `black` e `isort`.
- Não há erros de tipagem básicos reportados pelo `mypy`.
- Os testes relevantes passam.

## Convenções de nomenclatura

Siga o padrão já usado no código:

- **Módulos e arquivos**: `snake_case` (ex.: `sim_cli.py`, `sinan.py`).
- **Funções e métodos**: `snake_case` (ex.: `download`, `load_dataframe`, `describe_fields`).
- **Classes**: `CamelCase` (ex.: `SinanDataSource`, `SimDataSource`, `GuaraciConfig`).
- **Constantes**: `UPPER_SNAKE_CASE` (ex.: `NEGLECTED_DISEASES`, `UF_DICT`).
- Use nomes descritivos e evite abreviações obscuras.
- Mantenha a API pública em inglês (nomes de classes, métodos, parâmetros), mesmo quando mensagens e logs sejam em português.

## Docstrings, comentários e mensagens

- Use **docstrings em inglês** para classes, funções e métodos públicos, seguindo o padrão existente:
  - Pequena descrição.
  - Parâmetros / Returns documentados quando necessário.
- Comentários em linha devem ser raros e apenas quando o código não é autoexplicativo.
- Mensagens para usuários (CLI, logs de alto nível) podem ser em **português**, mantendo consistência com o restante do projeto.
- Use `loguru` para logging, com níveis adequados (`debug`, `info`, `warning`, `error`).

## Estrutura de novos módulos

Quando adicionar uma nova fonte de dados ou CLI, use os exemplos existentes (`SinanDataSource`, `SimDataSource`, `sinan_cli`, `sim_cli`) como referência:

- **DataSource**:
  - Herde de `guaraci.core.datasource.DataSource`.
  - Implemente pelo menos:
    - `download(...)`
    - `load_dataframe(...)`
  - Métodos auxiliares como `filter(...)`, `summary(...)`, `export(...)` e `describe_fields(...)` devem seguir a mesma assinatura/estilo quando fizer sentido.
- **CLI**:
  - Use `click` com grupos (`@click.group`) e subcomandos (`download`, `filter`, `summary`, `info`).
  - Utilize `rich` para barras de progresso e tabelas, seguindo o padrão de `sinan_cli.py`/`sim_cli.py`.

## Testes

- Crie testes em `tests/` seguindo o padrão existente.
- Para novas fontes de dados, priorize:
  - Testes de inicialização (nome, `output_path`).
  - Testes básicos para existência de métodos (`download`, `load_dataframe`, etc.).
  - Quando possível, isole dependências externas (por exemplo, PySUS/FTP) usando mocks.
- Lembre-se de que alguns testes podem precisar ser marcados com `skip` quando dependem de PySUS ou de rede externa.

## Commits e Pull Requests

- Mantenha commits focados em uma mudança lógica por vez.
- Descreva claramente no PR:
  - O problema resolvido ou a funcionalidade adicionada.
  - Como testar a mudança (comandos de Docker/pytest relevantes).
- Evite misturar refatoração extensa com correções pequenas na mesma PR.

Se tiver dúvidas sobre estilo ou estrutura, use como referência os módulos mais novos (`guaraci/core`, `guaraci/datasus/sinan.py`, `guaraci/datasus/sim.py`, `guaraci/cli/sinan_cli.py`, `guaraci/cli/sim_cli.py`) e siga o padrão deles.
## Changelog

Veja `CHANGELOG.md` para o histórico de versões e novidades.

