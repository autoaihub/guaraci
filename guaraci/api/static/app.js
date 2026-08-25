/* ═══════════════════════════════════════════════════════════════
   Guaraci UI — app shell (Coletas / Nova coleta / Fontes)
   Vanilla JS, sem build step. Identidade "amanhecer de dados".
   ═══════════════════════════════════════════════════════════════ */
"use strict";

const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const JOBS_LIMIT = 40;

let currentView = "jobs";
let sourcesList = [];
let sourcesBySource = {};
const schemasBySource = {};
let currentSource = null;
let currentSchema = null;
let lastJobs = [];
let jobsFilter = "all";
let jobsQuery = "";
let selectedJobId = null;
let selectedJobStatus = null;
let refreshInFlight = false;

/* ═══ i18n pt/en ═══ */
const I18N = {
  pt: {
    brand_sub: "dados públicos de saúde",
    nav_operation: "Operação",
    nav_jobs: "Coletas",
    nav_new: "Nova coleta",
    nav_sources: "Fontes",
    nav_help: "Ajuda",
    nav_docs: "Documentação",
    theme_toggle: "Alternar tema",
    api_connecting: "API: conectando…",
    api_online: "API conectada",
    api_offline: "API offline",
    kpi_running: "Em execução",
    kpi_done: "Concluídas",
    kpi_failed: "Falhas",
    kpi_volume: "Volume transferido",
    kpi_window: "entre as últimas 40 coletas",
    kpi_queued_note: "{n} na fila",
    kpi_files_note: "{n} arquivos",
    jobs_search_ph: "Buscar por fonte ou ID…",
    src_search_ph: "Buscar fonte… (ex.: dengue, sih, população)",
    flt_all: "Todas",
    flt_active: "Ativas",
    flt_done: "Concluídas",
    flt_failed: "Falhas",
    refresh_list: "Atualizar",
    jobs_caption: "Lista de coletas com status, progresso e ações",
    th_job: "ID",
    th_source: "Fonte",
    th_status: "Status",
    th_progress: "Progresso",
    th_files: "Arquivos",
    th_attempt: "Tent.",
    jobs_empty: "Nenhuma coleta ainda. Crie a primeira em “Nova coleta”.",
    jobs_empty_filter: "Nenhuma coleta corresponde ao filtro.",
    step_source: "Fonte",
    step_filters: "Filtros e revisão",
    sources_hint: "Clique numa fonte para iniciar uma coleta com ela.",
    catalog_empty: "Nenhuma fonte encontrada com esse termo.",
    fam_datasus: "DATASUS — FTP oficial",
    fam_opendatasus: "OpenDataSUS — catálogo aberto",
    fam_ibge: "IBGE",
    fam_nasa: "NASA — clima e ambiente",
    fam_govbr: "Saneamento — gov.br",
    fam_other: "Outras fontes",
    advanced: "Filtros avançados",
    summary_title: "Resumo da coleta",
    sum_source: "Fonte",
    sum_mode: "Modo",
    sum_none: "Nenhum filtro definido — a coleta usa os padrões da fonte.",
    btn_estimate: "Estimar volume",
    estimating: "Consultando a fonte…",
    estimate_result: "<strong>{docs} arquivos{size}</strong> estimados na fonte para esses filtros.",
    estimate_size: " · ~{size}",
    estimate_fail: "Não foi possível estimar: {err}",
    btn_submit: "Iniciar coleta",
    btn_change_source: "← Trocar fonte",
    btn_cancel: "Cancelar",
    btn_retry: "Repetir",
    open_folder: "Abrir pasta",
    copy_path: "Copiar caminho",
    lbl_source: "Fonte",
    lbl_created: "Criada",
    lbl_params: "Filtros",
    lbl_current_file: "Arquivo atual",
    lbl_output_folder: "Destino",
    lbl_attempt: "tentativa",
    log_title: "Log da execução",
    no_logs: "Sem logs para exibir ainda.",
    no_params_set: "padrões da fonte",
    exported_title: "Arquivos exportados ({n})",
    st_queued: "Na fila",
    st_running: "Em execução",
    st_cancel_requested: "Cancelando…",
    st_canceled: "Cancelada",
    st_completed: "Concluída",
    st_failed: "Falhou",
    required: "obrigatório",
    activate: "Ativar",
    select_all: "Selecionar tudo",
    clear_sel: "Limpar",
    no_filter: "(sem filtro)",
    ms_all: "Todos",
    ms_selected_n: "{n} selecionados",
    ms_search_ph: "Buscar opção…",
    ms_no_match: "Nenhuma opção encontrada.",
    no_params: "Sem parâmetros configuráveis para esta fonte.",
    job_created: "Coleta criada: ",
    cancel_requested_for: "Cancelamento solicitado para ",
    retry_created: "Nova tentativa criada: ",
    copy_ok: "Caminho copiado para a área de transferência.",
    copy_fail: "Não foi possível copiar o caminho.",
    copy_none: "Ainda não há pasta de saída para copiar.",
    open_fail: "Não foi possível abrir a pasta.",
    open_ok: "Pasta aberta.",
    open_manual: "Abra a pasta manualmente usando o caminho exibido.",
    fail_create: "Falha ao criar a coleta",
    fail_cancel: "Falha ao cancelar",
    fail_retry: "Falha ao repetir",
    fail_sources: "Falha ao carregar as fontes",
    boot_error: "Erro ao iniciar a interface: ",
    today_at: "hoje às {t}",
    tip_output_dir: "Diretório principal de saída.\nPadrão: pasta Guaraci Downloads na Área de Trabalho.",
    tip_output_format: "Formato de exportação pós-download.\nExemplo: csv",
    tip_keep_raw: "Quando ativado, também salva o JSONL bruto da API.\nPadrão: desativado",
    tip_start_year: "Ano inicial para buscar arquivos.\nExemplo: 2023",
    tip_end_year: "Ano final para buscar arquivos.\nExemplo: 2025",
    tip_uf: "Filtra por unidade federativa.\nExemplo: SP",
    tip_select_multi: "Selecione um ou mais valores.\nExemplo: ",
    tip_select_one: "Selecione um valor válido.\nExemplo: ",
    tip_integer: "Valor numérico.\nExemplo: ",
    tip_boolean: "Ative para SIM; desative para NÃO.",
    tip_csv: "Lista separada por vírgulas.\nExemplo: valor1, valor2",
    tip_free: "Campo opcional de texto livre."
  },
  en: {
    brand_sub: "Brazilian public health data",
    nav_operation: "Operation",
    nav_jobs: "Downloads",
    nav_new: "New download",
    nav_sources: "Sources",
    nav_help: "Help",
    nav_docs: "Documentation",
    theme_toggle: "Toggle theme",
    api_connecting: "API: connecting…",
    api_online: "API connected",
    api_offline: "API offline",
    kpi_running: "Running",
    kpi_done: "Completed",
    kpi_failed: "Failed",
    kpi_volume: "Volume transferred",
    kpi_window: "within the last 40 downloads",
    kpi_queued_note: "{n} queued",
    kpi_files_note: "{n} files",
    jobs_search_ph: "Search by source or ID…",
    src_search_ph: "Search sources… (e.g. dengue, sih, population)",
    flt_all: "All",
    flt_active: "Active",
    flt_done: "Completed",
    flt_failed: "Failed",
    refresh_list: "Refresh",
    jobs_caption: "List of downloads with status, progress and actions",
    th_job: "ID",
    th_source: "Source",
    th_status: "Status",
    th_progress: "Progress",
    th_files: "Files",
    th_attempt: "Att.",
    jobs_empty: "No downloads yet. Create the first one in “New download”.",
    jobs_empty_filter: "No download matches the filter.",
    step_source: "Source",
    step_filters: "Filters & review",
    sources_hint: "Click a source to start a download with it.",
    catalog_empty: "No source matches that term.",
    fam_datasus: "DATASUS — official FTP",
    fam_opendatasus: "OpenDataSUS — open catalog",
    fam_ibge: "IBGE",
    fam_nasa: "NASA — climate & environment",
    fam_govbr: "Sanitation — gov.br",
    fam_other: "Other sources",
    advanced: "Advanced filters",
    summary_title: "Download summary",
    sum_source: "Source",
    sum_mode: "Mode",
    sum_none: "No filter set — the download uses the source defaults.",
    btn_estimate: "Estimate volume",
    estimating: "Querying the source…",
    estimate_result: "<strong>{docs} files{size}</strong> estimated at the source for these filters.",
    estimate_size: " · ~{size}",
    estimate_fail: "Could not estimate: {err}",
    btn_submit: "Start download",
    btn_change_source: "← Change source",
    btn_cancel: "Cancel",
    btn_retry: "Retry",
    open_folder: "Open folder",
    copy_path: "Copy path",
    lbl_source: "Source",
    lbl_created: "Created",
    lbl_params: "Filters",
    lbl_current_file: "Current file",
    lbl_output_folder: "Destination",
    lbl_attempt: "attempt",
    log_title: "Execution log",
    no_logs: "No logs to display yet.",
    no_params_set: "source defaults",
    exported_title: "Exported files ({n})",
    st_queued: "Queued",
    st_running: "Running",
    st_cancel_requested: "Canceling…",
    st_canceled: "Canceled",
    st_completed: "Completed",
    st_failed: "Failed",
    required: "required",
    activate: "Enable",
    select_all: "Select all",
    clear_sel: "Clear",
    no_filter: "(no filter)",
    ms_all: "All",
    ms_selected_n: "{n} selected",
    ms_search_ph: "Search option…",
    ms_no_match: "No option found.",
    no_params: "No configurable parameters for this source.",
    job_created: "Download created: ",
    cancel_requested_for: "Cancellation requested for ",
    retry_created: "Retry created: ",
    copy_ok: "Path copied to clipboard.",
    copy_fail: "Could not copy the path.",
    copy_none: "There is no output folder to copy yet.",
    open_fail: "Could not open the folder.",
    open_ok: "Folder opened.",
    open_manual: "Open the folder manually using the displayed path.",
    fail_create: "Failed to create the download",
    fail_cancel: "Failed to cancel",
    fail_retry: "Failed to retry",
    fail_sources: "Failed to load sources",
    boot_error: "Error starting the interface: ",
    today_at: "today at {t}",
    tip_output_dir: "Main output directory.\nDefault: Guaraci Downloads folder on your Desktop.",
    tip_output_format: "Post-download export format.\nExample: csv",
    tip_keep_raw: "When enabled, also saves the raw API JSONL.\nDefault: off",
    tip_start_year: "First year to fetch files for.\nExample: 2023",
    tip_end_year: "Last year to fetch files for.\nExample: 2025",
    tip_uf: "Filters by state (UF).\nExample: SP",
    tip_select_multi: "Pick one or more values.\nExample: ",
    tip_select_one: "Pick a valid value.\nExample: ",
    tip_integer: "Numeric value.\nExample: ",
    tip_boolean: "Enable for YES; disable for NO.",
    tip_csv: "Comma-separated list.\nExample: value1, value2",
    tip_free: "Optional free-text field."
  }
};

