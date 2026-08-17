let wizardStep = 1;
let latestJobId = null;
let currentSchema = null;
const schemasBySource = {};
let refreshInFlight = false;
let selectedJobStatus = null;
let lastJobs = [];

/* ═══ i18n pt/en ═══ */
const I18N = {
  pt: {
    api_connecting: "API: conectando...",
    api_online: "API: online",
    api_offline: "API: offline",
    hero_tagline: "· coleta de dados",
    hero_subtitle: "Escolha a fonte, preencha os filtros e acompanhe o download — direto da fonte oficial.",
    new_job: "Novo Job",
    step1: "1. Fonte",
    step2: "2. Filtros",
    step3: "3. Revisão",
    step1_title: "Selecione a fonte",
    source_label: "Fonte",
    loading: "Carregando...",
    step1_hint: "O schema de parâmetros dessa fonte aparece abaixo.",
    schema_loading: "Carregando schema...",
    step2_title: "Defina os parâmetros",
    step2_hint: "Consulte seus downloads na pasta Guaraci Downloads na sua Área de Trabalho.",
    advanced: "Filtragem avançada",
    step3_title: "Confirmação",
    review_placeholder: "Preencha os campos para visualizar o resumo da operação.",
    step3_hint: "Confira os filtros escolhidos antes de criar o job.",
    btn_back: "Voltar",
    btn_next: "Próximo",
    btn_submit: "Criar Job",
    monitoring: "Monitoramento",
    no_job_selected: "Nenhum job selecionado.",
    cancel_selected: "Cancelar Selecionado",
    retry_selected: "Retry Selecionado",
    refresh_list: "Atualizar Lista",
    copy_path: "Copiar Caminho",
    open_folder: "Abrir Pasta",
    no_logs: "Sem logs para exibir.",
    output_unavailable: "Pasta de saída: indisponível.",
    jobs_caption: "Lista de jobs de download com status, progresso e ações",
    progress_label: "Progresso do download",
    th_job: "Job",
    th_status: "Status",
    th_source: "Fonte",
    th_attempt: "Tent.",
    th_summary: "Resumo",
    th_actions: "Ações",
    btn_select_row: "Selecionar",
    btn_cancel_row: "Cancelar",
    btn_retry_row: "Retry",
    required: "Obrigatório",
    activate: "Ativar",
    select_all: "Selecionar tudo",
    clear_sel: "Limpar",
    no_filter: "(sem filtro)",
    no_params: "Sem parâmetros configuráveis para esta fonte.",
    use_advanced: "Use os filtros avançados para configurar esta fonte.",
    review_select_source: "Selecione uma fonte para ver o resumo.",
    review_source: "Fonte:",
    review_mode: "Modo de coleta:",
    review_params: "Parâmetros selecionados:",
    review_none: "Nenhum parâmetro foi definido.",
    empty_value: "(vazio)",
    mode_prefix: "Modo: ",
    schema_unavailable: "Schema indisponível",
    schema_unavailable_source: "Schema indisponível para esta fonte.",
    tip: "Dica:",
    awaiting_result: "Aguardando resultado",
    file_prefix: "Arquivo: ",
    dest_prefix: "Destino: ",
    lbl_job: "Job:",
    lbl_source: "Fonte:",
    lbl_status: "Status:",
    lbl_attempt: "Tentativa:",
    lbl_summary: "Resumo:",
    lbl_files: "Arquivos:",
    lbl_bytes: "Transferido:",
    lbl_time: "Tempo:",
    lbl_eta: "ETA:",
    lbl_current_file: "Arquivo Atual:",
    lbl_output_folder: "Pasta de saída:",
    lbl_format: "Formato:",
    lbl_exported: "Arquivos exportados:",
    lbl_warning: "Aviso:",
    none_word: "nenhum",
    job_created: "Job criado: ",
    cancel_requested_for: "Cancelamento solicitado para ",
    retry_created: "Retry criado: ",
    copy_ok: "Caminho copiado para a área de transferência.",
    copy_fail: "Não foi possível copiar o caminho.",
    copy_none: "Ainda não há pasta de saída para copiar.",
    open_select_job: "Selecione um job para abrir a pasta.",
    open_fail: "Não foi possível abrir a pasta.",
    open_ok: "Comando para abrir pasta executado.",
    open_manual: "Abra a pasta manualmente usando o caminho exibido.",
    fail_create: "Falha ao criar job",
    fail_cancel: "Falha ao cancelar job",
    fail_retry: "Falha ao disparar retry",
    fail_sources: "Falha ao carregar fontes",
    boot_error: "Erro ao iniciar interface: "
  },
  en: {
    api_connecting: "API: connecting...",
    api_online: "API: online",
    api_offline: "API: offline",
    hero_tagline: "· data collection",
    hero_subtitle: "Pick the source, fill in the filters and track the download — straight from the official source.",
    new_job: "New Job",
    step1: "1. Source",
    step2: "2. Filters",
    step3: "3. Review",
    step1_title: "Select the source",
    source_label: "Source",
    loading: "Loading...",
    step1_hint: "The parameter schema for this source appears below.",
    schema_loading: "Loading schema...",
    step2_title: "Set the parameters",
    step2_hint: "Find your downloads in the Guaraci Downloads folder on your Desktop.",
    advanced: "Advanced filtering",
    step3_title: "Confirmation",
    review_placeholder: "Fill in the fields to preview the operation summary.",
    step3_hint: "Check the chosen filters before creating the job.",
    btn_back: "Back",
    btn_next: "Next",
    btn_submit: "Create Job",
    monitoring: "Monitoring",
    no_job_selected: "No job selected.",
    cancel_selected: "Cancel Selected",
    retry_selected: "Retry Selected",
    refresh_list: "Refresh List",
    copy_path: "Copy Path",
    open_folder: "Open Folder",
    no_logs: "No logs to display.",
    output_unavailable: "Output folder: unavailable.",
    jobs_caption: "List of download jobs with status, progress and actions",
    progress_label: "Download progress",
    th_job: "Job",
    th_status: "Status",
    th_source: "Source",
    th_attempt: "Att.",
    th_summary: "Summary",
    th_actions: "Actions",
    btn_select_row: "Select",
    btn_cancel_row: "Cancel",
    btn_retry_row: "Retry",
    required: "Required",
    activate: "Enable",
    select_all: "Select all",
    clear_sel: "Clear",
    no_filter: "(no filter)",
    no_params: "No configurable parameters for this source.",
    use_advanced: "Use the advanced filters to configure this source.",
    review_select_source: "Select a source to see the summary.",
    review_source: "Source:",
    review_mode: "Collection mode:",
    review_params: "Selected parameters:",
    review_none: "No parameter was set.",
    empty_value: "(empty)",
    mode_prefix: "Mode: ",
    schema_unavailable: "Schema unavailable",
    schema_unavailable_source: "Schema unavailable for this source.",
    tip: "Tip:",
    awaiting_result: "Waiting for result",
    file_prefix: "File: ",
    dest_prefix: "Destination: ",
    lbl_job: "Job:",
    lbl_source: "Source:",
    lbl_status: "Status:",
    lbl_attempt: "Attempt:",
    lbl_summary: "Summary:",
    lbl_files: "Files:",
    lbl_bytes: "Transferred:",
    lbl_time: "Time:",
    lbl_eta: "ETA:",
    lbl_current_file: "Current File:",
    lbl_output_folder: "Output folder:",
    lbl_format: "Format:",
    lbl_exported: "Exported files:",
    lbl_warning: "Warning:",
    none_word: "none",
    job_created: "Job created: ",
    cancel_requested_for: "Cancellation requested for ",
    retry_created: "Retry created: ",
    copy_ok: "Path copied to clipboard.",
    copy_fail: "Could not copy the path.",
    copy_none: "There is no output folder to copy yet.",
    open_select_job: "Select a job to open its folder.",
    open_fail: "Could not open the folder.",
    open_ok: "Open-folder command executed.",
    open_manual: "Open the folder manually using the displayed path.",
    fail_create: "Failed to create job",
    fail_cancel: "Failed to cancel job",
    fail_retry: "Failed to trigger retry",
    fail_sources: "Failed to load sources",
    boot_error: "Error starting the interface: "
  }
};

