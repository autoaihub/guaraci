/* Guaraci — AutoAI-Pandemics | deck generator (pptxgenjs) */
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";          // 13.33 x 7.5
pres.author = "Luis Felipe Vogel Lopes";
pres.title = "Guaraci — AutoAI-Pandemics";
const W = 13.33, H = 7.5;

/* ---------- palette ---------- */
const TEAL_DARK = "0E3A43", TEAL_DEEP = "0A2E35", TEAL = "1C7293", TEAL_LT = "8FB9C0";
const GOLD = "EFA63B", GOLD_BR = "F6C25A";
const CREAM = "F5F6F3", INK = "1C2B2F", MUTED = "627179", WHITE = "FFFFFF", LINEC = "DEE4E1";
const BRONZE = "BC824A", SILVER = "9CABB0", OURO = "E0B23C";
const HEAD = "Georgia", BODY = "Calibri";

/* ---------- helpers ---------- */
const sh = (o = {}) => Object.assign({ type: "outer", color: "0A2E35", blur: 8, offset: 2, angle: 135, opacity: 0.13 }, o);

function ring(slide, cx, cy, r, color, width, transp) {
  slide.addShape(pres.shapes.OVAL, { x: cx - r, y: cy - r, w: 2 * r, h: 2 * r, fill: { color: CREAM, transparency: 100 }, line: { color, width, transparency: transp || 0 } });
}
function lightSun(slide) {
  ring(slide, 13.05, 0.26, 0.72, GOLD, 1.25, 58);
  ring(slide, 13.05, 0.26, 0.46, GOLD, 1.25, 32);
  slide.addShape(pres.shapes.OVAL, { x: 13.05 - 0.15, y: 0.26 - 0.15, w: 0.30, h: 0.30, fill: { color: GOLD } });
}
function darkSun(slide, corner) {
  let cx = W - 1.0, cy = 1.0;
  if (corner === "br") { cx = W - 1.0; cy = H - 1.0; }
  if (corner === "bl") { cx = 1.0; cy = H - 1.0; }
  ring(slide, cx, cy, 1.85, GOLD, 1.5, 60);
  ring(slide, cx, cy, 1.35, GOLD, 1.5, 45);
  slide.addShape(pres.shapes.OVAL, { x: cx - 0.95, y: cy - 0.95, w: 1.9, h: 1.9, fill: { color: GOLD, transparency: 8 } });
}
function contentHead(slide, kicker, title) {
  lightSun(slide);
  slide.addShape(pres.shapes.OVAL, { x: 0.6, y: 0.64, w: 0.17, h: 0.17, fill: { color: GOLD } });
  slide.addText(kicker.toUpperCase(), { x: 0.88, y: 0.5, w: 11, h: 0.36, fontFace: BODY, fontSize: 12.5, bold: true, color: TEAL, charSpacing: 2, margin: 0, valign: "middle" });
  slide.addText(title, { x: 0.58, y: 0.92, w: 11.6, h: 0.85, fontFace: HEAD, fontSize: 31, bold: true, color: INK, margin: 0, valign: "middle" });
}
function card(slide, x, y, w, h, opts = {}) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: opts.fill || WHITE }, line: { color: opts.border || LINEC, width: opts.bw || 1.25 }, rectRadius: 0.08, shadow: sh(opts.shadow || {}) });
}
function strip(slide, y, runs, opts = {}) {
  const h = opts.h || 0.9;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 12.13, h, fill: { color: opts.fill || TEAL_DARK }, rectRadius: 0.07, shadow: sh({ opacity: 0.12 }) });
  slide.addText(runs, { x: 0.95, y, w: opts.tw || 11.4, h, fontFace: BODY, fontSize: opts.fs || 14, color: opts.color || WHITE, valign: "middle", margin: 0, align: opts.align || "left" });
}
function footer(slide, n, dark = false) {
  const c = dark ? TEAL_LT : MUTED;
  slide.addText([{ text: "Guaraci", options: { bold: true, color: dark ? GOLD : TEAL } }, { text: "  ·  AutoAI-Pandemics", options: { color: c } }],
    { x: 0.6, y: H - 0.46, w: 8, h: 0.3, fontFace: BODY, fontSize: 9, margin: 0, valign: "middle" });
  slide.addText(String(n), { x: W - 1.1, y: H - 0.46, w: 0.5, h: 0.3, fontFace: BODY, fontSize: 9, color: dark ? "DCEAEC" : c, align: "right", margin: 0, valign: "middle" });
}
function arrow(slide, x, y, color = GOLD, size = 20) {
  slide.addText("→", { x, y, w: 0.4, h: 0.4, fontSize: size, bold: true, color, align: "center", valign: "middle", margin: 0, fontFace: BODY });
}
function flowBox(slide, x, y, w, h, title, desc, o = {}) {
  card(slide, x, y, w, h, { fill: o.fill || WHITE, border: o.border || LINEC, bw: o.bw || 1.25, shadow: { blur: 6, offset: 2, opacity: 0.1 } });
  slide.addText([
    { text: title, options: { bold: true, color: o.titleColor || TEAL_DARK, fontSize: o.titleSize || 13, breakLine: true, fontFace: BODY } },
    ...(desc ? [{ text: desc, options: { color: o.descColor || MUTED, fontSize: o.descSize || 10.5, fontFace: BODY } }] : []),
  ], { x: x + 0.16, y: y + 0.14, w: w - 0.32, h: h - 0.28, valign: "top", margin: 0, paraSpaceAfter: 5, lineSpacingMultiple: 1.02 });
}
function S() { return pres.addSlide(); }