let currentLang = (function () {
  try {
    const saved = localStorage.getItem("guaraci_lang");
    if (saved === "pt" || saved === "en") return saved;
  } catch (error) { /* localStorage indisponível */ }
  return "pt";
})();

function t(key) {
  const table = I18N[currentLang] || I18N.pt;
  if (Object.prototype.hasOwnProperty.call(table, key)) return table[key];
  if (Object.prototype.hasOwnProperty.call(I18N.pt, key)) return I18N.pt[key];
  return key;
}

function tf(key, vars) {
  let text = t(key);
  Object.entries(vars || {}).forEach(([name, value]) => {
    text = text.replaceAll("{" + name + "}", String(value));
  });
  return text;
}

function applyI18n() {
  document.documentElement.lang = currentLang === "en" ? "en" : "pt-BR";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  const langBtn = document.getElementById("lang-toggle");
  langBtn.textContent = currentLang === "pt" ? "EN" : "PT";
  langBtn.setAttribute(
    "aria-label",
    currentLang === "pt" ? "Switch to English" : "Mudar para português"
  );
  updateTopbarTitle();
}

function setLang(lang) {
  currentLang = lang === "en" ? "en" : "pt";
  try { localStorage.setItem("guaraci_lang", currentLang); } catch (error) { /* ignore */ }
  applyI18n();
  renderCatalogs();
  if (currentSchema) {
    renderDynamicFields(currentSchema);
    renderSummary();
  }
  renderJobs();
  renderKpis();
  if (selectedJobId) {
    const job = lastJobs.find((item) => item.job_id === selectedJobId);
    if (job) renderDrawer(job);
  }
}

/* ═══ tema ═══ */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
}
(function initTheme() {
  try {
    const saved = localStorage.getItem("guaraci_theme");
    if (saved === "light" || saved === "dark") applyTheme(saved);
  } catch (error) { /* ignore */ }
})();

/* ═══ helpers ═══ */
function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("`", "&#96;");
}

function splitCsv(rawValue) {
  return rawValue.split(",").map((item) => item.trim()).filter((item) => item.length > 0);
}

function isTerminalStatus(status) {
  return status === "completed" || status === "failed" || status === "canceled";
}

function formatSeconds(value) {
  if (value === null || value === undefined) return "--";
  const total = Math.max(0, Math.round(Number(value)));
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return String(min).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
}

function humanBytes(value) {
  if (value === null || value === undefined) return "--";
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "--";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = bytes;
  let idx = 0;
  while (amount >= 1024 && idx < units.length - 1) {
    amount /= 1024;
    idx += 1;
  }
  return amount.toFixed(idx === 0 ? 0 : 1) + " " + units[idx];
}