let currentLang = (function () {
  try {
    const saved = localStorage.getItem("guaraci_lang");
    if (saved === "pt" || saved === "en") {
      return saved;
    }
  } catch (error) {
    /* localStorage indisponível */
  }
  return "pt";
})();

function t(key) {
  const table = I18N[currentLang] || I18N.pt;
  if (Object.prototype.hasOwnProperty.call(table, key)) {
    return table[key];
  }
  if (Object.prototype.hasOwnProperty.call(I18N.pt, key)) {
    return I18N.pt[key];
  }
  return key;
}

function applyI18n() {
  document.documentElement.lang = currentLang === "en" ? "en" : "pt-BR";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  const langBtn = document.getElementById("lang-toggle");
  if (langBtn) {
    langBtn.textContent = currentLang === "pt" ? "EN" : "PT";
    langBtn.setAttribute(
      "aria-label",
      currentLang === "pt" ? "Switch to English" : "Mudar para português"
    );
  }
  const track = document.querySelector(".progress-track");
  if (track) {
    track.setAttribute("aria-label", t("progress_label"));
  }
}

function setLang(lang) {
  currentLang = lang === "en" ? "en" : "pt";
  try {
    localStorage.setItem("guaraci_lang", currentLang);
  } catch (error) {
    /* localStorage indisponível */
  }
  applyI18n();
  if (currentSchema) {
    renderSchemaDetails(currentSchema);
  }
  renderReview();
  if (Array.isArray(lastJobs) && lastJobs.length > 0) {
    renderJobs(lastJobs);
    const selected = lastJobs.find((item) => item.job_id === latestJobId);
    if (selected) {
      renderLatest(selected);
    }
  }
  if (latestJobId) {
    refreshSelectedDetails(latestJobId);
  }
}

