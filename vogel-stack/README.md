# Vogel Stack

`Vogel Stack` é um conjunto de documentos-base para repositórios que usam agentes de IA como parte real do fluxo de desenvolvimento, documentação e operação.

O objetivo desta pasta é transformar práticas testadas em um projeto específico em um padrão reutilizável para outros contextos, sem depender de regras subjetivas ou conhecimento tribal.

## Propósito

Esta stack ajuda a manter:

- documentação coerente com o código real;
- regras operacionais claras para agentes e humanos;
- matriz explícita do que é suportado, experimental ou apenas legado;
- contratos de entrada e saída mais estáveis para UI, API e automações;
- evolução arquitetural controlada;
- versionamento e changelog auditáveis;
- critérios mais objetivos para mudanças de produto e dashboard;
- guardrails para custo, execução e observabilidade.

## Estrutura

- `principios.md`: princípios permanentes para qualquer projeto.
- `operacao-agentes.md`: política operacional para uso de agentes, comandos e execuções.
- `registro-e-evidencias.md`: padrão para registry, manifestos e rastreabilidade de execuções.
- `documentacao-e-versionamento.md`: papéis dos docs, regras de atualização e convenções de versionamento.
- `evolucao-produto.md`: método para evoluir arquitetura, produto e dashboards sem ficar preso ao legado atual.
- `templates.md`: modelos de documentos para iniciar novos repositórios com o mesmo padrão.

## Como usar

Forma mínima de adoção em outro projeto:

1. copiar esta pasta para o novo repositório;
2. adaptar `templates.md` para gerar `AGENTS.md`, `README.md`, `docs/arquitetura.md`, `docs/versionamento.md` e `docs/changelog.md`;
3. ajustar fontes de verdade, fluxo de deploy, autenticação, matriz de suporte de ambiente e contratos do projeto alvo;
4. manter os documentos atualizados no mesmo ciclo em que o comportamento do produto mudar.

## Escopo

Esta stack não tenta impor uma linguagem, framework ou arquitetura única.

Ela define:

- critérios de clareza;
- disciplina de documentação;
- padrão operacional de agentes;
- padrão de evidência operacional e rastreabilidade de runs;
- disciplina de contratos, schemas e identificadores canônicos;
- método de evolução de produto;
- guardrails para evitar desperdício, opacidade e retrabalho.