function pad2(value) { return String(value).padStart(2, "0"); }

function formatLogTimestamp(raw) {
  if (!raw) return "--";
  const text = String(raw);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) return text.slice(11);
  const parsed = new Date(text.includes("Z") || text.includes("+") ? text : text + "Z");
  if (Number.isNaN(parsed.getTime())) {
    return text.replace("T", " ").replace(/\.\d+/, "").replace("Z", "").slice(11, 19) || text;
  }
  return pad2(parsed.getHours()) + ":" + pad2(parsed.getMinutes()) + ":" + pad2(parsed.getSeconds());
}

function formatCreatedAt(raw) {
  if (!raw) return "--";
  const text = String(raw);
  const parsed = new Date(text.includes("Z") || text.includes("+") ? text : text + "Z");
  if (Number.isNaN(parsed.getTime())) return text;
  const now = new Date();
  const hhmm = pad2(parsed.getHours()) + ":" + pad2(parsed.getMinutes());
  if (parsed.toDateString() === now.toDateString()) return tf("today_at", { t: hhmm });
  return pad2(parsed.getDate()) + "/" + pad2(parsed.getMonth() + 1) + " " + hhmm;
}

function shortName(pathOrUrl) {
  if (!pathOrUrl) return "--";
  const text = String(pathOrUrl).trim();
  if (!text) return "--";
  const normalized = text.replaceAll("\\", "/");
  const idx = normalized.lastIndexOf("/");
  return idx >= 0 ? normalized.slice(idx + 1) || normalized : normalized;
}

function prettyLabel(name) {
  const raw = String(name || "");
  if (raw === "output_dir") return currentLang === "en" ? "Download directory" : "Diretório do download";
  if (raw === "keep_raw") return currentLang === "en" ? "Keep raw file" : "Manter arquivo bruto";
  return raw.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function paramsSummaryText(params) {
  const entries = Object.entries(params || {});
  if (entries.length === 0) return t("no_params_set");
  return entries
    .map(([key, value]) => prettyLabel(key) + ": " + (Array.isArray(value) ? value.join(", ") : String(value)))
    .join(" · ");
}

let toastTimer = null;
function toast(message, kind) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast show" + (kind === "ok" ? " t-ok" : kind === "fail" ? " t-fail" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3400);
}

function setApiStatus(ok) {
  const dot = document.getElementById("api-dot");
  const label = document.getElementById("api-label");
  dot.className = "api-dot " + (ok ? "is-on" : "is-off");
  label.textContent = ok ? t("api_online") : t("api_offline");
}

/* ═══ fundo animado — rede de dados ═══ */
(function initCanvas() {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas || REDUCED_MOTION) return;
  const ctx = canvas.getContext("2d");
  let W = 0;
  let H = 0;
  let pts = [];
  const DENSITY = 1 / 26000;
  function resize() {
    W = canvas.width = innerWidth * devicePixelRatio;
    H = canvas.height = innerHeight * devicePixelRatio;
    const n = Math.min(70, Math.floor(innerWidth * innerHeight * DENSITY));
    pts = Array.from({ length: n }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.14 * devicePixelRatio,
      vy: (Math.random() - 0.5) * 0.14 * devicePixelRatio,
      r: (Math.random() * 1.4 + 0.7) * devicePixelRatio,
      warm: Math.random() < 0.3
    }));
  }
  function tick() {
    ctx.clearRect(0, 0, W, H);
    const linkDist = 120 * devicePixelRatio;
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
      for (let j = i + 1; j < pts.length; j++) {
        const q = pts[j];
        const d = Math.hypot(p.x - q.x, p.y - q.y);
        if (d < linkDist) {
          ctx.strokeStyle = "rgba(20,184,166," + (0.12 * (1 - d / linkDist)).toFixed(3) + ")";
          ctx.lineWidth = devicePixelRatio * 0.7;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.stroke();
        }
      }
    }
    for (const p of pts) {
      ctx.fillStyle = p.warm ? "rgba(247,164,29,.6)" : "rgba(20,184,166,.5)";
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    requestAnimationFrame(tick);
  }
  resize();
  addEventListener("resize", resize);
  requestAnimationFrame(tick);
})();

/* ═══ navegação ═══ */
function updateTopbarTitle() {
  const key = currentView === "jobs" ? "nav_jobs" : currentView === "new" ? "nav_new" : "nav_sources";
  document.getElementById("topbar-title").textContent = t(key);
}

function playReveals(view) {
  const els = document.querySelectorAll("#view-" + view + " .reveal");
  els.forEach((el, i) => {
    el.classList.remove("in");
    setTimeout(() => el.classList.add("in"), REDUCED_MOTION ? 0 : 60 + i * 90);
  });
}

