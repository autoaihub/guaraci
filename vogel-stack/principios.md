# Princípios Gerais

Este documento reúne princípios que devem permanecer válidos em diferentes projetos, independentemente da stack técnica específica.

## 1. O comportamento documentado deve refletir o sistema real

Documentação aspiracional só é útil quando está explicitamente marcada como futura.

Regra prática:

- `README.md` descreve o estado operacional atual;
- `docs/arquitetura.md` descreve a arquitetura existente;
- docs de futuro devem ser separados e claramente rotulados como planejados ou experimentais;
- qualquer divergência entre código e documentação deve ser tratada como dívida visível.

## 2. Toda aplicação precisa de fontes de verdade explícitas

Cada projeto deve declarar quais são suas fontes de verdade, por exemplo:

- APIs externas;
- banco de dados;
- cache local;
- arquivos de configuração;
- sessão/autenticação;
- filas ou eventos.

Toda mudança deve preservar a coerência entre essas camadas.

## 3. Clareza operacional é tão importante quanto correção técnica

Um sistema pode estar tecnicamente certo e ainda assim ser difícil de operar, auditar ou explicar.

Princípios:

- interfaces devem priorizar leitura útil, não apenas exibição de dados;
- permissões e restrições devem ser auditáveis;
- erros precisam ser visíveis;
- filtros, estados e fluxos precisam ser previsíveis;
- relatórios e dashboards devem responder perguntas reais de operação.

## 4. Evolução estrutural deve ser progressiva

Reescrita total raramente é o primeiro passo certo.

Sequência preferencial:

1. documentar o estado atual com honestidade;
2. extrair regras de negócio da interface;
3. criar contratos internos e serviços reutilizáveis;
4. introduzir novas camadas sem quebrar o fluxo atual;
5. migrar a operação quando a nova camada estiver estável.

## 5. Mudanças seguras exigem contratos explícitos

Antes de alterar um módulo, validar:

- se o contrato de dados mudou;
- se a autenticação ou autorização foi impactada;
- se nomes, listas, filtros ou métricas exibidas mudaram;
- se a interpretação de gráficos, KPIs ou indicadores mudou;
- se documentação, changelog e versão precisam ser atualizados.

## 6. Configuração deve ser centralizada e auditável

Boas práticas:

- preferir variáveis de ambiente para novas configurações sensíveis;
- concentrar configuração compartilhada em um ponto explícito;
- não espalhar valores operacionais importantes em múltiplos arquivos;
- documentar cada variável relevante e seu efeito.

## 7. Segredos não devem virar conteúdo documental

Regras mínimas:

- não publicar tokens, senhas ou chaves em `README`, exemplos ou docs técnicos;
- não introduzir novos segredos hardcoded em código novo;
- se um segredo existente ainda não foi migrado, registrar isso como limitação conhecida, não como padrão.

## 8. Observabilidade precisa existir desde cedo

Mesmo em protótipos, o projeto deve oferecer algum grau de rastreabilidade.

Base recomendada:

- logs de backend;
- logs de frontend ou cliente, quando aplicável;
- rotação ou retenção;
- mensagens suficientes para diagnosticar falhas sem depender de memória humana.

## 9. Versionamento e rastreabilidade não são opcionais

Mudanças relevantes precisam aparecer em algum lugar claro:

- `docs/versionamento.md` para evolução funcional e arquitetural;
- `docs/changelog.md` para entregas concretas já realizadas.

## 10. Produto deve ser pensado pelas respostas que precisa entregar

Especialmente em dashboards, o ponto de partida não deve ser o gráfico atual.

A pergunta correta é:

- quais perguntas o usuário precisa conseguir responder;
- o que exige atenção imediata;
- qual nível de detalhe confirma ou explica a leitura principal.

O visual deve nascer dessa necessidade, não do legado da ferramenta anterior.

## 11. Modos de execução suportados devem ser explícitos

Projetos maduros quase sempre têm mais de um caminho possível de execução, mas nem todos têm o mesmo nível de suporte.

Padrão recomendado:

- declarar no `README.md` qual é o caminho oficialmente suportado;
- marcar explicitamente o que está em `WIP`, `alpha`, `experimental` ou `legacy`;
- evitar documentar fluxos secundários como se fossem equivalentes ao fluxo principal;
- manter comandos de validação coerentes com o caminho oficialmente suportado.

## 12. Contratos declarativos são melhores que comportamento implícito

Quando o projeto expõe parâmetros, filtros, jobs ou automações, o contrato deve ser declarativo e reaproveitável.

Boas práticas:

- definir schemas ou contratos em um ponto explícito;
- derivar UI, API ou automações desse contrato quando possível;
- rejeitar parâmetros desconhecidos por padrão;
- distinguir claramente campos obrigatórios, opcionais, técnicos e derivados.

## 13. Identificadores canônicos devem prevalecer

Aliases convenientes demais costumam gerar ambiguidade entre código, API, documentação e operação.

Regra prática:

- escolher nomes canônicos para entidades expostas externamente;
- usar esses nomes na documentação, API, UI e persistência;
- só introduzir aliases quando houver motivo forte de compatibilidade;
- quando houver alias, documentar o motivo, o escopo e a estratégia de depreciação.

## 14. UX de filtros deve separar intenção de negócio e refinamento técnico

Quando uma interface expõe filtros, o bloco principal deve priorizar o que o usuário realmente entende como consulta principal.

Padrão útil:

- filtros nativos da fonte ou do domínio ficam no fluxo básico;
- refinamentos locais, tuning técnico e overrides vão para uma seção avançada;
- campos fundamentais de destino, saída ou escopo não devem ficar escondidos atrás de opções avançadas.

## 15. Semântica de saída deve ser estável e auditável

Projetos que geram artefatos, exportações ou resultados intermediários precisam manter contratos de saída compreensíveis.

Base recomendada:

- definir quais artefatos são sempre esperados;
- distinguir resultado final, material bruto, manifestos e avisos;
- tornar rastreável quando houve saída parcial, truncada ou só parcialmente exportada;
- documentar os campos de saída que clientes, usuários e agentes podem confiar.

## 16. Evidência operacional deve ser persistida

Quando o projeto executa jobs, pipelines, automações ou agentes recorrentes, não basta ter código e documentação conceitual.

Também é preciso materializar:

- o que foi rodado;
- com qual escopo;
- quando foi rodado;
- quais artefatos foram gerados;
- qual foi o resultado principal.

Em projetos com esse perfil, manter um `registry` e manifestos por execução deixa de ser luxo e passa a ser parte da rastreabilidade mínima.