/* ===================================================================== */
/* 1 · CAPA */
let s = S(); s.background = { color: TEAL_DARK };
darkSun(s, "tr");
s.addText("TUPI-GUARANI  ·  GUARACI = O SOL", { x: 0.95, y: 1.45, w: 8, h: 0.4, fontFace: BODY, fontSize: 13, bold: true, color: GOLD, charSpacing: 2.5, margin: 0 });
s.addText("Guaraci", { x: 0.9, y: 1.95, w: 9, h: 1.3, fontFace: HEAD, fontSize: 66, bold: true, color: GOLD_BR, margin: 0 });
s.addText("Coleta automatizada de dados públicos para pesquisa", { x: 0.95, y: 3.35, w: 9.5, h: 0.6, fontFace: BODY, fontSize: 22, color: WHITE, margin: 0 });
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.95, y: 4.2, w: 5.35, h: 0.62, fill: { color: TEAL_DARK }, line: { color: GOLD, width: 1.25 }, rectRadius: 0.31 });
s.addText("um componente do projeto AutoAI-Pandemics", { x: 0.95, y: 4.2, w: 5.35, h: 0.62, fontFace: BODY, fontSize: 13, italic: true, color: GOLD_BR, align: "center", valign: "middle", margin: 0 });
s.addText([
  { text: "Luis Felipe Vogel Lopes", options: { bold: true, color: WHITE } },
  { text: "    nUSP 13730051    ·    vogel@usp.br", options: { color: TEAL_LT } },
], { x: 0.95, y: 6.35, w: 11, h: 0.4, fontFace: BODY, fontSize: 14, margin: 0 });
s.addText("Universidade de São Paulo  ·  Guaraci v0.5.2", { x: 0.95, y: 6.78, w: 11, h: 0.35, fontFace: BODY, fontSize: 11, color: TEAL_LT, margin: 0 });
s.addNotes("Abertura (0:30). Guaraci = o sol na mitologia tupi-guarani: a ideia é iluminar/centralizar dados públicos de saúde e ambiente. Eu sou o Luis, trabalho na camada de coleta de dados do AutoAI-Pandemics.");

