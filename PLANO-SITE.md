# Plano de reorganização do site do Guaraci

> Planejamento aprovado em 2026-08-10. Execução em etapa futura.
> Referências analisadas: `guaraci.html` (versão atual, 881 linhas), `AutoAI-Pandemics.html` + `AutoAI-Pandemics_files/` (site da AutoAI baixado), `hero-img.png` (logo AutoAI), https://sabiadatalake.com.br/.

## 1. Diagnóstico do site atual

O `guaraci.html` atual é sólido em conteúdo (catálogo completo das 91 bases, FAQ bem escrito, narrativa problema→solução), mas visualmente é "Bootstrap claro genérico":

- Tema claro com cards arredondados — não conversa com a estética escura/neon da logo AutoAI (índio cibernético, laranja + teal com glow).
- Sem identidade visual própria: a "logo" é um ícone `bi-sun-fill` do Bootstrap Icons.
- Única animação é o contador; sem animações de scroll, sem interatividade real.
- O catálogo das 91 bases é um accordion longo e passivo — difícil de explorar.
- "Como usar" tem só 2 cards — não ensina um leigo a instalar e rodar nada.
- Não há seção de financiadores/parceiros nem de ecossistema (AutoAI ↔ Guaraci ↔ Sabiá).
- Paleta atual (laranja `#f4a300` + verde-floresta `#244e3d`) destoa do teal da AutoAI (`#008374`/`#14b8a6`).

## 2. Direção visual

**Conceito: "amanhecer de dados"** — Guaraci é o deus-sol tupi-guarani; a AutoAI é o índio cibernético. O site do Guaraci é o *sol* desse universo: tema escuro tech com glow solar.

### Paleta (ponte entre Guaraci e AutoAI)
| Token | Valor | Papel |
|---|---|---|
| `--sun` | `#f7a41d` | Laranja-sol (herda o rosto laranja da logo AutoAI) |
| `--sun-2` | `#ffd166` | Amarelo-claro (raios, highlights) |
| `--ember` | `#f85a40` | Coral da AutoAI (acentos, CTAs secundários) |
| `--teal` | `#14b8a6` | Teal AutoAI (circuitos, links, dados) |
| `--teal-deep` | `#008374` | Teal-marca AutoAI |
| `--bg` | `#04120f` / `#05231f` | Fundo escuro (mesmo `--aa-dark` da AutoAI) |
| `--surface` | `rgba(255,255,255,.04)` | Cards glassmorphism |
| Texto | `#e8f2ee` / `#9db8b0` | Principal / secundário |

Gradiente-assinatura: `linear-gradient(135deg, #ffd166, #f7a41d 40%, #14b8a6)` — nasce no sol e termina no teal dos circuitos.

### Tipografia
- Títulos: **Space Grotesk** (tech, geométrica, moderna — upgrade sobre a Montserrat da AutoAI sem brigar com ela).
- Corpo: **Inter**.
- Código/terminal: **JetBrains Mono**.

### Logo do Guaraci (SVG, criada na execução)
Sol geométrico em perfil de amanhecer, com os **raios superiores desenhando traços de circuito** (linhas ortogonais a 45°, com pads circulares e "estrelas" de brilho nas pontas) — citação direta do cocar de circuitos da logo AutoAI. Disco solar em laranja `#f7a41d` com borda/extrusão escura (mesmo estilo flat-3D da logo AutoAI), circuitos em teal `#14b8a6` com glow verde-limão.

Entregáveis: `assets/logo-guaraci.svg` (ícone), versão horizontal com wordmark "Guaraci" em Space Grotesk, favicon, e versão monocromática para o footer. No hero, versão grande animada (raios de circuito "acendem" progressivamente via `stroke-dashoffset` + pulsos de glow).

## 3. Stack técnica

Site continua **um HTML estático** (deploy trivial: GitHub Pages), mas com bibliotecas de ponta via CDN:

| Biblioteca | Uso |
|---|---|
| **Tailwind (Play CDN) ou CSS custom com design tokens** | preferir CSS custom bem organizado — evita dependência do Play CDN em produção |
| **GSAP + ScrollTrigger** | animações de scroll de alto nível (parallax, pin, reveal em cascata, timeline do passo a passo) |
| **Lenis** | smooth scrolling premium |
| **particles/canvas próprio** | fundo do hero: constelação de nós e linhas (rede de dados) em teal, com sol nascendo |
| **CountUp.js** (ou manter contador próprio) | métricas animadas |
| **Typed.js ou animação própria** | terminal simulado digitando comandos reais do Guaraci |
| **Fuse.js** | busca fuzzy no catálogo das 91 bases |

Sem framework JS (React etc.) — nada justifica build step aqui. Acessibilidade: `prefers-reduced-motion` desliga GSAP/particles; contraste AA no tema escuro.

## 4. Nova arquitetura de seções (ordem)

