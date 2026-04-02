# Evolução de Produto e Arquitetura

Este documento propõe um método para evoluir produtos digitais e dashboards sem ficar preso ao formato atual da interface ou ao acoplamento técnico existente.

## 1. Começar pelas respostas, não pelos widgets

A pergunta principal não é:

- qual gráfico temos hoje.

A pergunta correta é:

- quais respostas o produto precisa entregar para o usuário.

Exemplos de respostas desejadas:

- o que exige atenção imediata;
- onde está o maior desvio;
- qual cliente, área ou fluxo puxou o consumo;
- qual detalhe confirma a hipótese principal;
- quais ações operacionais podem ser tomadas a partir da leitura.

## 2. Método recomendado para dashboards

Sequência recomendada:

1. `Brainstorm`
2. `Concepção`
3. `Wireframe`
4. `Implementação`

### Brainstorm

Objetivo:

- listar perguntas de negócio;
- desafiar as soluções atuais;
- levantar alternativas visuais e modulares;
- separar identidade visual de semântica de status.

### Concepção

Objetivo:

- consolidar respostas prioritárias;
- definir módulos obrigatórios;
- propor navegação;
- explicitar a ordem de leitura desejada.

### Wireframe

Objetivo:

- definir o grid;
- definir proporções horizontais e verticais;
- definir quais módulos são protagonistas e quais são contextuais;
- reduzir a chance de a tela virar um relatório comprido.

### Implementação

Objetivo:

- materializar a direção já escolhida;
- validar com dados reais;
- corrigir os pontos de uso sem reabrir a concepção inteira a cada ajuste pequeno.

## 3. Padrão de leitura recomendado para dashboards operacionais

Em vez de empilhar tudo verticalmente, a tela deve conduzir o olhar em ordem de prioridade:

1. o que exige atenção;
2. onde o problema está;
3. por que ele está acontecendo;
4. qual detalhe confirma a leitura.

Isso normalmente pede:

- uma faixa executiva superior;
- um módulo principal de criticidade;
- um ou mais módulos de diagnóstico ao lado ou logo abaixo;
- uma área final de auditoria ou detalhamento contido.

## 4. Triage, diagnóstico e auditoria

Uma boa interface costuma misturar três camadas:

### Triage

Serve para:

- destacar exceções;
- mostrar status;
- priorizar o olhar.

### Diagnóstico

Serve para:

- explicar causas;
- mostrar tendência;
- expor composição ou drivers.

### Auditoria

Serve para:

- abrir detalhe;
- confirmar leitura;
- dar base para ação operacional.

O erro comum é colocar auditoria como protagonista e deixar triage escondida.

## 5. Evolução arquitetural em fases

Modelo prático:

### Fase 1: documentar e desacoplar

- descrever arquitetura real;
- extrair regras de negócio da UI;
- centralizar contratos e serviços;
- preservar o fluxo operacional existente.

### Fase 2: introduzir nova camada de backend

- expor serviços por API;
- padronizar contratos de entrada e saída;
- desacoplar frontend da fonte bruta;
- manter a origem dos dados, se necessário, até que a transição esteja madura.

### Fase 3: introduzir novo frontend

- reconstruir a UI com mais liberdade de layout;
- superar limitações da ferramenta de prototipação;
- manter equivalência funcional mínima antes de buscar refinamento.

### Fase 4: promover a nova superfície

- validar execução local, em contêiner e em deploy;
- tornar a nova superfície a interface principal;
- reclassificar a camada antiga como `legacy`, se ainda for necessário mantê-la.

### Fase 5: repaginação major

- só chamar de nova major quando a experiência, a navegação e a linguagem de produto realmente tiverem mudado de patamar.

## 6. Preservar o fluxo atual durante a transição

Mudanças estruturais não devem quebrar o caminho de entrega existente sem necessidade.

Regras úteis:

- manter o deploy atual enquanto a nova stack ainda é experimental;
- validar localmente e em Docker antes de promover a nova superfície;
- evitar que a migração arquitetural dependa de mudança simultânea de tudo.

## 7. Cores, identidade e status

Em dashboards, existem dois sistemas de cor diferentes:

- cor de identidade da marca, produto ou cliente;
- cor semântica de status, risco, progresso ou criticidade.

Esses sistemas não devem ser confundidos.

Boas práticas:

- usar cores de marca para identidade e contexto;
- usar gradientes ou escalas específicas para status;
- documentar a lógica da escala, especialmente quando ela carrega significado operacional.

## 8. Critério para não desperdiçar tempo com solução legada

Nem toda melhoria pontual vale a pena depois que um brainstorm mais forte redefiniu a direção.

Antes de implementar uma melhoria, perguntar:

- isso ainda converge com a direção de produto escolhida;
- isso reduz dívida de curto prazo;
- isso evita retrabalho;
- isso melhora algo que continuará existindo na próxima camada.

Se a resposta for não, registrar e postergar é melhor do que otimizar o legado sem retorno.