function splitCsv(rawValue) {
  return rawValue
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function statusClass(status) {
  return "status-" + (status || "queued");
}

function isTerminalStatus(status) {
  return status === "completed" || status === "failed" || status === "canceled";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("`", "&#96;");
}

function formatSeconds(value) {
  if (value === null || value === undefined) {
    return "--";
  }
  const total = Math.max(0, Math.round(Number(value)));
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return String(min).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
}

function humanBytes(value) {
  if (value === null || value === undefined) {
    return "--";
  }
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "--";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = bytes;
  let idx = 0;
  while (amount >= 1024 && idx < units.length - 1) {
    amount /= 1024;
    idx += 1;
  }
  return amount.toFixed(idx === 0 ? 0 : 1) + " " + units[idx];
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatLogTimestamp(raw) {
  if (!raw) {
    return "--";
  }
  const compactPattern = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;
  const text = String(raw);
  if (compactPattern.test(text)) {
    return text;
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return text.replace("T", " ").replace(/\.\d+/, "").replace("Z", "").replace("+00:00", "");
  }
  return (
    parsed.getUTCFullYear() + "-" +
    pad2(parsed.getUTCMonth() + 1) + "-" +
    pad2(parsed.getUTCDate()) + " " +
    pad2(parsed.getUTCHours()) + ":" +
    pad2(parsed.getUTCMinutes()) + ":" +
    pad2(parsed.getUTCSeconds())
  );
}

function shortName(pathOrUrl) {
  if (!pathOrUrl) {
    return "--";
  }
  const text = String(pathOrUrl).trim();
  if (!text) {
    return "--";
  }
  const normalized = text.replaceAll("\\", "/");
  const idx = normalized.lastIndexOf("/");
  return idx >= 0 ? normalized.slice(idx + 1) || normalized : normalized;
}

function setProgressPanel(job, outputDir) {
  const pctValue = Math.max(0, Math.min(100, Number(job && job.progress ? job.progress : 0)));
  const elapsed = formatSeconds(job ? job.elapsed_seconds : null);
  const eta = formatSeconds(job ? job.eta_seconds : null);
  const fileName = shortName(job ? job.current_file : null);
  const destination = outputDir || (job && job.output_dir ? String(job.output_dir) : "--");

  document.getElementById("progress-percent").textContent = pctValue.toFixed(1) + "%";
  document.getElementById("progress-time").textContent = elapsed + " | ETA " + eta;
  document.getElementById("progress-fill").style.width = pctValue.toFixed(1) + "%";
  const track = document.querySelector(".progress-track");
  if (track) {
    track.setAttribute("aria-valuenow", pctValue.toFixed(1));
  }
  document.getElementById("progress-file").textContent = t("file_prefix") + fileName;
  document.getElementById("progress-destination").textContent = t("dest_prefix") + destination;
}

function showNotice(type, message) {
  const box = document.getElementById("notice");
  box.className = "notice notice-visible notice-" + type;
  box.textContent = message;
}

function clearNotice() {
  const box = document.getElementById("notice");
  box.className = "notice";
  box.textContent = "";
}

function setApiPill(ok) {
  const pill = document.getElementById("api-pill");
  if (ok) {
    pill.textContent = t("api_online");
    pill.style.background = "rgba(52, 211, 153, 0.12)";
    pill.style.color = "#34d399";
  } else {
    pill.textContent = t("api_offline");
    pill.style.background = "rgba(255, 125, 104, 0.12)";
    pill.style.color = "#ff7d68";
  }
}

function setWizardStep(step) {
  wizardStep = Math.max(1, Math.min(3, step));
  document.querySelectorAll(".step-btn").forEach((btn) => {
    const active = Number(btn.dataset.step) === wizardStep;
    btn.classList.toggle("step-active", active);
  });
  document.querySelectorAll(".step-pane").forEach((pane) => {
    const active = Number(pane.dataset.stepPane) === wizardStep;
    pane.classList.toggle("step-visible", active);
  });
  document.getElementById("btn-prev").disabled = wizardStep === 1;
  document.getElementById("btn-next").disabled = wizardStep === 3;
  document.getElementById("btn-submit").disabled = wizardStep !== 3;
  if (wizardStep === 3) {
    renderReview();
  }
}

function prettyLabel(name) {
  const raw = String(name || "");
  if (raw === "output_dir") {
    return "Diretorio do Download";
  }
  if (raw === "keep_raw") {
    return "Manter Arquivo Bruto";
  }
  return String(name || "")
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function orderSchemaParams(params) {
  const priority = {
    output_dir: 10,
    output_format: 20,
    start_year: 30,
    end_year: 40
  };
  return [...params].sort((a, b) => {
    const pa = Object.prototype.hasOwnProperty.call(priority, a.name) ? priority[a.name] : 100;
    const pb = Object.prototype.hasOwnProperty.call(priority, b.name) ? priority[b.name] : 100;
    if (pa !== pb) {
      return pa - pb;
    }
    return String(a.name).localeCompare(String(b.name));
  });
}

function fieldHintText(spec) {
  const name = String(spec.name || "");
  const allowed = Array.isArray(spec.allowed_values) ? spec.allowed_values : [];

  if (name === "output_dir") {
    return "Diretorio principal de saida.\nPadrao: pasta Guaraci Downloads na Area de Trabalho.";
  }
  if (name === "output_format") {
    return "Formato de exportação pós-download.\nExemplo: csv";
  }
  if (name === "keep_raw") {
    return "Quando ativado, também salva o JSONL bruto da API.\nPadrão: desativado";
  }
  if (name === "start_year") {
    return "Ano inicial para buscar arquivos.\nExemplo: 2023";
  }
  if (name === "end_year") {
    return "Ano final para buscar arquivos.\nExemplo: 2025";
  }
  if (name === "uf") {
    return "Filtra por unidade federativa no arquivo exportado.\nExemplo: SP";
  }
  if (name === "sexo") {
    return "Filtra por sexo no arquivo exportado.\nExemplo: M";
  }
  if (name === "municipio") {
    return "Filtra por município (texto).\nExemplo: Fortaleza";
  }
  if (allowed.length > 0) {
    if (spec.type === "string_list") {
      return "Selecione um ou mais valores.\nExemplo: " + allowed.slice(0, 3).join(", ");
    }
    return "Selecione um valor válido.\nExemplo: " + String(allowed[0]);
  }
  if (spec.type === "integer") {
    const numericExample = spec.default ?? spec.minimum ?? 2024;
    return "Valor numérico.\nExemplo: " + String(numericExample);
  }
  if (spec.type === "boolean") {
    return "Ative para SIM; desative para NÃO.";
  }
  if (spec.type === "string_list") {
    return "Lista separada por vírgulas.\nExemplo: valor1, valor2";
  }
  return "Campo opcional de texto livre.";
}

function renderSchemaDetails(schema) {
  const box = document.getElementById("schema-info");
  const modeBadge = document.getElementById("source-mode");
  if (!schema || !Array.isArray(schema.params)) {
    modeBadge.textContent = t("schema_unavailable");
    box.textContent = t("schema_unavailable_source");
    return;
  }

  const modeText = String(schema.mode || "desconhecido");
  modeBadge.textContent = t("mode_prefix") + modeText;
  const modeLower = modeText.toLowerCase();
  let behaviorHint = "Download com filtros estruturados por parâmetros.";
  if (modeLower.includes("crawl")) {
    behaviorHint = "Crawler web: use filtros básicos e URL opcional quando necessário.";
  } else if (modeLower.includes("pysus")) {
    behaviorHint = "PySUS: use filtros de período, grupo e UF para reduzir volume.";
  } else if (modeLower.includes("opendatasus")) {
    behaviorHint = "OpenDataSUS API: prefira janelas curtas de data e abra filtros avançados só quando necessário.";
  }

  const ordered = orderSchemaParams(schema.params);
  const lines = ordered.map((item) => {
    const required = item.required ? "obrigatório" : "opcional";
    const type = item.type || "string";
    return prettyLabel(item.name) + " (" + type + ", " + required + ")";
  });
  box.innerHTML = "<div class='schema-lines'><b>" + escapeHtml(t("tip")) + "</b> " + escapeHtml(behaviorHint) + "<br>" +
    lines.map((line) => "• " + escapeHtml(line)).join("<br>") + "</div>";
}

function isAdvancedField(spec) {
  const name = String(spec.name || "");
  if (name === "output_dir") {
    return false;
  }
  if (name === "output_format") {
    return false;
  }
  const schema = currentSchema || {};
  const source = String(schema.source || "");
  const mode = String(schema.mode || "").toLowerCase();
  if (mode.includes("opendatasus")) {
    if (name === "start_date" || name === "end_date" || name === "keep_raw") {
      return true;
    }
    if (source === "zikavirus" && name === "uf") {
      return true;
    }
  }
  
  const technical = new Set([
    "api_base_url",
    "batch_size",
    "max_pages",
    "resource_id",
    "results_url",
    "timeout",
    "overwrite",
    "extract_archives"
  ]);
  if (technical.has(name)) {
    return true;
  }

  if (spec.phase === "basico" || spec.phase === "coleta" || spec.phase === "refinamento") {
    return false;
  }

  if (name.endsWith("_url") || name.endsWith("_id")) {
    return true;
  }

  return true;
}

function setAdvancedSectionVisible(show, expanded) {
  const toggle = document.getElementById("advanced-toggle");
  const wrap = document.getElementById("advanced-wrap");
  const arrow = document.getElementById("advanced-arrow");
  if (!toggle || !wrap || !arrow) {
    return;
  }
  toggle.hidden = !show;
  if (!show) {
    wrap.classList.remove("is-open");
    arrow.textContent = "▼";
    return;
  }
  wrap.classList.toggle("is-open", Boolean(expanded));
  arrow.textContent = expanded ? "▲" : "▼";
}

function createFieldCard(spec) {
  const field = document.createElement("div");
  const isWide = spec.type === "string_list" || spec.name === "results_url";
  field.className = "field-card" + (isWide ? " is-wide" : "");
  field.dataset.paramName = spec.name;
  field.dataset.paramType = spec.type;

  const title = document.createElement("div");
  title.className = "field-title";
  const labelText = document.createElement("span");
  labelText.textContent = prettyLabel(spec.name);
  title.appendChild(labelText);
  const hint = document.createElement("span");
  hint.className = "hint-icon";
  hint.textContent = "?";
  hint.tabIndex = 0;
  hint.setAttribute("role", "button");
  hint.setAttribute("data-tooltip", fieldHintText(spec));
  hint.setAttribute("title", fieldHintText(spec).replaceAll("\n", " | "));
  hint.setAttribute("aria-label", fieldHintText(spec).replaceAll("\n", " | "));
  title.appendChild(hint);
  if (spec.required) {
    const required = document.createElement("span");
    required.className = "field-required";
    required.textContent = t("required");
    title.appendChild(required);
  }
  field.appendChild(title);

  const help = document.createElement("p");
  help.className = "field-help";
  help.textContent = spec.description || "";
  field.appendChild(help);

  if (spec.type === "boolean") {
    const checkWrap = document.createElement("label");
    checkWrap.className = "toggles";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.role = "value";
    input.checked = Boolean(spec.default);
    input.addEventListener("change", renderReview);
    checkWrap.appendChild(input);
    checkWrap.append(" " + t("activate"));
    field.appendChild(checkWrap);
    return field;
  }

  if (spec.type === "integer") {
    const input = document.createElement("input");
    input.type = "number";
    input.step = "1";
    input.dataset.role = "value";
    if (spec.minimum !== null && spec.minimum !== undefined) {
      input.min = String(spec.minimum);
    }
    if (spec.maximum !== null && spec.maximum !== undefined) {
      input.max = String(spec.maximum);
    }
    if (spec.default !== null && spec.default !== undefined) {
      input.value = String(spec.default);
    }
    input.placeholder = spec.minimum !== null && spec.minimum !== undefined
      ? "Mínimo: " + spec.minimum
      : "";
    input.addEventListener("input", renderReview);
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
    if (spec.default !== null && spec.default !== undefined) {
      select.value = String(spec.default);
    }
    select.addEventListener("change", renderReview);
    field.appendChild(select);
    return field;
  }

  if (spec.type === "string_list" && Array.isArray(spec.allowed_values) && spec.allowed_values.length > 0) {
    const controls = document.createElement("div");
    controls.className = "output-controls";
    controls.style.marginBottom = "6px";

    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "btn-small btn-muted";
    allBtn.textContent = t("select_all");
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "btn-small btn-alt";
    clearBtn.textContent = t("clear_sel");
    controls.appendChild(allBtn);
    controls.appendChild(clearBtn);
    field.appendChild(controls);

    const select = document.createElement("select");
    select.dataset.role = "value";
    select.multiple = true;
    select.className = "multi-select";
    select.size = Math.min(12, Math.max(4, spec.allowed_values.length));
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
    select.addEventListener("change", renderReview);
    allBtn.addEventListener("click", () => {
      Array.from(select.options).forEach((option) => {
        option.selected = true;
      });
      renderReview();
    });
    clearBtn.addEventListener("click", () => {
      Array.from(select.options).forEach((option) => {
        option.selected = false;
      });
      renderReview();
    });
    field.appendChild(select);
    return field;
  }

  const input = document.createElement("input");
  input.dataset.role = "value";
  if (spec.type === "string_list") {
    const defaultCsv = Array.isArray(spec.default) ? spec.default.join(", ") : "";
    input.placeholder = defaultCsv || "valor1, valor2";
    input.value = defaultCsv;
  } else {
    input.placeholder = spec.default !== null && spec.default !== undefined
      ? String(spec.default)
      : "";
    if (spec.default !== null && spec.default !== undefined) {
      input.value = String(spec.default);
    }
  }
  input.addEventListener("input", renderReview);
  field.appendChild(input);
  return field;
}

function renderDynamicFields(schema) {
  const basic = document.getElementById("dynamic-fields-basic");
  const advanced = document.getElementById("dynamic-fields-advanced");
  if (!basic || !advanced) {
    return;
  }
  basic.innerHTML = "";
  advanced.innerHTML = "";
  setAdvancedSectionVisible(false, false);

  if (!schema || !Array.isArray(schema.params) || schema.params.length === 0) {
    basic.innerHTML = "<div class='field-card is-wide'>" + escapeHtml(t("no_params")) + "</div>";
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

  if (basic.children.length === 0 && advancedCount > 0) {
    basic.innerHTML = "<div class='field-card is-wide'>" + escapeHtml(t("use_advanced")) + "</div>";
  }
  setAdvancedSectionVisible(advancedCount > 0, false);
}

function buildPayload() {
  const payload = {
    source: document.getElementById("source").value,
    params: {}
  };
  const schema = currentSchema;
  if (!schema || !Array.isArray(schema.params)) {
    return payload;
  }

  schema.params.forEach((spec) => {
    const card = document.querySelector("[data-param-name='" + spec.name + "']");
    if (!card) {
      return;
    }
    const control = card.querySelector("[data-role='value']");
    if (!control) {
      return;
    }

    if (spec.type === "boolean") {
      payload.params[spec.name] = Boolean(control.checked);
      return;
    }

    if (spec.type === "integer") {
      const raw = String(control.value || "").trim();
      if (!raw) {
        if (spec.required) {
          payload.params[spec.name] = spec.default ?? null;
        }
        return;
      }
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) {
        payload.params[spec.name] = parsed;
      }
      return;
    }

    if (spec.type === "string_list") {
      let values = [];
      if (control.tagName === "SELECT") {
        values = Array.from(control.selectedOptions || []).map((option) => option.value);
      } else {
        values = splitCsv(String(control.value || ""));
      }
      if (values.length > 0) {
        payload.params[spec.name] = values;
      }
      return;
    }

    const text = String(control.value || "").trim();
    if (text) {
      payload.params[spec.name] = text;
    }
  });
  return payload;
}

function renderReview() {
  const reviewBox = document.getElementById("review-box");
  const payload = buildPayload();
  const schema = currentSchema;
  if (!schema || !Array.isArray(schema.params)) {
    reviewBox.textContent = t("review_select_source");
    return;
  }

  const selectedParams = Object.entries(payload.params);
  const items = [
    "<div class='review-item'><span class='review-key'>" + escapeHtml(t("review_source")) + "</span> " + escapeHtml(String(schema.title || payload.source)) + "</div>",
    "<div class='review-item'><span class='review-key'>" + escapeHtml(t("review_mode")) + "</span> " + escapeHtml(String(schema.mode || "--")) + "</div>",
  ];
  if (selectedParams.length === 0) {
    items.push("<div class='review-item'>" + escapeHtml(t("review_none")) + "</div>");
  } else {
    items.push("<div class='review-item'><span class='review-key'>" + escapeHtml(t("review_params")) + "</span></div>");
    selectedParams.forEach(([key, value]) => {
      const rendered = Array.isArray(value) ? value.join(", ") : String(value);
      items.push(
        "<div class='review-item'>• " + escapeHtml(prettyLabel(key)) + ": " + escapeHtml(rendered || t("empty_value")) + "</div>"
      );
    });
  }
  reviewBox.innerHTML = items.join("");
}

async function loadSourceSchema(source) {
  if (schemasBySource[source]) {
    return schemasBySource[source];
  }
  const response = await fetch("/sources/" + source + "/schema");
  if (!response.ok) {
    return null;
  }
  const schema = await response.json();
  schemasBySource[source] = schema;
  return schema;
}

async function applySourceSchema(source) {
  const schema = await loadSourceSchema(source);
  currentSchema = schema;
  renderSchemaDetails(schema);
  renderDynamicFields(schema);
  renderReview();
}

async function loadSources() {
  const response = await fetch("/sources");
  if (!response.ok) {
    throw new Error(t("fail_sources"));
  }
  const sources = (await response.json()).slice().sort((a, b) =>
    String(a.title || a.source).localeCompare(String(b.title || b.source))
  );
  const select = document.getElementById("source");
  select.innerHTML = "";
  sources.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.source;
    option.textContent = item.title;
    select.appendChild(option);
  });
  if (sources.length > 0) {
    await applySourceSchema(sources[0].source);
  }
}

function resultSummary(job) {
  if (job.error) {
    return job.error;
  }
  if (!job.result) {
    return t("awaiting_result");
  }
  const success = job.result.downloaded_count ?? 0;
  const failed = job.result.failed_count ?? 0;
  const skipped = job.result.skipped_count ?? 0;
  return "down=" + success + " | skip=" + skipped + " | fail=" + failed;
}

function jobLine(job) {
  const status = job.status || "queued";
  const pct = Number(job.progress || 0).toFixed(0) + "%";
  return "<span class='" + statusClass(status) + "'>" + escapeHtml(status) + "</span> (" + pct + ")";
}

async function fetchJob(jobId) {
  const response = await fetch("/jobs/" + jobId);
  if (!response.ok) {
    throw new Error("Falha ao consultar job " + jobId);
  }
  return await response.json();
}

async function fetchJobs() {
  const response = await fetch("/jobs?limit=40");
  if (!response.ok) {
    throw new Error("Falha ao listar jobs");
  }
  return await response.json();
}

async function fetchJobLogs(jobId) {
  const response = await fetch("/jobs/" + jobId + "/logs?limit=120");
  if (!response.ok) {
    throw new Error("Falha ao consultar logs do job " + jobId);
  }
  return await response.json();
}

async function fetchJobOutput(jobId) {
  const response = await fetch("/jobs/" + jobId + "/output");
  if (!response.ok) {
    throw new Error("Falha ao consultar saída do job " + jobId);
  }
  return await response.json();
}

function renderLatest(job) {
  latestJobId = job.job_id;
  selectedJobStatus = job.status || null;
  const box = document.getElementById("latest-job");
  const status = jobLine(job);
  const elapsed = formatSeconds(job.elapsed_seconds);
  const eta = formatSeconds(job.eta_seconds);
  const bytesLabel = humanBytes(job.bytes_downloaded);
  const bytesTotalLabel = humanBytes(job.bytes_total);
  const currentFile = shortName(job.current_file || "--");
  box.innerHTML =
    "<div><b>" + escapeHtml(t("lbl_job")) + "</b> <span class='mono'>" + escapeHtml(job.job_id) + "</span></div>" +
    "<div><b>" + escapeHtml(t("lbl_source")) + "</b> " + escapeHtml(job.source) + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_status")) + "</b> " + status + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_attempt")) + "</b> " + escapeHtml(String(job.attempt || 1)) + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_summary")) + "</b> " + escapeHtml(resultSummary(job)) + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_files")) + "</b> " + escapeHtml(String(job.files_completed || 0)) + " / " +
      escapeHtml(String(job.files_total || 0)) + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_bytes")) + "</b> " + bytesLabel + " / " + bytesTotalLabel + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_time")) + "</b> " + elapsed + " | <b>" + escapeHtml(t("lbl_eta")) + "</b> " + eta + "</div>" +
    "<div><b>" + escapeHtml(t("lbl_current_file")) + "</b> " + escapeHtml(currentFile) + "</div>";
  setProgressPanel(job, null);
}