function go(view) {
  currentView = view;
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
  document.querySelectorAll(".nav-item[data-view]").forEach((b) => {
    if (b.dataset.view === view) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  updateTopbarTitle();
  document.getElementById("topbar-new").style.visibility = view === "new" ? "hidden" : "visible";
  closeDrawer();
  playReveals(view);
}

/* ═══ fontes / catálogo ═══ */
function familyOf(mode) {
  const lower = String(mode || "").toLowerCase();
  if (lower.includes("opendatasus")) return "opendatasus";
  if (lower.includes("datasus") || lower.includes("pysus")) return "datasus";
  if (lower.includes("ibge")) return "ibge";
  if (lower.includes("nasa")) return "nasa";
  if (lower.includes("gov.br") || lower.includes("crawl")) return "govbr";
  return "other";
}
const FAMILY_ORDER = ["datasus", "opendatasus", "ibge", "nasa", "govbr", "other"];

async function loadSources() {
  const response = await fetch("/sources");
  if (!response.ok) throw new Error(t("fail_sources"));
  sourcesList = (await response.json()).slice().sort((a, b) =>
    String(a.title || a.source).localeCompare(String(b.title || b.source))
  );
  sourcesBySource = {};
  sourcesList.forEach((item) => { sourcesBySource[item.source] = item; });
  renderCatalogs();
}

function renderCatalogInto(el, query, clickable) {
  el.innerHTML = "";
  const q = String(query || "").trim().toLowerCase();
  const filtered = sourcesList.filter((item) =>
    !q ||
    String(item.title).toLowerCase().includes(q) ||
    String(item.source).toLowerCase().includes(q) ||
    String(item.mode).toLowerCase().includes(q)
  );
  if (filtered.length === 0) {
    el.innerHTML = "<div class='catalog-empty'>" + escapeHtml(t("catalog_empty")) + "</div>";
    return;
  }
  const groups = {};
  filtered.forEach((item) => {
    const fam = familyOf(item.mode);
    (groups[fam] = groups[fam] || []).push(item);
  });
  FAMILY_ORDER.forEach((fam) => {
    const items = groups[fam];
    if (!items || items.length === 0) return;
    const group = document.createElement("div");
    group.className = "family-group";
    const heading = document.createElement("h3");
    heading.textContent = t("fam_" + fam) + " · " + items.length;
    group.appendChild(heading);
    const grid = document.createElement("div");
    grid.className = "catalog";
    items.forEach((item) => {
      const card = document.createElement("button");
      card.className = "src-card";
      card.type = "button";
      if (clickable && currentSource === item.source) card.setAttribute("aria-pressed", "true");
      card.innerHTML =
        "<span class='mode'>" + escapeHtml(item.mode) + "</span>" +
        "<strong>" + escapeHtml(item.title) + "</strong>" +
        "<p>" + escapeHtml(item.source) + "</p>";
      card.addEventListener("click", () => selectSource(item.source));
      grid.appendChild(card);
    });
    group.appendChild(grid);
    el.appendChild(group);
  });
}

function renderCatalogs() {
  renderCatalogInto(
    document.getElementById("nc-catalog"),
    document.getElementById("nc-search").value,
    true
  );
  renderCatalogInto(
    document.getElementById("sources-catalog"),
    document.getElementById("sources-search").value,
    false
  );
}

/* ═══ schema / formulário dinâmico ═══ */
async function loadSourceSchema(source) {
  if (schemasBySource[source]) return schemasBySource[source];
  const response = await fetch("/sources/" + encodeURIComponent(source) + "/schema");
  if (!response.ok) return null;
  const schema = await response.json();
  schemasBySource[source] = schema;
  return schema;
}

async function selectSource(source) {
  currentSource = source;
  const schema = await loadSourceSchema(source);
  currentSchema = schema;
  if (currentView !== "new") go("new");
  const info = sourcesBySource[source] || { title: source, mode: "--" };
  document.getElementById("form-title").textContent = info.title;
  document.getElementById("form-sub").textContent = source + " · " + info.mode;
  renderDynamicFields(schema);
  renderSummary();
  document.getElementById("estimate-box").hidden = true;
  document.getElementById("btn-estimate").hidden = !info.supports_discovery;
  document.getElementById("nc-step1").hidden = true;
  document.getElementById("nc-step2").hidden = false;
  document.getElementById("stp-1").className = "st is-done";
  document.getElementById("stp-2").className = "st is-active";
  window.scrollTo({ top: 0 });
}

function backToCatalog() {
  document.getElementById("nc-step1").hidden = false;
  document.getElementById("nc-step2").hidden = true;
  document.getElementById("stp-1").className = "st is-active";
  document.getElementById("stp-2").className = "st";
  renderCatalogs();
}

function orderSchemaParams(params) {
  const priority = { output_dir: 10, output_format: 20, start_year: 30, end_year: 40 };
  return [...params].sort((a, b) => {
    const pa = Object.prototype.hasOwnProperty.call(priority, a.name) ? priority[a.name] : 100;
    const pb = Object.prototype.hasOwnProperty.call(priority, b.name) ? priority[b.name] : 100;
    if (pa !== pb) return pa - pb;
    return String(a.name).localeCompare(String(b.name));
  });
}

function fieldHintText(spec) {
  const name = String(spec.name || "");
  const allowed = Array.isArray(spec.allowed_values) ? spec.allowed_values : [];
  if (name === "output_dir") return t("tip_output_dir");
  if (name === "output_format") return t("tip_output_format");
  if (name === "keep_raw") return t("tip_keep_raw");
  if (name === "start_year") return t("tip_start_year");
  if (name === "end_year") return t("tip_end_year");
  if (name === "uf") return t("tip_uf");
  if (allowed.length > 0) {
    if (spec.type === "string_list") return t("tip_select_multi") + allowed.slice(0, 3).join(", ");
    return t("tip_select_one") + String(allowed[0]);
  }
  if (spec.type === "integer") return t("tip_integer") + String(spec.default ?? spec.minimum ?? 2024);
  if (spec.type === "boolean") return t("tip_boolean");
  if (spec.type === "string_list") return t("tip_csv");
  return t("tip_free");
}

function isAdvancedField(spec) {
  const name = String(spec.name || "");
  if (name === "output_dir" || name === "output_format") return false;
  const schema = currentSchema || {};
  const source = String(schema.source || "");
  const mode = String(schema.mode || "").toLowerCase();
  if (mode.includes("opendatasus")) {
    if (name === "start_date" || name === "end_date" || name === "keep_raw") return true;
    if (source === "zikavirus" && name === "uf") return true;
  }
  const technical = new Set([
    "api_base_url", "batch_size", "max_pages", "resource_id",
    "results_url", "timeout", "overwrite", "extract_archives"
  ]);
  if (technical.has(name)) return true;
  if (spec.phase === "basico" || spec.phase === "coleta" || spec.phase === "refinamento") return false;
  return true;
}

/* ═══ dropdown de multiseleção (string_list) ═══ */
function closeAllMultiSelectDropdowns(except) {
  document.querySelectorAll(".ms-dropdown.is-open").forEach((node) => {
    if (node === except) return;
    node.classList.remove("is-open");
    const trigger = node.querySelector(".ms-trigger");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  });
}

function multiSelectSummaryText(values, allowedCount) {
  if (values.length === 0) return t("no_filter");
  if (values.length === allowedCount) return t("ms_all");
  if (values.length <= 3) return values.join(", ");
  return tf("ms_selected_n", { n: values.length });
}

function createMultiSelectDropdown(spec) {
  const wrap = document.createElement("div");
  wrap.className = "ms-dropdown";

  // <select multiple> oculto: continua sendo a fonte de verdade lida por
  // buildPayload()/renderSummary() (dataset.role = "value"); os checkboxes
  // visíveis só espelham o estado dele.
  const select = document.createElement("select");
  select.dataset.role = "value";
  select.multiple = true;
  select.className = "sr-only";
  select.setAttribute("aria-hidden", "true");
  select.tabIndex = -1;
  spec.allowed_values.forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    select.appendChild(option);
  });
  const defaults = Array.isArray(spec.default) ? spec.default.map(String) : [];
  Array.from(select.options).forEach((option) => {
    option.selected = defaults.includes(option.value);
  });

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "ms-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  const summarySpan = document.createElement("span");
  summarySpan.className = "ms-summary";
  trigger.appendChild(summarySpan);
  const chevron = document.createElement("span");
  chevron.className = "ms-chevron";
  chevron.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 6l4 4 4-4"/></svg>';
  trigger.appendChild(chevron);

  const panel = document.createElement("div");
  panel.className = "ms-panel";

  const actions = document.createElement("div");
  actions.className = "ms-panel-actions";
  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "mini-btn";
  allBtn.textContent = t("select_all");
  const clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "mini-btn";
  clearBtn.textContent = t("clear_sel");
  actions.appendChild(allBtn);
  actions.appendChild(clearBtn);
  panel.appendChild(actions);

  let searchInput = null;
  const showSearch = spec.allowed_values.length > 8;
  if (showSearch) {
    const searchWrap = document.createElement("div");
    searchWrap.className = "ms-search";
    searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = t("ms_search_ph");
    searchInput.setAttribute("aria-label", t("ms_search_ph"));
    searchWrap.appendChild(searchInput);
    panel.appendChild(searchWrap);
  }

  const optionsList = document.createElement("div");
  optionsList.className = "ms-options";
  optionsList.setAttribute("role", "listbox");
  optionsList.setAttribute("aria-multiselectable", "true");

  const checkboxes = [];
  spec.allowed_values.forEach((value) => {
    const strValue = String(value);
    const label = document.createElement("label");
    label.className = "ms-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = strValue;
    checkbox.checked = defaults.includes(strValue);
    checkbox.addEventListener("change", () => {
      const option = Array.from(select.options).find((opt) => opt.value === strValue);
      if (option) option.selected = checkbox.checked;
      updateSummary();
      renderSummary();
    });
    label.appendChild(checkbox);
    label.append(" " + strValue);
    optionsList.appendChild(label);
    checkboxes.push({ value: strValue, node: label, checkbox });
  });

  const emptyMsg = document.createElement("div");
  emptyMsg.className = "ms-empty";
  emptyMsg.hidden = true;
  emptyMsg.textContent = t("ms_no_match");
  optionsList.appendChild(emptyMsg);
  panel.appendChild(optionsList);

  function updateSummary() {
    const values = Array.from(select.selectedOptions).map((opt) => opt.value);
    summarySpan.textContent = multiSelectSummaryText(values, spec.allowed_values.length);
  }

  allBtn.addEventListener("click", () => {
    checkboxes.forEach(({ node, checkbox }) => {
      if (node.classList.contains("is-hidden")) return;
      checkbox.checked = true;
      const option = Array.from(select.options).find((opt) => opt.value === checkbox.value);
      if (option) option.selected = true;
    });
    updateSummary();
    renderSummary();
  });
  clearBtn.addEventListener("click", () => {
    checkboxes.forEach(({ checkbox }) => { checkbox.checked = false; });
    Array.from(select.options).forEach((option) => { option.selected = false; });
    updateSummary();
    renderSummary();
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const query = searchInput.value.trim().toLowerCase();
      checkboxes.forEach(({ value, node }) => {
        node.classList.toggle("is-hidden", query.length > 0 && !value.toLowerCase().includes(query));
      });
      const anyVisible = checkboxes.some(({ node }) => !node.classList.contains("is-hidden"));
      emptyMsg.hidden = anyVisible;
    });
  }

  function openPanel() {
    closeAllMultiSelectDropdowns(wrap);
    wrap.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    if (searchInput) searchInput.focus();
  }
  function closePanel() {
    wrap.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
  }
  trigger.addEventListener("click", () => {
    if (wrap.classList.contains("is-open")) closePanel();
    else openPanel();
  });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePanel();
      trigger.focus();
    }
    if ((event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") && !wrap.classList.contains("is-open")) {
      event.preventDefault();
      openPanel();
    }
  });

  select.addEventListener("change", () => {
    // mantém os checkboxes em sincronia caso o select seja alterado
    // programaticamente (ex.: defaults aplicados após troca de idioma).
    Array.from(select.options).forEach((option) => {
      const entry = checkboxes.find((item) => item.value === option.value);
      if (entry) entry.checkbox.checked = option.selected;
    });
    updateSummary();
  });

  updateSummary();

  wrap.appendChild(select);
  wrap.appendChild(trigger);
  wrap.appendChild(panel);
  return wrap;
}