/* 2 · AUTOAI-PANDEMICS */
s = S(); s.background = { color: CREAM };
contentHead(s, "Projeto-mãe", "AutoAI-Pandemics");
card(s, 0.6, 1.95, 5.45, 3.45);
s.addText("O QUE É", { x: 0.85, y: 2.12, w: 5, h: 0.35, fontFace: BODY, fontSize: 12.5, bold: true, color: GOLD, charSpacing: 1.5, margin: 0 });
s.addText([
  { text: "IA para preparação e resposta a epidemias e pandemias.", options: { color: INK, fontSize: 14.5, breakLine: true } },
  { text: "Missão: democratizar a IA e a ciência de dados para quem não é especialista — biólogos, médicos e epidemiologistas.", options: { color: TEAL, fontSize: 14.5, bold: true } },
], { x: 0.85, y: 2.55, w: 4.95, h: 2.7, fontFace: BODY, valign: "top", margin: 0, paraSpaceAfter: 10, lineSpacingMultiple: 1.05 });
card(s, 6.25, 1.95, 6.48, 3.45);
s.addText([
  { text: "Coordenação   ", options: { bold: true, color: TEAL } },
  { text: "André de Carvalho — PI (USP/ICMC) · Robson Bonidia — Co-PI (UTFPR, Paraná)", options: { color: INK, breakLine: true } },
  { text: "Rede   ", options: { bold: true, color: TEAL } },
  { text: "Hub brasileiro da AI4PEP (Global South AI for Pandemic & Epidemic Preparedness & Response)", options: { color: INK, breakLine: true } },
  { text: "Financiamento   ", options: { bold: true, color: TEAL } },
  { text: "IDRC — agência pública de fomento à pesquisa do Canadá (programa IA para Saúde Global)", options: { color: INK, breakLine: true } },
  { text: "Pilares   ", options: { bold: true, color: TEAL } },
  { text: "Epidemiologia automatizada · bioinformática · combate à desinformação", options: { color: INK } },
], { x: 6.5, y: 2.15, w: 6.0, h: 3.1, fontFace: BODY, fontSize: 12.5, valign: "top", margin: 0, paraSpaceAfter: 9, lineSpacingMultiple: 1.02 });
strip(s, 5.7, [
  { text: "Única iniciativa do Brasil entre ~21 selecionadas em chamada global (AI4PEP · IDRC · UK Int'l Development) — grant ~CAD 206 mil.", options: { bold: true } },
  { text: "     autoaipandemics.icmc.usp.br", options: { color: GOLD_BR } },
], { fs: 13.5 });
footer(s, 2);
s.addNotes("AutoAI-Pandemics (2:00). É o guarda-chuva. PI André (USP), Co-PI Robson (UTFPR-Paraná). Financiado pelo IDRC (Canadá) via rede AI4PEP. A missão é democratizar IA/dados para não-especialistas — guarde isso, é o fio da meada. O projeto tem vários pilares e TODOS dependem de dados: é aí que o Guaraci entra.");

/* 3 · ONDE O GUARACI ENTRA */
s = S(); s.background = { color: CREAM };
contentHead(s, "Posicionamento", "Onde o Guaraci entra");
s.addText("O AutoAI-Pandemics precisa de dados públicos em escala e atualizados. O Guaraci é essa camada de aquisição.", { x: 0.6, y: 1.82, w: 12.1, h: 0.55, fontFace: BODY, fontSize: 15, italic: true, color: MUTED, margin: 0 });
card(s, 0.6, 2.55, 5.95, 1.95, { border: GOLD, bw: 1.5 });
s.addText("Guaraci — plataforma de coleta", { x: 0.85, y: 2.72, w: 5.5, h: 0.4, fontFace: BODY, fontSize: 15, bold: true, color: TEAL_DARK, margin: 0 });
s.addText("Baixa dados públicos direto da fonte oficial. É o que vou mostrar hoje.", { x: 0.85, y: 3.18, w: 5.5, h: 1.1, fontFace: BODY, fontSize: 13, color: MUTED, margin: 0, valign: "top" });
card(s, 6.78, 2.55, 5.95, 1.95);
s.addText("Guaraci — datalake", { x: 7.03, y: 2.72, w: 5.5, h: 0.4, fontFace: BODY, fontSize: 15, bold: true, color: TEAL_DARK, margin: 0 });
s.addText("Repositório do projeto, no braço do Prof. Robson (UTFPR / Paraná). É o destino dos dados.", { x: 7.03, y: 3.18, w: 5.5, h: 1.1, fontFace: BODY, fontSize: 13, color: MUTED, margin: 0, valign: "top" });
strip(s, 4.7, [{ text: "Meu papel: a automação da coleta — o elo que abastece o datalake de forma contínua e rastreável.", options: { bold: true } }], { fs: 14.5, fill: TEAL });
const f3 = [["Fontes públicas", 0.6, false], ["Guaraci · coletor", 4.85, true], ["Datalake", 9.1, false]];
f3.forEach(([t, x, hot], i) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.85, w: 3.7, h: 0.95, fill: { color: WHITE }, line: { color: hot ? GOLD : LINEC, width: hot ? 1.75 : 1.25 }, rectRadius: 0.09, shadow: sh({ blur: 6, offset: 2, opacity: 0.1 }) });
  s.addText(t, { x, y: 5.85, w: 3.7, h: 0.95, fontFace: BODY, fontSize: 14, bold: true, color: TEAL_DARK, align: "center", valign: "middle", margin: 0 });
  if (i < 2) arrow(s, x + 3.75, 6.12, GOLD, 20);
});
footer(s, 3);
s.addNotes("Posicionamento (1:30). Deixe claro que há DOIS Guaraci: a plataforma (ferramenta de coleta) e o datalake (repositório, com o Robson no Paraná). Minha contribuição específica é a automação da coleta — a seta do meio.");