function renderOutputInfo(payload) {
  const box = document.getElementById("output-path");
  const outputDir = payload && payload.output_dir ? String(payload.output_dir) : null;
  const hostOutputDir = payload && payload.host_output_dir ? String(payload.host_output_dir) : null;
  const bestPath = hostOutputDir || outputDir;
  if (!payload || !outputDir) {
    box.textContent = t("output_unavailable");
    box.dataset.path = "";
    document.getElementById("progress-destination").textContent = t("dest_prefix") + "--";
    return;
  }
  const suffix = hostOutputDir ? " (host)" : "";
  const exported = Array.isArray(payload.exported_files) ? payload.exported_files : [];
  const format = payload.output_format ? String(payload.output_format) : "";
  const warning = payload.export_warning ? String(payload.export_warning) : "";
  const exportedLabel = exported.length > 0
    ? exported.map((path) => "• " + escapeHtml(String(path))).join("<br>")
    : escapeHtml(t("none_word"));
  box.innerHTML =
    "<b>" + escapeHtml(t("lbl_output_folder")) + "</b> " + escapeHtml(bestPath + suffix) + "<br>" +
    (format ? "<b>" + escapeHtml(t("lbl_format")) + "</b> " + escapeHtml(format) + "<br>" : "") +
    "<b>" + escapeHtml(t("lbl_exported")) + "</b> " + exported.length + "<br>" +
    (exported.length > 0 ? exportedLabel + "<br>" : "") +
    (warning ? "<b>" + escapeHtml(t("lbl_warning")) + "</b> " + escapeHtml(warning) : "");
  box.dataset.path = bestPath;
  document.getElementById("progress-destination").textContent = t("dest_prefix") + bestPath;
}