function createFieldCard(spec) {
  const field = document.createElement("div");
  const isWide = spec.type === "string_list" || spec.name === "results_url" || spec.name === "output_dir";
  field.className = "field" + (isWide ? " is-wide" : "");
  field.dataset.paramName = spec.name;
  field.dataset.paramType = spec.type;

  const label = document.createElement("span");
  label.className = "field-label";
  const labelText = document.createElement("span");
  labelText.textContent = prettyLabel(spec.name);
  label.appendChild(labelText);
  const hint = document.createElement("span");
  hint.className = "hint-icon";
  hint.textContent = "?";
  hint.tabIndex = 0;
  hint.setAttribute("role", "button");
  hint.setAttribute("data-tooltip", fieldHintText(spec));
  hint.setAttribute("aria-label", fieldHintText(spec).replaceAll("\n", " | "));
  label.appendChild(hint);
  if (spec.required) {
    const required = document.createElement("span");
    required.className = "req";
    required.textContent = t("required");
    label.appendChild(required);
  }
  field.appendChild(label);

  if (spec.description) {
    const help = document.createElement("span");
    help.className = "help";
    help.textContent = spec.description;
    field.appendChild(help);
  }

  if (spec.type === "boolean") {
    const wrap = document.createElement("label");
    wrap.className = "check-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.role = "value";
    input.checked = Boolean(spec.default);
    input.addEventListener("change", renderSummary);
    wrap.appendChild(input);
    wrap.append(" " + t("activate"));
    field.appendChild(wrap);
    return field;
  }

  if (spec.type === "integer") {
    const input = document.createElement("input");
    input.type = "number";
    input.step = "1";
    input.dataset.role = "value";
    if (spec.minimum !== null && spec.minimum !== undefined) input.min = String(spec.minimum);
    if (spec.maximum !== null && spec.maximum !== undefined) input.max = String(spec.maximum);
    if (spec.default !== null && spec.default !== undefined) input.value = String(spec.default);
    input.addEventListener("input", renderSummary);
    field.appendChild(input);
    return field;
  }

  if (spec.type === "string" && Array.isArray(spec.allowed_values) && spec.allowed_values.length > 0) {
    const select = document.createElement("select");
    select.dataset.role = "value";
    if (!spec.required) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = t("no_filter");
      select.appendChild(empty);
    }
    spec.allowed_values.forEach((value) => {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = String(value);
      select.appendChild(option);
    });
    if (spec.default !== null && spec.default !== undefined) select.value = String(spec.default);
    select.addEventListener("change", renderSummary);
    field.appendChild(select);
    return field;
  }

  if (spec.type === "string_list" && Array.isArray(spec.allowed_values) && spec.allowed_values.length > 0) {
    field.appendChild(createMultiSelectDropdown(spec));
    return field;
  }

  const input = document.createElement("input");
  input.dataset.role = "value";
  if (spec.type === "string_list") {
    const defaultCsv = Array.isArray(spec.default) ? spec.default.join(", ") : "";
    input.placeholder = defaultCsv || "valor1, valor2";
    input.value = defaultCsv;
  } else {
    if (spec.default !== null && spec.default !== undefined) {
      input.placeholder = String(spec.default);
      input.value = String(spec.default);
    }
  }
  input.addEventListener("input", renderSummary);
  field.appendChild(input);
  return field;
}