/* 4 · O PROBLEMA */
s = S(); s.background = { color: CREAM };
contentHead(s, "Motivação", "O problema");
card(s, 0.6, 1.95, 6.5, 3.45);
s.addText([
  { text: "Dado público fragmentado", options: { bold: true, color: INK, breakLine: true } },
  { text: "Cada fonte expõe a informação de um jeito: páginas web, APIs, servidores FTP.", options: { color: MUTED, fontSize: 12.5, breakLine: true } },
  { text: "Formatos legados", options: { bold: true, color: INK, breakLine: true } },
  { text: "Arquivos antigos e comprimidos, difíceis de abrir.", options: { color: MUTED, fontSize: 12.5, breakLine: true } },
  { text: "Barreiras técnicas", options: { bold: true, color: INK, breakLine: true } },
  { text: "Autenticação, paginação, parsing — semanas de “encanamento” antes da ciência.", options: { color: MUTED, fontSize: 12.5 } },
], { x: 0.85, y: 2.15, w: 6.0, h: 3.05, fontFace: BODY, fontSize: 14, valign: "top", margin: 0, paraSpaceAfter: 7, lineSpacingMultiple: 1.02 });
const chips = [["DATASUS", 7.45, 2.2], ["OpenDataSUS", 10.25, 2.2], ["gov.br", 7.45, 3.45], ["NASA", 10.25, 3.45]];
chips.forEach(([t, x, y]) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.35, h: 1.0, fill: { color: WHITE }, line: { color: TEAL, width: 1.25 }, rectRadius: 0.1, shadow: sh({ blur: 5, offset: 2, opacity: 0.1 }) });
  s.addText(t, { x, y, w: 2.35, h: 1.0, fontFace: BODY, fontSize: 14, bold: true, color: TEAL, align: "center", valign: "middle", margin: 0 });
});
s.addText("fontes dispersas, sem padrão", { x: 7.45, y: 4.62, w: 5.15, h: 0.35, fontFace: BODY, fontSize: 11.5, italic: true, color: MUTED, align: "center", margin: 0 });
strip(s, 5.7, [{ text: "Quem precisa do dado é o pesquisador de saúde e ambiente — não o profissional de TI.", options: { bold: true, color: INK } }], { fs: 15, fill: GOLD });
footer(s, 4);
s.addNotes("O problema (1:30). Conte a dor concreta: para montar uma série de internações por UF/ano você hoje cata FTP, decodifica formato antigo e junta arquivo por arquivo. Feche com o público-alvo do AutoAI-Pandemics: o epidemiologista, o médico, o biólogo — não é de TI.");

/* 5 · O QUE FAZ */
s = S(); s.background = { color: CREAM };
contentHead(s, "Visão geral", "O que a plataforma faz");
card(s, 0.6, 1.95, 12.13, 1.45, { fill: TEAL_DARK, border: TEAL_DARK });
s.addText("Baixa dados públicos, direto da fonte oficial, e entrega prontos para análise.", { x: 1.0, y: 1.95, w: 11.3, h: 1.45, fontFace: HEAD, fontSize: 24, bold: true, color: WHITE, valign: "middle", margin: 0 });
const ifaces = [["Web UI", "Para qualquer usuário, com aba avançada.", 0.6], ["API REST", "Para integrar com outros sistemas.", 4.65], ["CLI", "Para automação e scripts.", 8.7]];
ifaces.forEach(([t, d, x]) => {
  card(s, x, 3.65, 3.78, 1.7);
  s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: 3.88, w: 0.22, h: 0.22, fill: { color: GOLD } });
  s.addText(t, { x: x + 0.6, y: 3.8, w: 3.0, h: 0.4, fontFace: BODY, fontSize: 16, bold: true, color: TEAL_DARK, margin: 0, valign: "middle" });
  s.addText(d, { x: x + 0.27, y: 4.35, w: 3.3, h: 0.85, fontFace: BODY, fontSize: 12.5, color: MUTED, margin: 0, valign: "top" });
});
strip(s, 5.7, [{ text: "~80 fontes integradas", options: { bold: true, color: GOLD_BR } }, { text: "   de saúde e de ambiente, sempre da fonte primária oficial.", options: {} }], { fs: 14.5 });
footer(s, 5);
s.addNotes("O que faz (1:00). Uma frase resume tudo. Três interfaces, um motor só, rodando em container. ~80 fontes.");

