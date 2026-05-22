# VogelStack — Project Review and Improvements

*Este documento consolida a revisão arquitetural e as recomendações de melhoria mapeadas pela stack Vogel para o projeto Guaraci.*

## 1. Avaliação do Estado Atual

- O fluxo **Docker-first** provou ser coerente e maduro para operação regular.
- O registro de fontes e o schema declarativo de parâmetros formam uma base sólida e escalável.
- O subsistema de Jobs (retry, cancelamento, logs, ETA) fornece uma forte sustentação operacional.
- A integração do OpenDataSUS avançou significativamente, introduzindo nomes canônicos, preview de jobs, diagnósticos ricos e segmentação inteligente.
- A cobertura de documentação reflete os fluxos reais de operação.

## 2. Pontos Fortes (Strengths)

- **Direção de Produto**: Foco prático em tornar downloads de saúde pública acessíveis para não especialistas.
- **Base Técnica**: Separação limpa entre `DownloadService` e `DownloadJobService`. O contrato `JobResult` unifica fontes heterogêneas.
- **Evolução UX**: Preview de tamanho antes do download previne frustrações em extrações massivas. A interface orientada a schema evita hardcoding excessivo.

## 3. Áreas de Melhoria (Críticas)

### 3.1 Arquitetura e Código
- **Ruído no Repositório**: A normalização de line-endings melhorou, mas ainda há risco de poluição de diff em diferentes ambientes.
- **Responsabilidades Sobrecarregadas**: O datasource do OpenDataSUS acumula resolução de API, execução, filtro, preview e segmentação. Futuramente deve ser quebrado em utilitários menores.
- **Contratos de Teste**: A estratégia de testes é útil, mas os contornos de regressão para preview, segmentação e tradução de caminhos host precisam ser mais explícitos.

### 3.2 Experiência do Usuário (UX)
- **Heurísticas no Frontend**: A UI ainda toma decisões baseadas em nomes de parâmetros em vez de metadados ricos no schema (embora a introdução de `phase` tenha amenizado isso).
- **Assimetria de Preview**: Fontes OpenDataSUS têm preview rico; crawler e PySUS oferecem apenas visões estruturais.
- **Completude vs. Falha**: Usuários precisam entender mais claramente se um download demorado resultará em arquivos únicos, segmentados, ou apenas dados crus.

## 4. Recomendações e Melhorias Prioritárias

### P0. Confiabilidade Operacional
1. **Erros Acionáveis**: Distinguir claramente erros de rede, falhas de validação, erros de exportação e cancelamentos em todas as fontes.
2. **Retry Robusto**: Refinar políticas de repetição para crawler, FTP e API, registrando o contexto exato da falha para reprodução.

### P1. Evolução do Schema e Frontend
1. **Eliminar Heurísticas**: Enriquecer o `SourceParameterSpec` com mais hints visuais e de comportamento para aliviar a lógica no frontend.
2. **Padronização Visual**: Manter diretórios de saída e opções básicas separados de controles técnicos em todas as famílias de fontes (Crawler, PySUS, API).

### P2. Expansão Sustentável e Integração
1. **Escala OpenDataSUS**: Manter o ritmo de adição de fontes canônicas preservando o `DownloadService` declarativo.
2. **Manifestos**: Padronizar rigorosamente a estrutura de manifestos entre as três arquiteturas de extração para facilitar integrações downstream.
3. **Paths Visíveis**: Sempre priorizar a exibição de diretórios host (físicos) em vez de caminhos de container virtuais nos outputs da UI.

---
← [Índice da documentação](README.md) · [Voltar ao projeto](../README.md)