function renderDynamicFields(schema) {
  const basic = document.getElementById("dynamic-fields-basic");
  const advanced = document.getElementById("dynamic-fields-advanced");
  basic.innerHTML = "";
  advanced.innerHTML = "";
  const disclosure = document.getElementById("adv");
  disclosure.hidden = true;
  disclosure.classList.remove("open");

  if (!schema || !Array.isArray(schema.params) || schema.params.length === 0) {
    basic.innerHTML = "<div class='field is-wide'><span class='help'>" + escapeHtml(t("no_params")) + "</span></div>";
    return;
  }

  const orderedSpecs = orderSchemaParams(schema.params);
  let advancedCount = 0;
  orderedSpecs.forEach((spec) => {
    const card = createFieldCard(spec);
    if (isAdvancedField(spec)) {
      advanced.appendChild(card);
      advancedCount += 1;
    } else {
      basic.appendChild(card);
    }
  });
  if (advancedCount > 0) {
    disclosure.hidden = false;
    document.getElementById("adv-count").textContent = String(advancedCount);
  }
}

function buildPayload() {
  const payload = { source: currentSource, params: {} };
  const schema = currentSchema;
  if (!schema || !Array.isArray(schema.params)) return payload;

  schema.params.forEach((spec) => {
    const card = document.querySelector("[data-param-name='" + CSS.escape(spec.name) + "']");
    if (!card) return;
    const control = card.querySelector("[data-role='value']");
    if (!control) return;

    if (spec.type === "boolean") {
      payload.params[spec.name] = Boolean(control.checked);
      return;
    }
    if (spec.type === "integer") {
      const raw = String(control.value || "").trim();
      if (!raw) {
        if (spec.required) payload.params[spec.name] = spec.default ?? null;
        return;
      }
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) payload.params[spec.name] = parsed;
      return;
    }
    if (spec.type === "string_list") {
      let values = [];
      if (control.tagName === "SELECT") {
        values = Array.from(control.selectedOptions || []).map((option) => option.value);
      } else {
        values = splitCsv(String(control.value || ""));
      }
      if (values.length > 0) payload.params[spec.name] = values;
      return;
    }
    const text = String(control.value || "").trim();
    if (text) payload.params[spec.name] = text;
  });
  return payload;
}

function renderSummary() {
  const rows = document.getElementById("sum-rows");
  if (!currentSchema || !currentSource) {
    rows.innerHTML = "";
    return;
  }
  const info = sourcesBySource[currentSource] || { title: currentSource, mode: "--" };
  const payload = buildPayload();
  const parts = [
    "<div class='row'><span class='k'>" + escapeHtml(t("sum_source")) + "</span><span class='v'>" + escapeHtml(info.title) + "</span></div>",
    "<div class='row'><span class='k'>" + escapeHtml(t("sum_mode")) + "</span><span class='v'>" + escapeHtml(info.mode) + "</span></div>"
  ];
  const entries = Object.entries(payload.params);
  if (entries.length === 0) {
    parts.push("<div class='row'><span class='k'>" + escapeHtml(t("sum_none")) + "</span></div>");
  } else {
    entries.forEach(([key, value]) => {
      const rendered = Array.isArray(value) ? value.join(", ") : String(value);
      parts.push(
        "<div class='row'><span class='k'>" + escapeHtml(prettyLabel(key)) + "</span><span class='v'>" +
        escapeHtml(rendered) + "</span></div>"
      );
    });
  }
  rows.innerHTML = parts.join("");
}

/* ═══ estimativa (discovery) ═══ */
async function estimateVolume() {
  if (!currentSource) return;
  const box = document.getElementById("estimate-box");
  box.hidden = false;
  box.textContent = t("estimating");
  const payload = buildPayload();
  try {
    const response = await fetch("/sources/" + encodeURIComponent(currentSource) + "/discovery", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: payload.params })
    });
    const raw = await response.json();
    if (!response.ok) {
      box.textContent = tf("estimate_fail", { err: raw.detail || response.status });
      return;
    }
    const size = Number(raw.total_size_bytes || 0);
    box.innerHTML = tf("estimate_result", {
      docs: Number(raw.documents_found || 0).toLocaleString(currentLang === "en" ? "en-US" : "pt-BR"),
      size: size > 0 ? tf("estimate_size", { size: humanBytes(size) }) : ""
    });
  } catch (error) {
    box.textContent = tf("estimate_fail", { err: String(error) });
  }
}

/* ═══ jobs ═══ */
const STATUS_BADGE = {
  queued: ["queued", "st_queued", "<circle cx='8' cy='8' r='5.5'/><path d='M8 5v3l2 2'/>", false],
  running: ["running", "st_running", "<path d='M8 2a6 6 0 1 1-6 6'/>", true],
  cancel_requested: ["warn", "st_cancel_requested", "<path d='M8 2a6 6 0 1 1-6 6'/>", true],
  canceled: ["canceled", "st_canceled", "<path d='M4 8h8'/>", false],
  completed: ["done", "st_completed", "<path d='M3 8.5l3.2 3L13 5'/>", false],
  failed: ["failed", "st_failed", "<path d='M4 4l8 8M12 4l-8 8'/>", false]
};

function badgeHtml(status) {
  const [cls, labelKey, icon, spinning] = STATUS_BADGE[status] || STATUS_BADGE.queued;
  return "<span class='badge " + cls + "'><svg viewBox='0 0 16 16' fill='none' stroke='currentColor' stroke-width='2'" +
    (spinning ? " class='spin'" : "") + ">" + icon + "</svg>" + escapeHtml(t(labelKey)) + "</span>";
}

function sourceTitle(source) {
  const info = sourcesBySource[source];
  return info ? info.title : source;
}