function renderLogs(logs) {
  const box = document.getElementById("log-box");
  if (!Array.isArray(logs) || logs.length === 0) {
    box.textContent = t("no_logs");
    return;
  }
  const lines = logs.map((item) => {
    const ts = formatLogTimestamp(item.timestamp_utc || "--");
    const level = String(item.level || "info").toUpperCase();
    const message = String(item.message || "");
    return "[" + ts + "] [" + level + "] " + message;
  });
  box.textContent = lines.join("\n");
  box.scrollTop = box.scrollHeight;
}

async function refreshSelectedDetails(jobId) {
  if (!jobId) {
    renderOutputInfo(null);
    renderLogs([]);
    return;
  }
  try {
    const [logs, output] = await Promise.all([fetchJobLogs(jobId), fetchJobOutput(jobId)]);
    renderLogs(logs);
    renderOutputInfo(output);
  } catch (error) {
    showNotice("fail", String(error));
  }
}

async function copyOutputPath() {
  const path = document.getElementById("output-path").dataset.path || "";
  if (!path) {
    showNotice("info", t("copy_none"));
    return;
  }
  try {
    await navigator.clipboard.writeText(path);
    showNotice("ok", t("copy_ok"));
  } catch (error) {
    showNotice("fail", t("copy_fail"));
  }
}

