# Registro e Evidências Operacionais

Este documento define um padrão para projetos que executam pipelines, jobs, agentes, integrações ou análises recorrentes e precisam manter evidência material do que foi rodado.

## 1. O que este documento cobre

Ele complementa:

- `documentacao-e-versionamento.md`, que define papéis dos documentos;
- `operacao-agentes.md`, que define quem prepara, quem executa e como colaborar;
- `principios.md`, que define rastreabilidade como princípio.

Aqui o foco é:

- como registrar execuções;
- como ligar entradas, saídas e artefatos;
- como distinguir histórico de execução de changelog e versionamento.

## 2. Changelog não substitui registry

Cada artefato tem papel diferente:

- `docs/changelog.md`: o que foi entregue ao produto ou ao repositório;
- `docs/versionamento.md`: como o produto evoluiu por versão;
- `registry` de execução: o que foi rodado, quando, com qual escopo, com quais artefatos e com qual resultado.

Projetos com jobs, pipelines, modelos, agentes ou automações recorrentes não devem depender só de changelog para auditoria operacional.

## 3. Quando um registry é recomendado

O padrão passa a ser fortemente recomendado quando houver:

- pipelines de dados;
- treinos ou avaliações de modelos;
- execuções por ambiente, cliente ou escopo;
- jobs com múltiplos estágios;
- artefatos persistidos em diretórios por rodada;
- automações acionadas por agentes;
- necessidade de reproduzir uma execução específica sem memória oral.

## 4. Campos mínimos de um registro de execução

O formato exato pode variar, mas o registro deveria capturar pelo menos:

- timestamp da execução;
- `run_id` único;
- `pipeline_run_id` ou correlato para agrupar estágios;
- estágio ou tipo de execução;
- escopo, ambiente, cliente ou fonte;
- versão, algoritmo ou modo de execução, quando aplicável;
- intervalo temporal ou filtros principais;
- fingerprint ou referência do input;
- localização dos artefatos gerados;
- status, confiança ou observação operacional.

## 5. Manifesto por run

Quando a execução gera múltiplos arquivos, vale manter um manifesto por run.

Esse manifesto deve responder:

- quais arquivos foram gerados;
- quais são finais e quais são auxiliares;
- o que estava ausente;
- se houve saída parcial.

## 6. Estrutura prática recomendada

Modelo simples e reutilizável:

```text
reports/
  runs/
    <run_id>/
      summary.json
      artifacts.json
      <artefatos>
  registry.csv
```

O diretório por run concentra o contexto local da rodada.

O `registry.csv` ou equivalente serve para comparação transversal entre execuções.

## 7. Relação com agentes

Projetos agent-friendly ganham muito quando o registry já existe, porque o agente pode:

- comparar execuções sem inferir demais;
- localizar artefatos rapidamente;
- resumir progresso por estágio;
- detectar lacunas de cobertura entre escopos;
- evitar repetir trabalho já materializado.

## 8. Qualidade mínima da evidência

Uma boa evidência operacional deve permitir responder:

1. o que foi executado;
2. com qual escopo;
3. quais entradas foram usadas;
4. quais saídas foram produzidas;
5. onde estão os artefatos;
6. qual foi o resultado principal;
7. o que ainda ficou pendente ou parcial.

## 9. O que não fazer

Evitar:

- deixar artefatos soltos sem identificador de execução;
- salvar múltiplas saídas finais sobrescrevendo contexto sem nenhum histórico;
- misturar runbook, changelog e evidência operacional no mesmo documento;
- depender de nomes manuais ou memória humana para descobrir o que foi rodado.

## 10. Template mínimo de registry

```text
recorded_at_utc,run_id,pipeline_run_id,stage,scope,mode,input_fingerprint,status,artifact_dir,note
```

Campos extras podem ser adicionados conforme o domínio, por exemplo:

- métricas;
- versão de schema;
- thresholds;
- ambiente;
- links para dashboards;
- usuário ou automação que disparou a rodada.