function jobMatchesFilter(job) {
  if (jobsFilter === "active" && (isTerminalStatus(job.status))) return false;
  if (jobsFilter === "completed" && job.status !== "completed") return false;
  if (jobsFilter === "failed" && job.status !== "failed") return false;
  if (jobsQuery) {
    const q = jobsQuery;
    const hay = (job.job_id + " " + job.source + " " + sourceTitle(job.source)).toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function renderKpis() {
  const running = lastJobs.filter((j) => j.status === "running" || j.status === "cancel_requested").length;
  const queued = lastJobs.filter((j) => j.status === "queued").length;
  const done = lastJobs.filter((j) => j.status === "completed").length;
  const failed = lastJobs.filter((j) => j.status === "failed").length;
  const bytes = lastJobs.reduce((acc, j) => acc + (Number(j.bytes_downloaded) || 0), 0);
  const files = lastJobs.reduce((acc, j) => acc + (Number(j.files_completed) || 0), 0);
  document.getElementById("kpi-running").textContent = String(running);
  document.getElementById("kpi-done").textContent = String(done);
  document.getElementById("kpi-failed").textContent = String(failed);
  document.getElementById("kpi-volume").textContent = humanBytes(bytes);
  document.getElementById("kpi-queued-note").textContent = tf("kpi_queued_note", { n: queued });
  document.getElementById("kpi-files-note").textContent = tf("kpi_files_note", { n: files });
}

function renderJobs() {
  const body = document.getElementById("jobs-body");
  body.innerHTML = "";
  const visible = lastJobs.filter(jobMatchesFilter);
  if (visible.length === 0) {
    const key = lastJobs.length === 0 ? "jobs_empty" : "jobs_empty_filter";
    body.innerHTML =
      "<tr class='row-empty'><td colspan='6' style='text-align:center;padding:30px;color:var(--muted)'>" +
      escapeHtml(t(key)) + "</td></tr>";
    return;
  }
  visible.forEach((job) => {
    const pct = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const live = job.status === "running" || job.status === "cancel_requested" ? " is-live" : "";
    const tr = document.createElement("tr");
    if (selectedJobId === job.job_id && document.body.classList.contains("drawer-open")) {
      tr.setAttribute("aria-selected", "true");
    }
    tr.innerHTML =
      "<td class='c-id'>" + escapeHtml(String(job.job_id).slice(0, 10)) + "</td>" +
      "<td class='src-cell'><strong>" + escapeHtml(sourceTitle(job.source)) + "</strong><span>" + escapeHtml(job.source) + "</span></td>" +
      "<td>" + badgeHtml(job.status) + "</td>" +
      "<td><div class='meter'><div class='meter-track'><div class='meter-fill" + live + "' style='width:" + pct + "%'></div></div>" +
        "<span class='meter-pct'>" + pct.toFixed(0) + "%</span></div></td>" +
      "<td class='c-num'>" + escapeHtml(String(job.files_completed || 0)) + " / " + escapeHtml(String(job.files_total || 0)) + "</td>" +
      "<td class='c-num'>" + escapeHtml(String(job.attempt || 1)) + "</td>";
    tr.addEventListener("click", () => openDrawer(job.job_id));
    body.appendChild(tr);
  });
}

async function fetchJobs() {
  const response = await fetch("/jobs?limit=" + JOBS_LIMIT);
  if (!response.ok) throw new Error("HTTP " + response.status);
  return await response.json();
}

async function refreshJobs() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    lastJobs = await fetchJobs();
    setApiStatus(true);
    renderKpis();
    renderJobs();
    if (selectedJobId && document.body.classList.contains("drawer-open")) {
      const job = lastJobs.find((item) => item.job_id === selectedJobId);
      if (job) {
        const previousStatus = selectedJobStatus;
        renderDrawer(job);
        const becameTerminal = previousStatus && !isTerminalStatus(previousStatus) && isTerminalStatus(job.status);
        if (!isTerminalStatus(job.status) || becameTerminal) {
          await refreshDrawerDetails(selectedJobId);
        }
      }
    }
  } catch (error) {
    setApiStatus(false);
  } finally {
    refreshInFlight = false;
  }
}

/* ═══ drawer ═══ */
function closeDrawer() {
  document.body.classList.remove("drawer-open");
  document.querySelectorAll("#jobs-body tr[aria-selected]").forEach((r) => r.removeAttribute("aria-selected"));
}

async function openDrawer(jobId) {
  selectedJobId = jobId;
  document.body.classList.add("drawer-open");
  renderJobs();
  let job = lastJobs.find((item) => item.job_id === jobId);
  if (!job) {
    try {
      const response = await fetch("/jobs/" + encodeURIComponent(jobId));
      if (response.ok) job = await response.json();
    } catch (error) { /* offline */ }
  }
  if (job) renderDrawer(job);
  await refreshDrawerDetails(jobId);
}

function renderDrawer(job) {
  selectedJobStatus = job.status || null;
  document.getElementById("drawer-title").textContent = sourceTitle(job.source);
  document.getElementById("drawer-id").textContent =
    job.job_id + " · " + t("lbl_attempt") + " " + String(job.attempt || 1);
  document.getElementById("drawer-badge").innerHTML = badgeHtml(job.status);
  document.getElementById("term-title").textContent = "guaraci — " + String(job.job_id).slice(0, 14);

  const pct = Math.max(0, Math.min(100, Number(job.progress || 0)));
  document.getElementById("d-pct").textContent =
    pct.toFixed(1).replace(".", currentLang === "en" ? "." : ",") + "%";
  const fill = document.getElementById("d-fill");
  fill.style.width = pct.toFixed(1) + "%";
  fill.classList.toggle("is-live", job.status === "running" || job.status === "cancel_requested");
  document.getElementById("d-progressbar").setAttribute("aria-valuenow", pct.toFixed(1));

  const bytes = humanBytes(job.bytes_downloaded);
  const bytesTotal = job.bytes_total ? " / " + humanBytes(job.bytes_total) : "";
  document.getElementById("d-files-bytes").textContent =
    String(job.files_completed || 0) + " / " + String(job.files_total || 0) + " · " + bytes + bytesTotal;
  document.getElementById("d-time").textContent =
    formatSeconds(job.elapsed_seconds) + " · ETA " + formatSeconds(job.eta_seconds);

  document.getElementById("d-source").textContent = job.source + " · " + ((sourcesBySource[job.source] || {}).mode || "--");
  document.getElementById("d-created").textContent = formatCreatedAt(job.created_at);
  document.getElementById("d-params").textContent = paramsSummaryText(job.params);
  document.getElementById("d-current").textContent = shortName(job.current_file);

  const errorBox = document.getElementById("d-error");
  if (job.error) {
    errorBox.hidden = false;
    errorBox.textContent = job.error;
  } else {
    errorBox.hidden = true;
  }

  document.getElementById("d-cancel").disabled = isTerminalStatus(job.status) || job.status === "cancel_requested";
  document.getElementById("d-retry").disabled = !(job.status === "failed" || job.status === "canceled");
}

function renderLogs(logs) {
  const box = document.getElementById("log-box");
  if (!Array.isArray(logs) || logs.length === 0) {
    box.textContent = t("no_logs");
    return;
  }
  const html = logs.map((item) => {
    const ts = formatLogTimestamp(item.timestamp_utc);
    const level = String(item.level || "info").toLowerCase();
    const cls = level === "error" ? "lg-err" : level === "warning" || level === "warn" ? "lg-warn" : "";
    const message = escapeHtml(String(item.message || ""));
    return "<span class='lg-time'>" + escapeHtml(ts) + "</span>  " +
      (cls ? "<span class='" + cls + "'>" + message + "</span>" : message);
  });
  box.innerHTML = html.join("\n");
  box.scrollTop = box.scrollHeight;
}