async function openOutputFolder(jobId) {
  if (!jobId) {
    showNotice("info", t("open_select_job"));
    return;
  }
  clearNotice();
  try {
    const response = await fetch("/jobs/" + jobId + "/open-output", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      showNotice("fail", payload.detail || t("open_fail"));
      return;
    }
    if (payload.opened) {
      showNotice("ok", payload.message || t("open_ok"));
    } else {
      const hostPath = payload.host_output_dir || payload.output_dir || "";
      if (hostPath) {
        document.getElementById("output-path").dataset.path = String(hostPath);
      }
      showNotice("info", payload.message || t("open_manual"));
    }
  } catch (error) {
    showNotice("fail", String(error));
  }
}

function renderJobs(jobs) {
  lastJobs = Array.isArray(jobs) ? jobs : [];
  const body = document.getElementById("jobs-body");
  body.innerHTML = "";
  jobs.forEach((job) => {
    const isSelected = latestJobId && latestJobId === job.job_id;
    const row = document.createElement("tr");
    if (isSelected) {
      row.classList.add("is-selected");
    }

    const canCancel = !isTerminalStatus(job.status);
    const canRetry = job.status === "failed" || job.status === "canceled";

    row.innerHTML =
      "<td class='mono'>" + escapeHtml(job.job_id) + "</td>" +
      "<td>" + jobLine(job) + "</td>" +
      "<td>" + escapeHtml(job.source) + "</td>" +
      "<td>" + escapeHtml(String(job.attempt || 1)) + "</td>" +
      "<td>" + escapeHtml(resultSummary(job)) + "</td>" +
      "<td>" +
        "<button class='btn-small btn-muted' type='button' data-action='select' data-job='" + escapeHtml(job.job_id) + "'>" + escapeHtml(t("btn_select_row")) + "</button> " +
        "<button class='btn-small btn-fail' type='button' data-action='cancel' data-job='" + escapeHtml(job.job_id) + "'" + (canCancel ? "" : " disabled") + ">" + escapeHtml(t("btn_cancel_row")) + "</button> " +
        "<button class='btn-small btn-warn' type='button' data-action='retry' data-job='" + escapeHtml(job.job_id) + "'" + (canRetry ? "" : " disabled") + ">" + escapeHtml(t("btn_retry_row")) + "</button>" +
      "</td>";
    body.appendChild(row);
  });
}