/* 6 · TRÊS MECANISMOS */
s = S(); s.background = { color: CREAM };
contentHead(s, "Integração", "Como acessa as fontes");
const mech = [
  ["Crawler", "Raspa páginas web quando o dado só existe em HTML.", "Mais manual de configurar e sensível a mudanças no site.", 0.6],
  ["API", "Integração limpa e estruturada (REST, paginada).", "O caminho mais robusto, quando a fonte oferece.", 4.65],
  ["FTP", "Servidores de arquivos legados — o padrão do DATASUS.", "A plataforma decodifica os formatos antigos automaticamente.", 8.7],
];
mech.forEach(([t, d, e, x]) => {
  card(s, x, 1.95, 3.78, 3.45);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.27, y: 2.2, w: 1.7, h: 0.55, fill: { color: TEAL }, rectRadius: 0.27 });
  s.addText(t, { x: x + 0.27, y: 2.2, w: 1.7, h: 0.55, fontFace: BODY, fontSize: 15, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
  s.addText(d, { x: x + 0.27, y: 2.95, w: 3.25, h: 1.4, fontFace: BODY, fontSize: 13.5, color: INK, margin: 0, valign: "top" });
  s.addText(e, { x: x + 0.27, y: 4.4, w: 3.25, h: 0.85, fontFace: BODY, fontSize: 12, italic: true, color: MUTED, margin: 0, valign: "top" });
});
strip(s, 5.7, [{ text: "Cobre saúde (DATASUS, OpenDataSUS) e ambiente (NASA — clima, chuva, queimadas). A plataforma abstrai os três mecanismos.", options: {} }], { fs: 13.5 });
footer(s, 6);
s.addNotes("Mecanismos (2:00). Não entrar fonte por fonte. A mensagem: cada fonte entrega o dado de um jeito (web/API/FTP) e a plataforma esconde essa diferença. Crawler é o mais trabalhoso de manter.");

/* 7 · EXPERIÊNCIA */
s = S(); s.background = { color: CREAM };
contentHead(s, "Uso", "A experiência de quem usa");
const steps = [["1", "Escolhe a fonte", 0.6], ["2", "Preenche um formulário simples", 3.65], ["3", "Acompanha o progresso", 6.7], ["4", "Recebe CSV / Parquet", 9.75]];
steps.forEach(([n, t, x], i) => {
  card(s, x, 2.25, 2.85, 2.2);
  s.addShape(pres.shapes.OVAL, { x: x + 1.07, y: 2.5, w: 0.7, h: 0.7, fill: { color: GOLD } });
  s.addText(n, { x: x + 1.07, y: 2.5, w: 0.7, h: 0.7, fontFace: HEAD, fontSize: 24, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
  s.addText(t, { x: x + 0.2, y: 3.35, w: 2.45, h: 0.95, fontFace: BODY, fontSize: 14, bold: true, color: TEAL_DARK, align: "center", valign: "top", margin: 0 });
  if (i < 3) arrow(s, x + 2.85, 3.25, GOLD, 22);
});
strip(s, 5.7, [{ text: "Esconde FTP, formatos legados, tokens e paginação. ", options: { bold: true } }, { text: "“Você não precisa saber o que é um arquivo DBC.”", options: { italic: true, color: GOLD_BR } }], { fs: 14.5 });
footer(s, 7);
s.addNotes("Experiência (1:30). Quatro passos. O ponto central: toda a complexidade técnica fica escondida. Se tiver um screenshot da UI, mostre aqui.");

/* 8 · TRANSIÇÃO: DATALAKE */
s = S(); s.background = { color: TEAL_DARK };
darkSun(s, "br");
s.addText("O DESTINO DOS DADOS", { x: 0.95, y: 2.0, w: 9, h: 0.4, fontFace: BODY, fontSize: 13, bold: true, color: GOLD, charSpacing: 2.5, margin: 0 });
s.addText("A função final não é o arquivo no seu desktop.", { x: 0.95, y: 2.55, w: 10.5, h: 0.8, fontFace: BODY, fontSize: 24, color: WHITE, margin: 0 });
s.addText("É abastecer o datalake.", { x: 0.95, y: 3.5, w: 10.5, h: 1.0, fontFace: HEAD, fontSize: 40, bold: true, color: GOLD_BR, margin: 0 });
s.addNotes("Transição (0:45). Vire a chave: a entrega não é um download avulso, é alimentar continuamente o datalake do projeto.");

/* 9 · MEDALHÃO */
s = S(); s.background = { color: CREAM };
contentHead(s, "Arquitetura", "Medalhão: bronze → prata → ouro");
const tiers = [
  ["OURO", "Agregado, pronto para análise, ML e dashboards.", OURO, 2.05, INK],
  ["PRATA", "Limpo, padronizado e integrado entre fontes.", SILVER, 3.35, INK],
  ["BRONZE", "Dado bruto, exatamente como veio da fonte.", BRONZE, 4.65, WHITE],
];
tiers.forEach(([t, d, c, y, tc]) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.9, y, w: 8.3, h: 1.12, fill: { color: c }, rectRadius: 0.08, shadow: sh({ blur: 6, offset: 2, opacity: 0.14 }) });
  s.addText(t, { x: 1.2, y, w: 2.0, h: 1.12, fontFace: HEAD, fontSize: 22, bold: true, color: tc, valign: "middle", margin: 0 });
  s.addText(d, { x: 3.2, y, w: 5.8, h: 1.12, fontFace: BODY, fontSize: 13.5, color: tc, valign: "middle", margin: 0 });
});
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 9.55, y: 4.65, w: 3.18, h: 1.12, fill: { color: TEAL_DARK }, line: { color: GOLD, width: 1.5 }, rectRadius: 0.08 });
s.addText([{ text: "A coleta do Guaraci\n", options: { color: WHITE, fontSize: 12.5 } }, { text: "entra aqui", options: { bold: true, color: GOLD_BR, fontSize: 15 } }], { x: 9.7, y: 4.65, w: 2.9, h: 1.12, fontFace: BODY, valign: "middle", align: "center", margin: 0 });
arrow(s, 9.2, 4.9, TEAL, 24);
strip(s, 6.15, [{ text: "Garantimos um bronze confiável e atualizado. Prata e ouro são construídos sobre essa base.", options: {} }], { fs: 14, h: 0.78, fill: TEAL });
footer(s, 9);
s.addNotes("Medalhão (2:00). Padrão clássico de datalake. Bronze é a fundação (por isso na base): dado bruto. Nós entregamos o bronze; o time do datalake constrói prata e ouro em cima.");