function renderOutputInfo(payload) {
  const dest = document.getElementById("d-dest");
  const exportedBox = document.getElementById("d-exported");
  const outputDir = payload && payload.output_dir ? String(payload.output_dir) : null;
  const hostOutputDir = payload && payload.host_output_dir ? String(payload.host_output_dir) : null;
  const bestPath = hostOutputDir || outputDir;
  if (!bestPath) {
    dest.textContent = "--";
    dest.dataset.path = "";
    exportedBox.hidden = true;
    return;
  }
  dest.textContent = bestPath;
  dest.dataset.path = bestPath;
  const exported = Array.isArray(payload.exported_files) ? payload.exported_files : [];
  if (exported.length > 0) {
    exportedBox.hidden = false;
    exportedBox.innerHTML =
      "<div style='font-weight:600;margin-bottom:4px'>" + escapeHtml(tf("exported_title", { n: exported.length })) + "</div>" +
      exported.slice(0, 12).map((path) => "<div class='mono'>• " + escapeHtml(shortName(path)) + "</div>").join("") +
      (exported.length > 12 ? "<div class='mono'>…</div>" : "");
  } else {
    exportedBox.hidden = true;
  }
}

async function refreshDrawerDetails(jobId) {
  if (!jobId) return;
  try {
    const [logsResp, outputResp] = await Promise.all([
      fetch("/jobs/" + encodeURIComponent(jobId) + "/logs?limit=120"),
      fetch("/jobs/" + encodeURIComponent(jobId) + "/output")
    ]);
    if (logsResp.ok) renderLogs(await logsResp.json());
    if (outputResp.ok) renderOutputInfo(await outputResp.json());
  } catch (error) { /* mantém o conteúdo anterior */ }
}

/* ═══ ações ═══ */
async function submitJob() {
  if (!currentSource) return;
  const payload = buildPayload();
  const btn = document.getElementById("btn-submit");
  btn.disabled = true;
  try {
    const response = await fetch("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const raw = await response.json();
    if (!response.ok) {
      toast((raw.detail || t("fail_create")), "fail");
      return;
    }
    toast(t("job_created") + raw.job_id, "ok");
    backToCatalog();
    go("jobs");
    await refreshJobs();
    await openDrawer(raw.job_id);
  } catch (error) {
    toast(String(error), "fail");
  } finally {
    btn.disabled = false;
  }
}

async function cancelJob(jobId) {
  if (!jobId) return;
  try {
    const response = await fetch("/jobs/" + encodeURIComponent(jobId) + "/cancel", { method: "POST" });
    const raw = await response.json();
    if (!response.ok) {
      toast(raw.detail || t("fail_cancel"), "fail");
      return;
    }
    toast(t("cancel_requested_for") + jobId);
    await refreshJobs();
  } catch (error) {
    toast(String(error), "fail");
  }
}

async function retryJob(jobId) {
  if (!jobId) return;
  try {
    const response = await fetch("/jobs/" + encodeURIComponent(jobId) + "/retry", { method: "POST" });
    const raw = await response.json();
    if (!response.ok) {
      toast(raw.detail || t("fail_retry"), "fail");
      return;
    }
    toast(t("retry_created") + raw.job_id, "ok");
    await refreshJobs();
    await openDrawer(raw.job_id);
  } catch (error) {
    toast(String(error), "fail");
  }
}

async function copyOutputPath() {
  const path = document.getElementById("d-dest").dataset.path || "";
  if (!path) {
    toast(t("copy_none"));
    return;
  }
  try {
    await navigator.clipboard.writeText(path);
    toast(t("copy_ok"), "ok");
  } catch (error) {
    toast(t("copy_fail"), "fail");
  }
}

async function openOutputFolder(jobId) {
  if (!jobId) return;
  try {
    const response = await fetch("/jobs/" + encodeURIComponent(jobId) + "/open-output", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      toast(payload.detail || t("open_fail"), "fail");
      return;
    }
    if (payload.opened) {
      toast(payload.message || t("open_ok"), "ok");
    } else {
      const hostPath = payload.host_output_dir || payload.output_dir || "";
      if (hostPath) document.getElementById("d-dest").dataset.path = String(hostPath);
      toast(payload.message || t("open_manual"));
    }
  } catch (error) {
    toast(String(error), "fail");
  }
}

/* ═══ bootstrap ═══ */
async function bootstrap() {
  applyI18n();

  document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => go(btn.dataset.view));
  });
  document.getElementById("topbar-new").addEventListener("click", () => go("new"));
  document.getElementById("lang-toggle").addEventListener("click", () => {
    setLang(currentLang === "pt" ? "en" : "pt");
  });
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("guaraci_theme", next); } catch (error) { /* ignore */ }
  });

  document.getElementById("job-search").addEventListener("input", (event) => {
    jobsQuery = String(event.target.value || "").trim().toLowerCase();
    renderJobs();
  });
  document.getElementById("jobs-seg").addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-filter]");
    if (!btn) return;
    document.querySelectorAll("#jobs-seg button").forEach((b) => b.setAttribute("aria-pressed", "false"));
    btn.setAttribute("aria-pressed", "true");
    jobsFilter = btn.dataset.filter;
    renderJobs();
  });
  document.getElementById("refresh-jobs").addEventListener("click", refreshJobs);

  document.getElementById("nc-search").addEventListener("input", () => {
    renderCatalogInto(document.getElementById("nc-catalog"), document.getElementById("nc-search").value, true);
  });
  document.getElementById("sources-search").addEventListener("input", () => {
    renderCatalogInto(document.getElementById("sources-catalog"), document.getElementById("sources-search").value, false);
  });

  document.getElementById("advanced-toggle").addEventListener("click", () => {
    document.getElementById("adv").classList.toggle("open");
  });
  document.getElementById("btn-back-catalog").addEventListener("click", backToCatalog);
  document.getElementById("btn-estimate").addEventListener("click", estimateVolume);
  document.getElementById("btn-submit").addEventListener("click", submitJob);
  document.getElementById("job-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitJob();
  });

  document.getElementById("drawer-close").addEventListener("click", closeDrawer);
  document.getElementById("drawer-scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawer();
      closeAllMultiSelectDropdowns();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".ms-dropdown")) closeAllMultiSelectDropdowns();
  });
  document.getElementById("d-cancel").addEventListener("click", () => cancelJob(selectedJobId));
  document.getElementById("d-retry").addEventListener("click", () => retryJob(selectedJobId));
  document.getElementById("d-copy").addEventListener("click", copyOutputPath);
  document.getElementById("d-open").addEventListener("click", () => openOutputFolder(selectedJobId));

  try {
    await loadSources();
    await refreshJobs();
    setApiStatus(true);
  } catch (error) {
    setApiStatus(false);
    toast(t("boot_error") + String(error), "fail");
  }

  /* deep-links: #new · #sources · #new=<fonte> · #job=<id> */
  const hash = location.hash.replace("#", "");
  if (hash === "new" || hash === "sources") {
    go(hash);
  } else if (hash.startsWith("new=")) {
    const source = decodeURIComponent(hash.slice(4));
    if (sourcesBySource[source]) await selectSource(source);
    else go("new");
  } else if (hash.startsWith("job=")) {
    await openDrawer(decodeURIComponent(hash.slice(4)));
  } else {
    playReveals("jobs");
  }
  setInterval(refreshJobs, 5000);
}

bootstrap();