async function refreshJobs() {
  if (refreshInFlight) {
    return;
  }
  refreshInFlight = true;
  try {
    const jobs = await fetchJobs();
    renderJobs(jobs);

    if (!latestJobId && jobs.length > 0) {
      latestJobId = jobs[0].job_id;
      renderLatest(jobs[0]);
      await refreshSelectedDetails(latestJobId);
      return;
    }

    if (latestJobId) {
      const selected = jobs.find((item) => item.job_id === latestJobId);
      if (selected) {
        const previousStatus = selectedJobStatus;
        renderLatest(selected);
        const transitionedToTerminal = Boolean(
          previousStatus &&
          !isTerminalStatus(previousStatus) &&
          isTerminalStatus(selected.status)
        );
        if (!isTerminalStatus(selected.status) || transitionedToTerminal) {
          await refreshSelectedDetails(latestJobId);
        }
      }
    }
  } catch (error) {
    showNotice("fail", String(error));
  } finally {
    refreshInFlight = false;
  }
}

async function submitJob(event) {
  event.preventDefault();
  clearNotice();
  const payload = buildPayload();

  try {
    const response = await fetch("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const raw = await response.json();

    if (!response.ok) {
      showNotice("fail", raw.detail || t("fail_create"));
      return;
    }

    renderLatest(raw);
    await refreshSelectedDetails(raw.job_id);
    showNotice("ok", t("job_created") + raw.job_id);
    await refreshJobs();
  } catch (error) {
    showNotice("fail", String(error));
  }
}

async function cancelJob(jobId) {
  if (!jobId) {
    return;
  }
  clearNotice();
  try {
    const response = await fetch("/jobs/" + jobId + "/cancel", { method: "POST" });
    const raw = await response.json();
    if (!response.ok) {
      showNotice("fail", raw.detail || t("fail_cancel"));
      return;
    }
    renderLatest(raw);
    await refreshSelectedDetails(raw.job_id);
    showNotice("info", t("cancel_requested_for") + jobId);
    await refreshJobs();
  } catch (error) {
    showNotice("fail", String(error));
  }
}

async function retryJob(jobId) {
  if (!jobId) {
    return;
  }
  clearNotice();
  try {
    const response = await fetch("/jobs/" + jobId + "/retry", { method: "POST" });
    const raw = await response.json();
    if (!response.ok) {
      showNotice("fail", raw.detail || t("fail_retry"));
      return;
    }
    renderLatest(raw);
    await refreshSelectedDetails(raw.job_id);
    showNotice("ok", t("retry_created") + raw.job_id);
    await refreshJobs();
  } catch (error) {
    showNotice("fail", String(error));
  }
}

function bindWizardEvents() {
  document.querySelectorAll(".step-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setWizardStep(Number(btn.dataset.step));
    });
  });

  document.getElementById("btn-prev").addEventListener("click", () => {
    setWizardStep(wizardStep - 1);
  });

  document.getElementById("btn-next").addEventListener("click", () => {
    setWizardStep(wizardStep + 1);
  });
}