/* 10 · AUTOMAÇÃO / ORQUESTRADOR */
s = S(); s.background = { color: CREAM };
contentHead(s, "Automação", "A automação da coleta");
s.addText("Como a coleta se mantém atualizada sem baixar tudo de novo:", { x: 0.6, y: 1.8, w: 12, h: 0.45, fontFace: BODY, fontSize: 14, italic: true, color: MUTED, margin: 0 });
const fb = [
  ["Orquestrador", "Roda de forma agendada.", { border: GOLD, bw: 1.75 }],
  ["Discovery", "Lê a volumetria sem baixar nada (preflight).", {}],
  ["Compara", "Volumetria atual × a da última coleta.", {}],
  ["Coleta o delta", "Só o que é novo ou mudou de tamanho.", {}],
  ["Bronze", "Dado bruto + manifesto.", { fill: BRONZE, titleColor: WHITE, descColor: "F3E6D6" }],
];
let fx = 0.6; const fbw = 2.1, gap = 0.41;
fb.forEach(([t, d, o], i) => {
  flowBox(s, fx, 2.45, fbw, 1.95, t, d, Object.assign({ titleSize: 14 }, o));
  if (i < fb.length - 1) arrow(s, fx + fbw + 0.02, 3.22, GOLD, 19);
  fx += fbw + gap;
});
const badges = [["Idempotente", "não rebaixa o que já existe", 0.6], ["Rastreável", "tudo registrado no manifesto", 4.65], ["Econômico", "transfere apenas o delta", 8.7]];
badges.forEach(([t, d, x]) => {
  card(s, x, 4.7, 3.78, 0.85, { shadow: { blur: 5, offset: 1, opacity: 0.1 } });
  s.addText([{ text: t + "  ", options: { bold: true, color: TEAL } }, { text: d, options: { color: MUTED } }], { x: x + 0.2, y: 4.7, w: 3.4, h: 0.85, fontFace: BODY, fontSize: 12, valign: "middle", margin: 0 });
});
s.addText([{ text: "“Bater volumetria” ", options: { bold: true, color: INK } }, { text: "= comparar contagem e tamanho dos arquivos para detectar atualização sem transferir os dados.", options: { color: MUTED } }], { x: 0.6, y: 5.75, w: 12.1, h: 0.55, fontFace: BODY, fontSize: 12.5, italic: true, margin: 0, valign: "middle" });
footer(s, 10);
s.addNotes("Automação (2:30) — coração da minha contribuição. O orquestrador agendado usa o discovery (que já existe) para medir volumetria sem baixar nada, compara com o baseline e só baixa o delta, que cai no bronze. Idempotente, rastreável, econômico. Explique bem o termo 'bater volumetria'.");