1. **Navbar** — logo nova + links + botão GitHub; fundo glass escuro, barra de progresso de scroll no topo.
2. **Hero** — fundo canvas "rede de dados" + sol da logo nascendo; headline "Diversas bases. Um só caminho." mantida; badges com 91 bases / 5 áreas / gratuito; CTAs "Começar em 5 minutos" (→ passo a passo) e "GitHub". Menção "um projeto AutoAI-Pandemics (ICMC-USP)" com a logo do índio.
3. **O que é** (problema→solução) — manter conteúdo atual, redesenhar como comparação lado a lado com reveal animado; ilustrar o fluxo fonte oficial → Guaraci → seu computador com diagrama SVG animado (linhas de dados fluindo).
4. **Em números** — 4 métricas com CountUp + banda de impacto com gradiente-assinatura.
5. **Cinco áreas** — cards com tilt/hover glow, ícones no gradiente.
6. **Catálogo das 91 bases** — *upgrade principal de interatividade*: substituir accordion por **explorador com busca (Fuse.js) + filtros por área/fonte** (chips: DATASUS, Vigilância, Sisagua, Saúde indígena, IBGE, NASA, Saneamento…), grid de cards com contagem dinâmica ("mostrando X de 91"). Dados das bases movidos para um array JS (fonte única). Popover "quem mantém" vira detalhe no card.
7. **Como usar — passo a passo para leigos** (*seção nova, a mais importante*):
   - Timeline vertical com ScrollTrigger (passos acendem conforme o scroll):
     1. Instale Git e Docker (links, prints das telas de download, aviso de qual botão clicar);
     2. Copie o Guaraci (`git clone …`) — terminal simulado digitando;
     3. Suba com Docker (`docker compose up` ou comando real do repo);
     4. Peça uma base (exemplo real: dengue por estado/ano);
     5. Abra o resultado (CSV/Parquet — print do arquivo aberto em planilha).
   - "Prints de tela": para as etapas de terminal, usar **terminais simulados em HTML** (janela macOS-style, texto digitado com cursor) — sempre nítidos, tema do site, sem manutenção de imagem. Para telas externas (site do Docker, planilha com resultado), capturar screenshots reais na execução (Playwright ou capturas manuais) em `assets/screenshots/`.
   - Callouts "para leigos": o que é terminal, o que é Docker, quanto tempo demora, o que fazer se der erro.
   - Verificar os comandos exatos no README do repositório antes de escrever (não inventar CLI).
8. **Ecossistema** (*nova*) — diagrama AutoAI-Pandemics → Guaraci → Sabiá → sociedade, com as três logos e linhas animadas; explica "uso local hoje / Sabiá em construção" (substitui a seção "dois jeitos de acessar").
9. **Para quem é** — 4 cards atuais, restilizados.
10. **Fontes oficiais** — banda de confiança (Ministério da Saúde, IBGE, NASA, gov.br), restilizada.
11. **Financiadores e parceiros** (*nova*) — ver §5.
12. **FAQ** — manter as 8 perguntas atuais (ótimo conteúdo), restilizar como accordion escuro minimalista.
13. **CTA final** — "Dados que iluminam decisões" sobre gradiente-assinatura com glow do sol.
14. **Footer** — logo mono, links, "AutoAI-Pandemics (ICMC-USP) • Acesso aberto", contato vogel@usp.br.

## 5. Financiadores e parceiros

Seção com título tipo "Apoio e financiamento", logos em faixa clara (cards brancos sobre o tema escuro, para as logos coloridas funcionarem), com nome + papel embaixo:

| Instituição | Logo — origem |
|---|---|
| ICMC-USP | `AutoAI-Pandemics_files/icmc.png` |
| UTFPR | `AutoAI-Pandemics_files/utfpr.png` |
| AI4PEP | `AutoAI-Pandemics_files/AI4PEP2-logo.png` |
| IDRC | `AutoAI-Pandemics_files/idrc_logo_full_name_wordmark.jpg` |
| UK International Development (FCDO) | `AutoAI-Pandemics_files/uk-international-development-2.png` |
| Sabiá Data Lake | baixar de https://sabiadatalake.com.br/ na execução |

Na execução: copiar para `assets/partners/`, converter para WebP/PNG otimizado, altura uniforme (~48–56px), grayscale com cor no hover (padrão moderno). Logo da AutoAI (`logo-autoai.svg` existe nos assets baixados) entra no hero/ecossistema, não nesta faixa.

## 6. Estrutura de arquivos proposta

```
guaraci/
├── guaraci.html            (reescrito — ou index.html, se for virar GitHub Pages)
├── assets/
│   ├── logo-guaraci.svg / logo-guaraci-horizontal.svg / favicon.svg
│   ├── partners/           (6 logos otimizadas)
│   ├── autoai/             (logo-autoai.svg, hero do índio se usada)
│   └── screenshots/        (prints reais do passo a passo)
└── PLANO-SITE.md           (este arquivo)
```

CSS e JS podem ficar inline no HTML (mantém a portabilidade de arquivo único + pasta assets) ou em `assets/site.css`/`site.js` — decidir na execução conforme o tamanho.

## 7. Etapas de execução (futura)

1. **Logo** — desenhar `logo-guaraci.svg` + variantes; validar com o Luis antes de seguir.
2. **Assets** — copiar/otimizar logos de parceiros; baixar logo do Sabiá; extrair comandos reais do README do Guaraci.
3. **Esqueleto** — novo HTML com design tokens, navbar, hero (canvas + logo animada), footer.
4. **Seções de conteúdo** — migrar/restilizar seções 3–5, 9–13; mover as 91 bases para array JS e construir o explorador com busca/filtros.
5. **Passo a passo** — timeline GSAP + terminais simulados + screenshots.
6. **Ecossistema + financiadores.**
7. **Polimento** — responsivo, `prefers-reduced-motion`, contraste, SEO/OG tags, performance (lazy-load, logos otimizadas), teste em mobile.
8. **Verificação** — abrir no navegador, testar busca/filtros/animações, Lighthouse.

## 8. Modelo para execução

**Fable 5 é a escolha certa.** A execução é design frontend criativo de fôlego (SVG autoral da logo, animações GSAP coordenadas, ~2.000+ linhas de HTML/CSS/JS coesas) — exatamente o perfil em que o modelo de topo compensa; Opus 4.8 faria um bom site, mas a diferença aparece justamente em direção de arte e coesão visual. Sugestão: executar em 2–3 sessões (logo → site → polimento), validando a logo primeiro.