function bindFieldEvents() {
  document.getElementById("source").addEventListener("change", async (event) => {
    await applySourceSchema(event.target.value);
  });
  document.getElementById("advanced-toggle").addEventListener("click", () => {
    const wrap = document.getElementById("advanced-wrap");
    const open = !(wrap && wrap.classList.contains("is-open"));
    setAdvancedSectionVisible(true, open);
  });
  document.getElementById("dynamic-fields").addEventListener("change", renderReview);
  document.getElementById("dynamic-fields").addEventListener("input", renderReview);
}

function bindJobTableEvents() {
  document.getElementById("jobs-body").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }
    const action = button.dataset.action;
    const jobId = button.dataset.job;
    if (!jobId) {
      return;
    }

    try {
      if (action === "select") {
        latestJobId = jobId;
        const job = await fetchJob(jobId);
        renderLatest(job);
        await refreshSelectedDetails(jobId);
        await refreshJobs();
        return;
      }
      if (action === "cancel") {
        await cancelJob(jobId);
        return;
      }
      if (action === "retry") {
        await retryJob(jobId);
      }
    } catch (error) {
      showNotice("fail", String(error));
    }
  });
}

async function bootstrap() {
  applyI18n();
  const langBtn = document.getElementById("lang-toggle");
  if (langBtn) {
    langBtn.addEventListener("click", () => {
      setLang(currentLang === "pt" ? "en" : "pt");
    });
  }

  try {
    await loadSources();
    renderReview();
    await refreshJobs();
    setApiPill(true);
  } catch (error) {
    setApiPill(false);
    showNotice("fail", t("boot_error") + String(error));
  }

  bindWizardEvents();
  bindFieldEvents();
  bindJobTableEvents();

  document.getElementById("job-form").addEventListener("submit", submitJob);
  document.getElementById("cancel-latest").addEventListener("click", async () => {
    await cancelJob(latestJobId);
  });
  document.getElementById("retry-latest").addEventListener("click", async () => {
    await retryJob(latestJobId);
  });
  document.getElementById("refresh-jobs").addEventListener("click", refreshJobs);
  document.getElementById("copy-output").addEventListener("click", copyOutputPath);
  document.getElementById("open-output").addEventListener("click", async () => {
    await openOutputFolder(latestJobId);
  });

  setWizardStep(1);
  setInterval(refreshJobs, 8000);
}

bootstrap();