/* 11 · POR QUE AJUDA */
s = S(); s.background = { color: CREAM };
contentHead(s, "Impacto", "Por que isso ajuda o pesquisador");
const why = [
  ["Tira o fardo técnico", "Sem FTP, sem scripts, sem parsing de formatos legados.", 0.6],
  ["Dado atualizado e rastreável", "Sabe-se de onde veio e quando — com manifesto.", 4.65],
  ["Foco na ciência", "Energia na pergunta de pesquisa, não no encanamento.", 8.7],
];
why.forEach(([t, d, x]) => {
  card(s, x, 2.0, 3.78, 2.7);
  s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 2.28, w: 0.46, h: 0.46, fill: { color: GOLD } });
  s.addText(t, { x: x + 0.3, y: 2.95, w: 3.2, h: 0.85, fontFace: BODY, fontSize: 16, bold: true, color: TEAL_DARK, margin: 0, valign: "top" });
  s.addText(d, { x: x + 0.3, y: 3.75, w: 3.25, h: 0.85, fontFace: BODY, fontSize: 13, color: MUTED, margin: 0, valign: "top" });
});
strip(s, 5.7, [{ text: "É a missão do AutoAI-Pandemics na prática: democratizar o acesso aos dados.", options: { bold: true } }], { fs: 14.5, fill: TEAL });
footer(s, 11);
s.addNotes("Impacto (1:00). Amarre de volta à missão do projeto-mãe: democratizar o acesso. Esse é o sentido de tudo.");

/* 12 · IDEIAS DE PROBLEMAS */
s = S(); s.background = { color: CREAM };
contentHead(s, "Aplicações", "Ideias de problemas práticos");
const topRow = [
  ["Clima × arboviroses", "Chuva e temperatura (NASA) × dengue e chikungunya (DATASUS), por município.", 0.6],
  ["Queimadas × respiratório", "Focos de fogo (NASA FIRMS) × internações respiratórias.", 4.65],
  ["Saneamento × doença hídrica", "Indicadores de saneamento × notificações gastrointestinais.", 8.7],
];
topRow.forEach(([t, d, x]) => {
  card(s, x, 1.95, 3.78, 1.95);
  s.addText(t, { x: x + 0.25, y: 2.12, w: 3.3, h: 0.7, fontFace: BODY, fontSize: 14.5, bold: true, color: TEAL_DARK, margin: 0, valign: "top" });
  s.addText(d, { x: x + 0.25, y: 2.82, w: 3.3, h: 0.95, fontFace: BODY, fontSize: 12, color: MUTED, margin: 0, valign: "top" });
});
const botRow = [
  ["Vacinação × mortalidade", "Cobertura de campanhas (PNI) × óbitos (SIM).", 0.6],
  ["Séries históricas longas", "Microdados desde os anos 1990 para treinar modelos de ML.", 6.67],
];
botRow.forEach(([t, d, x]) => {
  card(s, x, 4.05, 6.06, 1.5);
  s.addText(t, { x: x + 0.25, y: 4.22, w: 5.6, h: 0.5, fontFace: BODY, fontSize: 14.5, bold: true, color: TEAL_DARK, margin: 0, valign: "top" });
  s.addText(d, { x: x + 0.25, y: 4.72, w: 5.6, h: 0.7, fontFace: BODY, fontSize: 12, color: MUTED, margin: 0, valign: "top" });
});
s.addText("Sementes de projeto para a disciplina — saúde e ambiente se cruzam no Guaraci.", { x: 0.6, y: 5.75, w: 12.1, h: 0.4, fontFace: BODY, fontSize: 12.5, italic: true, color: MUTED, align: "center", margin: 0 });
footer(s, 12);
s.addNotes("Aplicações (1:30). Provavelmente o que o André quer: ideias de projeto. O grande diferencial é cruzar saúde (DATASUS) com ambiente (NASA) — modelagem espaço-temporal de doenças.");

/* 13 · STACK & ESTADO */
s = S(); s.background = { color: CREAM };
contentHead(s, "Tecnologia", "Stack & estado");
const stats = [["~80", "fontes integradas", 0.6], ["~480", "testes automatizados verdes", 4.65], ["v0.5.2", "estágio alpha", 8.7]];
stats.forEach(([n, l, x]) => {
  card(s, x, 1.95, 3.78, 2.0);
  s.addText(n, { x: x + 0.25, y: 2.2, w: 3.3, h: 0.95, fontFace: HEAD, fontSize: 40, bold: true, color: GOLD, margin: 0, valign: "middle" });
  s.addText(l, { x: x + 0.27, y: 3.2, w: 3.3, h: 0.6, fontFace: BODY, fontSize: 13.5, color: MUTED, margin: 0, valign: "top" });
});
const tech = ["Python", "FastAPI", "Polars", "Docker"];
tech.forEach((t, i) => {
  const x = 0.6 + i * 3.06;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 4.25, w: 2.85, h: 0.7, fill: { color: TEAL_DARK }, rectRadius: 0.35 });
  s.addText(t, { x, y: 4.25, w: 2.85, h: 0.7, fontFace: BODY, fontSize: 15, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
});
strip(s, 5.7, [{ text: "Foco atual: robustez da extração para garantir um bronze confiável.", options: { bold: true } }], { fs: 14.5, fill: TEAL });
footer(s, 13);
s.addNotes("Stack & estado (1:00). Números de credibilidade. Docker-first por reprodutibilidade. É alpha: estável no que importa (coleta), evoluindo no resto.");

/* 14 · QUADRO COMPLETO */
s = S(); s.background = { color: TEAL_DARK };
darkSun(s, "tr");
s.addText("O QUADRO COMPLETO", { x: 0.9, y: 0.7, w: 9, h: 0.4, fontFace: BODY, fontSize: 13, bold: true, color: GOLD, charSpacing: 2.5, margin: 0 });
s.addText("Da fonte pública à pesquisa", { x: 0.88, y: 1.12, w: 11, h: 0.8, fontFace: HEAD, fontSize: 30, bold: true, color: WHITE, margin: 0 });
const pipe = [
  ["Fontes públicas", false], ["Guaraci · coletor\n(automatizado)", true], ["Bronze", true], ["Prata / Ouro", false], ["Pesquisa & ML", false],
];
let px = 0.6; const pw = 2.2, pgap = 0.28;
pipe.forEach(([t, hot], i) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: px, y: 3.25, w: pw, h: 1.5, fill: { color: hot ? GOLD : TEAL }, line: { color: hot ? GOLD_BR : TEAL_LT, width: 1.25 }, rectRadius: 0.09, shadow: sh({ color: "061F24", opacity: 0.25 }) });
  s.addText(t, { x: px + 0.1, y: 3.25, w: pw - 0.2, h: 1.5, fontFace: BODY, fontSize: 13.5, bold: true, color: hot ? INK : WHITE, align: "center", valign: "middle", margin: 0 });
  if (i < pipe.length - 1) arrow(s, px + pw + 0.0, 3.8, GOLD_BR, 20);
  px += pw + pgap;
});
s.addText("As duas etapas em dourado são a contribuição do Guaraci.", { x: 0.6, y: 5.25, w: 12, h: 0.4, fontFace: BODY, fontSize: 13, italic: true, color: TEAL_LT, align: "center", margin: 0 });
footer(s, 14, true);
s.addNotes("Quadro completo (0:45). Recapitule o pipeline inteiro. As caixas douradas (coletor + bronze) são a minha parte; o resto é o ecossistema do projeto.");

/* 15 · ENCERRAMENTO */
s = S(); s.background = { color: TEAL_DARK };
darkSun(s, "br");
s.addText("Obrigado", { x: 0.95, y: 1.85, w: 10, h: 1.1, fontFace: HEAD, fontSize: 54, bold: true, color: GOLD_BR, margin: 0 });
s.addText("Perguntas?", { x: 0.98, y: 3.05, w: 10, h: 0.7, fontFace: BODY, fontSize: 22, color: WHITE, margin: 0 });
s.addShape(pres.shapes.LINE, { x: 0.98, y: 4.0, w: 4.5, h: 0, line: { color: GOLD, width: 1.5 } });
s.addText([
  { text: "Luis Felipe Vogel Lopes\n", options: { bold: true, color: WHITE, fontSize: 16 } },
  { text: "nUSP 13730051   ·   vogel@usp.br", options: { color: TEAL_LT, fontSize: 14 } },
], { x: 0.98, y: 4.2, w: 11, h: 0.9, fontFace: BODY, margin: 0, lineSpacingMultiple: 1.15 });
s.addText([
  { text: "github.com/autoaihub/guaraci", options: { color: GOLD_BR } },
  { text: "      ·      ", options: { color: TEAL_LT } },
  { text: "autoaipandemics.icmc.usp.br", options: { color: GOLD_BR } },
], { x: 0.98, y: 5.5, w: 11.5, h: 0.4, fontFace: BODY, fontSize: 13, margin: 0 });
s.addNotes("Encerramento (0:30 + Q&A). Deixe o contato e os links visíveis durante as perguntas.");

/* ---- write ---- */
pres.writeFile({ fileName: "Guaraci-AutoAI-Pandemics.pptx" })
  .then(f => console.log("OK:", f))
  .catch(e => { console.error("ERR:", e); process.exit(1); });
