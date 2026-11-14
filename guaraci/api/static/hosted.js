/* ═══════════════════════════════════════════════════════════════
   Guaraci UI, modo hospedado (GUARACI_MODE=hosted).
   Carrega depois de app.js e divide o escopo global com ele. No modo local
   (/auth/me responde 404) nada daqui entra em cena.
   Todo texto vindo do servidor entra no DOM por textContent, nunca por
   innerHTML: nome, e-mail, finalidade e "detail" são entrada de usuário.
   ═══════════════════════════════════════════════════════════════ */
"use strict";

Object.assign(I18N.pt, {
  rate_limited: "Muitas requisições. Aguarde um instante e tente de novo.",
  nav_admin: "Administração",
  nav_admin_label: "Administração",
  nav_privacy: "Privacidade",
  logout: "Sair",
  loading: "Carregando…",
  auth_tab_login: "Entrar",
  auth_tab_signup: "Pedir acesso",
  auth_login_btn: "Entrar",
  auth_signup_btn: "Enviar pedido de acesso",
  auth_session_expired: "Sua sessão expirou. Entre de novo para continuar.",
  auth_login_fail: "Não foi possível entrar.",
  auth_signup_fail: "Não foi possível enviar o pedido.",
  auth_network: "Falha de conexão com o servidor.",
  auth_signup_done: "Pedido enviado. O acesso depende de aprovação.",
  auth_logging_note: "Para melhorar o serviço, registramos seus acessos, as telas visitadas e o endereço IP. Os detalhes estão na política de privacidade.",
  f_email: "E-mail",
  f_password: "Senha",
  f_name: "Nome completo",
  f_institution: "Instituição",
  f_purpose: "Finalidade do uso",
  f_password_new: "Senha (mínimo de 10 caracteres)",
  f_password_confirm: "Confirmação da senha",
  consent_pre: "Li e aceito a",
  consent_link: "política de privacidade",
  v_required: "Preencha todos os campos.",
  v_password_short: "A senha precisa ter pelo menos 10 caracteres.",
  v_password_match: "A confirmação da senha não confere.",
  v_consent: "É preciso aceitar a política de privacidade.",
  quota_jobs: "{used} de {max} coletas em 24 h",
  quota_active: "{used} de {max} ativas",
  dl_title: "Arquivos da coleta",
  dl_zip: "Baixar tudo (.zip)",
  dl_available_until: "Disponível até {d}",
  dl_expired: "Expirado e apagado",
  dl_none: "Esta coleta não gerou arquivos.",
  adm_tab_overview: "Visão geral",
  adm_tab_users: "Usuários",
  adm_tab_jobs: "Coletas",
  adm_tab_events: "Eventos",
  adm_period: "Período",
  adm_days: "{n} dias",
  adm_load_fail: "Não foi possível carregar os dados.",
  adm_action_fail: "A ação não foi concluída.",
  adm_k_users_total: "Usuários",
  adm_k_users_pending: "Aguardando aprovação",
  adm_k_users_approved: "Aprovados",
  adm_k_active_users: "Usuários ativos",
  adm_k_distinct_ips: "IPs distintos",
  adm_k_logins: "Logins",
  adm_k_login_failures: "Logins recusados",
  adm_k_jobs: "Coletas criadas",
  adm_k_jobs_rejected: "Coletas rejeitadas",
  adm_k_downloads: "Downloads",
  adm_k_queued: "Na fila",
  adm_k_running: "Em execução",
  adm_per_day: "Atividade por dia",
  adm_top_sources: "Fontes mais usadas",
  adm_top_views: "Telas mais vistas",
  adm_th_day: "Dia",
  adm_th_users: "Usuários",
  adm_th_anon: "IPs anônimos",
  adm_th_views: "Telas",
  adm_th_jobs: "Coletas",
  adm_th_downloads: "Downloads",
  adm_th_source: "Fonte",
  adm_th_view: "Tela",
  adm_th_count: "Visitas",
  adm_th_n: "Total",
  adm_th_user: "Usuário",
  adm_th_inst: "Instituição",
  adm_th_status: "Situação",
  adm_th_role: "Papel",
  adm_th_created: "Cadastro",
  adm_th_last: "Último acesso",
  adm_th_quota: "Coletas 24 h",
  adm_th_actions: "Ações",
  adm_th_owner: "Dono",
  adm_th_expires: "Expira",
  adm_th_when: "Quando",
  adm_th_kind: "Tipo",
  adm_th_what: "Tela ou fonte",
  adm_th_job: "Coleta",
  adm_th_ip: "IP",
  adm_th_agent: "Navegador",
  adm_filter_status: "Situação",
  adm_f_pending: "Pendentes",
  adm_f_approved: "Aprovados",
  adm_f_rejected: "Recusados",
  adm_f_disabled: "Desativados",
  adm_f_all: "Todos",
  adm_no_users: "Nenhum usuário nesta situação.",
  adm_no_rows: "Nada registrado.",
  adm_st_pending: "Aguardando",
  adm_st_approved: "Aprovado",
  adm_st_rejected: "Recusado",
  adm_st_disabled: "Desativado",
  adm_role_admin: "Administrador",
  adm_role_user: "Usuário",
  adm_approve: "Aprovar",
  adm_reject: "Recusar",
  adm_disable: "Desativar",
  adm_reactivate: "Reativar",
  adm_make_admin: "Tornar administrador",
  adm_remove_admin: "Remover administrador",
  adm_delete: "Excluir",
  adm_delete_confirm: "Confirmar exclusão",
  adm_deleted: "Usuário excluído.",
  adm_updated: "Alteração salva.",
  adm_quota_label: "Cota diária",
  adm_quota_default: "padrão",
  adm_quota_save: "Salvar cota",
  adm_purpose: "Finalidade informada",
  adm_journey: "Jornada do usuário",
  adm_journey_empty: "Sem eventos registrados para este usuário.",
  adm_pick_user: "Clique num usuário para ver a ficha e a jornada.",
  adm_cancel_job: "Cancelar",
  adm_job_canceled: "Cancelamento solicitado.",
  adm_ev_filter: "Tipo de evento",
  adm_user_n: "usuário {n}",
  ev_all: "Todos",
  ev_page_view: "Tela visitada",
  ev_signup: "Pedido de acesso",
  ev_login_ok: "Login",
  ev_login_fail: "Login recusado",
  ev_lockout: "Bloqueio temporário",
  ev_logout: "Saída",
  ev_job_create: "Coleta criada",
  ev_job_rejected: "Coleta rejeitada",
  ev_job_cancel: "Coleta cancelada",
  ev_job_retry: "Coleta repetida",
  ev_download: "Download",
  ev_admin_action: "Ação administrativa"
});

Object.assign(I18N.en, {
  rate_limited: "Too many requests. Wait a moment and try again.",
  nav_admin: "Administration",
  nav_admin_label: "Administration",
  nav_privacy: "Privacy",
  logout: "Sign out",
  loading: "Loading…",
  auth_tab_login: "Sign in",
  auth_tab_signup: "Request access",
  auth_login_btn: "Sign in",
  auth_signup_btn: "Send access request",
  auth_session_expired: "Your session expired. Sign in again to continue.",
  auth_login_fail: "Could not sign in.",
  auth_signup_fail: "Could not send the request.",
  auth_network: "Connection to the server failed.",
  auth_signup_done: "Request sent. Access depends on approval.",
  auth_logging_note: "To improve the service, we record your visits, the screens you open and your IP address. Details are in the privacy policy.",
  f_email: "E-mail",
  f_password: "Password",
  f_name: "Full name",
  f_institution: "Institution",
  f_purpose: "Purpose of use",
  f_password_new: "Password (at least 10 characters)",
  f_password_confirm: "Confirm password",
  consent_pre: "I have read and accept the",
  consent_link: "privacy policy",
  v_required: "Fill in all fields.",
  v_password_short: "The password must have at least 10 characters.",
  v_password_match: "The password confirmation does not match.",
  v_consent: "You must accept the privacy policy.",
  quota_jobs: "{used} of {max} downloads in 24 h",
  quota_active: "{used} of {max} active",
  dl_title: "Download files",
  dl_zip: "Download all (.zip)",
  dl_available_until: "Available until {d}",
  dl_expired: "Expired and deleted",
  dl_none: "This download produced no files.",
  adm_tab_overview: "Overview",
  adm_tab_users: "Users",
  adm_tab_jobs: "Downloads",
  adm_tab_events: "Events",
  adm_period: "Period",
  adm_days: "{n} days",
  adm_load_fail: "Could not load the data.",
  adm_action_fail: "The action was not completed.",
  adm_k_users_total: "Users",
  adm_k_users_pending: "Awaiting approval",
  adm_k_users_approved: "Approved",
  adm_k_active_users: "Active users",
  adm_k_distinct_ips: "Distinct IPs",
  adm_k_logins: "Logins",
  adm_k_login_failures: "Rejected logins",
  adm_k_jobs: "Downloads created",
  adm_k_jobs_rejected: "Downloads rejected",
  adm_k_downloads: "File downloads",
  adm_k_queued: "Queued",
  adm_k_running: "Running",
  adm_per_day: "Activity per day",
  adm_top_sources: "Most used sources",
  adm_top_views: "Most viewed screens",
  adm_th_day: "Day",
  adm_th_users: "Users",
  adm_th_anon: "Anonymous IPs",
  adm_th_views: "Views",
  adm_th_jobs: "Downloads",
  adm_th_downloads: "File downloads",
  adm_th_source: "Source",
  adm_th_view: "Screen",
  adm_th_count: "Visits",
  adm_th_n: "Total",
  adm_th_user: "User",
  adm_th_inst: "Institution",
  adm_th_status: "Status",
  adm_th_role: "Role",
  adm_th_created: "Signed up",
  adm_th_last: "Last login",
  adm_th_quota: "Downloads 24 h",
  adm_th_actions: "Actions",
  adm_th_owner: "Owner",
  adm_th_expires: "Expires",
  adm_th_when: "When",
  adm_th_kind: "Type",
  adm_th_what: "Screen or source",
  adm_th_job: "Download",
  adm_th_ip: "IP",
  adm_th_agent: "Browser",
  adm_filter_status: "Status",
  adm_f_pending: "Pending",
  adm_f_approved: "Approved",
  adm_f_rejected: "Rejected",
  adm_f_disabled: "Disabled",
  adm_f_all: "All",
  adm_no_users: "No users in this status.",
  adm_no_rows: "Nothing recorded.",
  adm_st_pending: "Pending",
  adm_st_approved: "Approved",
  adm_st_rejected: "Rejected",
  adm_st_disabled: "Disabled",
  adm_role_admin: "Administrator",
  adm_role_user: "User",
  adm_approve: "Approve",
  adm_reject: "Reject",
  adm_disable: "Disable",
  adm_reactivate: "Reactivate",
  adm_make_admin: "Make administrator",
  adm_remove_admin: "Remove administrator",
  adm_delete: "Delete",
  adm_delete_confirm: "Confirm deletion",
  adm_deleted: "User deleted.",
  adm_updated: "Change saved.",
  adm_quota_label: "Daily quota",
  adm_quota_default: "default",
  adm_quota_save: "Save quota",
  adm_purpose: "Stated purpose",
  adm_journey: "User journey",
  adm_journey_empty: "No events recorded for this user.",
  adm_pick_user: "Click a user to see the profile and the journey.",
  adm_cancel_job: "Cancel",
  adm_job_canceled: "Cancellation requested.",
  adm_ev_filter: "Event type",
  adm_user_n: "user {n}",
  ev_all: "All",
  ev_page_view: "Screen viewed",
  ev_signup: "Access request",
  ev_login_ok: "Login",
  ev_login_fail: "Login rejected",
  ev_lockout: "Temporary lockout",
  ev_logout: "Sign out",
  ev_job_create: "Download created",
  ev_job_rejected: "Download rejected",
  ev_job_cancel: "Download canceled",
  ev_job_retry: "Download retried",
  ev_download: "File download",
  ev_admin_action: "Admin action"
});

/* ═══ estado e helpers ═══ */
let me = null;
const adminState = { tab: "overview", days: 30, userStatus: "pending", userId: null, eventKind: "", seq: 0 };
const EVENT_KINDS = [
  "page_view", "signup", "login_ok", "login_fail", "lockout", "logout",
  "job_create", "job_rejected", "job_cancel", "job_retry", "download", "admin_action"
];

function byId(id) { return document.getElementById(id); }

function h(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === false) return;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "on") Object.entries(value).forEach(([name, fn]) => node.addEventListener(name, fn));
    else node.setAttribute(key, value === true ? "" : value);
  });
  kids.flat().forEach((kid) => {
    if (kid === null || kid === undefined || kid === false) return;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  });
  return node;
}

function isAdmin() { return Boolean(me && me.user && me.user.role === "admin"); }

function parseTs(raw) {
  if (!raw) return null;
  const text = String(raw);
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(text);
  const parsed = new Date(hasZone ? text : text.replace(" ", "T") + "Z");
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function fmtDate(raw) {
  const d = parseTs(raw);
  if (!d) return raw ? String(raw) : "--";
  return pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1) + "/" + d.getFullYear() +
    " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
}

function fmtInt(value) {
  return Number(value || 0).toLocaleString(currentLang === "en" ? "en-US" : "pt-BR");
}

/* Só aceita caminho relativo ao próprio servidor ou URL de mesma origem. */
function safeUrl(url) {
  const text = String(url || "");
  if (/^\/(?!\/)/.test(text)) return text;
  try {
    const parsed = new URL(text, location.origin);
    if (parsed.origin === location.origin) return parsed.href;
  } catch (error) { /* url inválida */ }
  return null;
}

/* ═══ modo e sessão ═══ */
function applyMe(data) {
  if (data && data.authenticated) {
    me = data;
    csrfToken = data.csrf || null;
  } else {
    me = null;
    csrfToken = null;
  }
}

async function detectMode() {
  try {
    const response = await fetch("/auth/me", { credentials: "same-origin" });
    if (!response.ok) return; // 404: modo local
    const data = await response.json();
    if (!data || data.mode !== "hosted") return;
    hostedMode = true;
    document.body.classList.add("is-hosted");
    applyMe(data);
  } catch (error) {
    hostedMode = false;
  }
}

async function refreshMe() {
  if (!hostedMode) return;
  try {
    const response = await api("/auth/me");
    if (!response.ok) return;
    const data = await response.json();
    if (!data.authenticated) {
      onSessionExpired();
      return;
    }
    applyMe(data);
    renderQuota();
  } catch (error) { /* mantém o que já está na tela */ }
}

function resetAppState() {
  lastJobs = [];
  selectedJobId = null;
  selectedJobStatus = null;
  currentSource = null;
  currentSchema = null;
  closeDrawer();
  renderJobs();
  renderKpis();
  backToCatalog();
  adminState.userId = null;
  adminState.tab = "overview";
}

function onSessionExpired() {
  if (!me) return;
  applyMe(null);
  resetAppState();
  showAuth("login", t("auth_session_expired"), false);
}

function onHostedView(view) {
  trackView(view);
  if (view === "admin") renderAdmin();
}

function onHostedLang() {
  syncAuthLang();
  if (!me) return;
  renderQuota();
  if (currentView === "admin") renderAdmin();
}

function cleanView(view) {
  return String(view || "").toLowerCase().replace(/[^a-z0-9_\-:/.]/g, "").slice(0, 80);
}

/* Registro de navegação: dispara e esquece, sem nunca travar a interface. */
function trackView(view, source) {
  if (!hostedMode || !csrfToken) return;
  const body = { view: cleanView(view) };
  if (!body.view) return;
  if (source) body.source = String(source).toLowerCase().slice(0, 80);
  try {
    api("/events/view", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).catch(() => {});
  } catch (error) { /* ignora */ }
}

/* ═══ moldura: conta, cota, menu ═══ */
function applyHostedChrome() {
  document.body.classList.add("is-hosted");
  document.body.classList.remove("auth-gate");
  byId("auth-screen").hidden = true;
  byId("user-box").hidden = false;
  byId("nav-privacy").hidden = false;
  byId("nav-admin-wrap").hidden = !isAdmin();
  renderQuota();
}

function setBar(id, used, max) {
  const bar = byId(id);
  const pct = max > 0 ? Math.min(100, (used / max) * 100) : 0;
  bar.style.width = pct.toFixed(0) + "%";
  bar.classList.toggle("is-full", max > 0 && used >= max);
}

function renderQuota() {
  if (!me || !me.user) return;
  byId("user-name").textContent = me.user.name || me.user.email;
  byId("user-inst").textContent = me.user.institution || me.user.email || "";
  const limits = me.limits || {};
  const usage = me.usage || {};
  const used24 = Number(usage.last_24h || 0);
  const max24 = Number(limits.jobs_per_day || 0);
  const active = Number(usage.active || 0);
  const maxActive = Number(limits.active_per_user || 0);
  byId("quota-jobs").textContent = tf("quota_jobs", { used: used24, max: max24 });
  byId("quota-active").textContent = tf("quota_active", { used: active, max: maxActive });
  setBar("quota-jobs-bar", used24, max24);
  setBar("quota-active-bar", active, maxActive);
}

/* ═══ tela de entrada ═══ */
function syncAuthLang() {
  const btn = byId("auth-lang");
  btn.textContent = currentLang === "pt" ? "EN" : "PT";
  btn.setAttribute("aria-label", currentLang === "pt" ? "Switch to English" : "Mudar para português");
}

function showAuthMsg(id, text) {
  const box = byId(id);
  box.textContent = text || "";
  box.hidden = !text;
}

function setAuthTab(tab) {
  const login = tab !== "signup";
  byId("form-login").hidden = !login;
  byId("form-signup").hidden = login;
  byId("tab-login").setAttribute("aria-selected", String(login));
  byId("tab-signup").setAttribute("aria-selected", String(!login));
  showAuthMsg("login-msg", "");
  showAuthMsg("signup-msg", "");
  const notice = byId("auth-notice");
  notice.hidden = true;
  notice.textContent = "";
}

function showAuth(tab, notice, ok) {
  document.body.classList.add("auth-gate", "is-hosted");
  byId("auth-screen").hidden = false;
  byId("user-box").hidden = true;
  byId("nav-admin-wrap").hidden = true;
  setAuthTab(tab);
  byId("login-password").value = "";
  if (notice) {
    const box = byId("auth-notice");
    box.textContent = notice;
    box.classList.toggle("is-ok", ok !== false);
    box.hidden = false;
  }
  syncAuthLang();
  window.scrollTo({ top: 0 });
  const field = byId(tab === "signup" ? "su-name" : "login-email");
  if (field) field.focus();
}

async function submitLogin(event) {
  event.preventDefault();
  const email = byId("login-email").value.trim();
  const password = byId("login-password").value;
  if (!email || !password) {
    showAuthMsg("login-msg", t("v_required"));
    return;
  }
  const btn = byId("login-submit");
  btn.disabled = true;
  showAuthMsg("login-msg", "");
  try {
    const response = await api("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email, password: password }),
      keepOn401: true
    });
    const raw = await readJson(response);
    if (!response.ok) {
      showAuthMsg("login-msg", detailOf(raw, t("auth_login_fail")));
      return;
    }
    applyMe(raw);
    byId("login-password").value = "";
    await enterApp();
  } catch (error) {
    showAuthMsg("login-msg", t("auth_network"));
  } finally {
    btn.disabled = false;
  }
}

async function submitSignup(event) {
  event.preventDefault();
  const body = {
    name: byId("su-name").value.trim(),
    email: byId("su-email").value.trim(),
    institution: byId("su-institution").value.trim(),
    purpose: byId("su-purpose").value.trim(),
    password: byId("su-password").value,
    consent: byId("su-consent").checked
  };
  const confirmation = byId("su-password2").value;
  let problem = "";
  if (!body.name || !body.email || !body.institution || !body.purpose || !body.password) problem = t("v_required");
  else if (body.password.length < 10) problem = t("v_password_short");
  else if (body.password !== confirmation) problem = t("v_password_match");
  else if (!body.consent) problem = t("v_consent");
  if (problem) {
    showAuthMsg("signup-msg", problem);
    return;
  }
  const btn = byId("signup-submit");
  btn.disabled = true;
  showAuthMsg("signup-msg", "");
  try {
    const response = await api("/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepOn401: true
    });
    const raw = await readJson(response);
    if (!response.ok) {
      showAuthMsg("signup-msg", detailOf(raw, t("auth_signup_fail")));
      return;
    }
    byId("form-signup").reset();
    showAuth("login", detailOf({ detail: raw.message }, t("auth_signup_done")), true);
  } catch (error) {
    showAuthMsg("signup-msg", t("auth_network"));
  } finally {
    btn.disabled = false;
  }
}

async function logout() {
  try {
    await api("/auth/logout", { method: "POST", keepOn401: true });
  } catch (error) { /* a sessão local é descartada de qualquer forma */ }
  applyMe(null);
  resetAppState();
  showAuth("login");
}

function initHosted() {
  document.querySelectorAll("[data-auth-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      setAuthTab(btn.dataset.authTab);
    });
  });
  byId("form-login").addEventListener("submit", submitLogin);
  byId("form-signup").addEventListener("submit", submitSignup);
  byId("btn-logout").addEventListener("click", logout);
  byId("auth-lang").addEventListener("click", () => setLang(currentLang === "pt" ? "en" : "pt"));
  byId("admin-tabs").addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-tab]");
    if (!btn) return;
    adminState.tab = btn.dataset.tab;
    renderAdmin();
  });
  syncAuthLang();
}

/* ═══ drawer: arquivos para baixar ═══ */
function renderHostedFiles(payload) {
  const box = byId("d-downloads");
  const list = byId("d-dl-list");
  const zip = byId("d-zip");
  const note = byId("d-dl-note");
  list.replaceChildren();
  zip.hidden = true;
  note.classList.remove("is-expired");
  if (!payload) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  if (payload.purged) {
    note.textContent = t("dl_expired");
    note.classList.add("is-expired");
    return;
  }
  note.textContent = payload.expires_at ? tf("dl_available_until", { d: fmtDate(payload.expires_at) }) : "";
  const files = Array.isArray(payload.files) ? payload.files : [];
  files.forEach((file) => {
    const url = safeUrl(file.url);
    const label = String(file.name || "");
    list.appendChild(h("li", null,
      url ? h("a", { href: url, download: label, text: label }) : h("span", { text: label }),
      h("span", { class: "sz", text: humanBytes(file.bytes) })
    ));
  });
  const zipUrl = safeUrl(payload.zip_url);
  if (zipUrl && files.length > 0) {
    zip.href = zipUrl;
    zip.hidden = false;
  }
  if (files.length === 0) {
    note.textContent = (note.textContent ? note.textContent + ". " : "") + t("dl_none");
  }
}

/* ═══ administração ═══ */
async function adminGet(path) {
  const response = await api(path);
  if (!response.ok) {
    const raw = await readJson(response);
    if (response.status !== 401) toast(detailOf(raw, t("adm_load_fail")), "fail");
    return null;
  }
  return await response.json();
}

async function adminCall(path, method, payload, okMessage) {
  const options = { method: method };
  if (payload !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }
  const response = await api(path, options);
  const raw = await readJson(response);
  if (!response.ok) {
    if (response.status !== 401) toast(detailOf(raw, t("adm_action_fail")), "fail");
    return null;
  }
  if (okMessage) toast(okMessage, "ok");
  return raw;
}

function adminBody() { return byId("admin-body"); }

function setAdminBody(...nodes) {
  adminBody().replaceChildren(...nodes.flat().filter(Boolean));
}

function renderAdmin() {
  if (!isAdmin()) return;
  document.querySelectorAll("#admin-tabs button").forEach((btn) => {
    btn.setAttribute("aria-selected", String(btn.dataset.tab === adminState.tab));
  });
  adminState.seq += 1;
  setAdminBody(h("div", { class: "adm-empty", text: t("loading") }));
  const run = { overview: adminOverview, users: adminUsers, jobs: adminJobs, events: adminEvents }[adminState.tab];
  if (run) run(adminState.seq);
}

function stale(seq) { return seq !== adminState.seq || currentView !== "admin"; }

function th(key, extra) {
  return h("th", { scope: "col", class: extra || null, text: t(key) });
}

function tableOf(headKeys, rows, opts) {
  const options = opts || {};
  const table = h("table", { class: options.clickable ? null : "static-rows" },
    h("thead", null, h("tr", null, headKeys.map((key) => (typeof key === "string" ? th(key) : key)))),
    h("tbody", null, rows)
  );
  return h("div", { class: "panel" }, h("div", { class: "panel-scroll" }, table));
}

function emptyRow(cols, key) {
  return h("tr", { class: "row-empty" }, h("td", { colspan: String(cols), class: "adm-empty", text: t(key) }));
}

function tile(label, value) {
  return h("div", { class: "tile" },
    h("div", { class: "t-label", text: label }),
    h("div", { class: "t-value", text: fmtInt(value) })
  );
}

function barCell(value, max, alt) {
  const pct = max > 0 ? Math.max(2, (Number(value || 0) / max) * 100) : 0;
  const bar = h("span", { class: "bar" + (alt ? " alt" : "") });
  bar.style.width = pct.toFixed(1) + "%";
  return h("td", { class: "bar-cell" }, Number(value || 0) > 0 ? bar : null);
}

async function adminOverview(seq) {
  const stats = await adminGet("/admin/stats?days=" + adminState.days);
  if (stale(seq)) return;
  if (!stats) {
    setAdminBody(h("div", { class: "adm-empty", text: t("adm_load_fail") }));
    return;
  }
  const queue = stats.queue || {};
  const select = h("select", {
    "aria-label": t("adm_period"),
    on: { change: (event) => { adminState.days = Number(event.target.value); renderAdmin(); } }
  }, [7, 30, 90, 365].map((n) => h("option", {
    value: String(n), selected: n === adminState.days, text: tf("adm_days", { n: n })
  })));
  const toolbar = h("div", { class: "adm-toolbar" }, h("span", { text: t("adm_period") + ":" }), select);

  const kpis = h("div", { class: "adm-kpis" },
    tile(t("adm_k_users_total"), stats.users_total),
    tile(t("adm_k_users_pending"), stats.users_pending),
    tile(t("adm_k_users_approved"), stats.users_approved),
    tile(t("adm_k_active_users"), stats.active_users),
    tile(t("adm_k_distinct_ips"), stats.distinct_ips),
    tile(t("adm_k_logins"), stats.logins),
    tile(t("adm_k_login_failures"), stats.login_failures),
    tile(t("adm_k_jobs"), stats.jobs),
    tile(t("adm_k_jobs_rejected"), stats.jobs_rejected),
    tile(t("adm_k_downloads"), stats.downloads),
    tile(t("adm_k_queued"), queue.queued),
    tile(t("adm_k_running"), queue.running)
  );

  const perDay = Array.isArray(stats.per_day) ? stats.per_day : [];
  const maxViews = Math.max(0, ...perDay.map((row) => Number(row.views || 0)));
  const dayRows = perDay.length === 0 ? [emptyRow(7, "adm_no_rows")] : perDay.map((row) => h("tr", null,
    h("td", { class: "c-id", text: String(row.day) }),
    h("td", { class: "c-num", text: fmtInt(row.users) }),
    h("td", { class: "c-num", text: fmtInt(row.anon_ips) }),
    h("td", { class: "c-num", text: fmtInt(row.views) }),
    barCell(row.views, maxViews),
    h("td", { class: "c-num", text: fmtInt(row.jobs) }),
    h("td", { class: "c-num", text: fmtInt(row.downloads) })
  ));
  const dayTable = tableOf(
    ["adm_th_day", "adm_th_users", "adm_th_anon", "adm_th_views", h("th", { scope: "col" }), "adm_th_jobs", "adm_th_downloads"],
    dayRows
  );

  const sources = Array.isArray(stats.top_sources) ? stats.top_sources : [];
  const maxSource = Math.max(0, ...sources.map((row) => Number(row.n || 0)));
  const sourceRows = sources.length === 0 ? [emptyRow(3, "adm_no_rows")] : sources.map((row) => h("tr", null,
    h("td", { class: "c-id", text: String(row.source) }),
    h("td", { class: "c-num", text: fmtInt(row.n) }),
    barCell(row.n, maxSource, true)
  ));
  const views = Array.isArray(stats.top_views) ? stats.top_views : [];
  const maxView = Math.max(0, ...views.map((row) => Number(row.n || 0)));
  const viewRows = views.length === 0 ? [emptyRow(4, "adm_no_rows")] : views.map((row) => h("tr", null,
    h("td", { class: "c-id", text: String(row.view) }),
    h("td", { class: "c-num", text: fmtInt(row.n) }),
    h("td", { class: "c-num", text: fmtInt(row.users) }),
    barCell(row.n, maxView, true)
  ));

  setAdminBody(
    toolbar,
    kpis,
    h("div", { class: "adm-h", text: t("adm_per_day") }),
    dayTable,
    h("div", { class: "adm-two" },
      h("div", null,
        h("div", { class: "adm-h", text: t("adm_top_sources") }),
        tableOf(["adm_th_source", h("th", { scope: "col", class: "c-num", text: t("adm_th_n") }), h("th", { scope: "col" })], sourceRows)
      ),
      h("div", null,
        h("div", { class: "adm-h", text: t("adm_top_views") }),
        tableOf(["adm_th_view", h("th", { scope: "col", text: t("adm_th_n") }), h("th", { scope: "col", text: t("adm_th_users") }), h("th", { scope: "col" })], viewRows)
      )
    )
  );
}

/* --- usuários --- */
const USER_BADGE = { pending: "pending", approved: "done", rejected: "failed", disabled: "canceled" };

function userBadge(status) {
  return h("span", { class: "badge " + (USER_BADGE[status] || "queued"), text: t("adm_st_" + status) });
}

async function adminUsers(seq) {
  const filter = adminState.userStatus;
  const users = await adminGet("/admin/users" + (filter === "all" ? "" : "?status=" + encodeURIComponent(filter)));
  if (stale(seq)) return;
  if (!users) {
    setAdminBody(h("div", { class: "adm-empty", text: t("adm_load_fail") }));
    return;
  }
  const select = h("select", {
    "aria-label": t("adm_filter_status"),
    on: { change: (event) => { adminState.userStatus = event.target.value; adminState.userId = null; renderAdmin(); } }
  }, ["pending", "approved", "rejected", "disabled", "all"].map((key) => h("option", {
    value: key, selected: key === filter, text: t("adm_f_" + key)
  })));
  const toolbar = h("div", { class: "adm-toolbar" }, h("span", { text: t("adm_filter_status") + ":" }), select);

  const reload = () => { adminState.seq += 1; adminUsers(adminState.seq); };
  const rows = users.length === 0 ? [emptyRow(8, "adm_no_users")] : users.map((user) => {
    const usage = user.usage || {};
    const quota = user.quota_jobs_day ? "/" + user.quota_jobs_day : "";
    const quick = [];
    if (user.status === "pending") {
      quick.push(
        h("button", {
          type: "button", class: "btn btn-sm btn-sq btn-primary", text: t("adm_approve"),
          on: { click: async (event) => { event.stopPropagation(); if (await adminCall("/admin/users/" + user.id + "/status", "POST", { status: "approved" }, t("adm_updated"))) reload(); } }
        }),
        h("button", {
          type: "button", class: "btn btn-sm btn-sq btn-danger", text: t("adm_reject"),
          on: { click: async (event) => { event.stopPropagation(); if (await adminCall("/admin/users/" + user.id + "/status", "POST", { status: "rejected" }, t("adm_updated"))) reload(); } }
        })
      );
    }
    const tr = h("tr", {
      class: user.status === "pending" ? "is-pending" : null,
      "aria-selected": adminState.userId === user.id ? "true" : null,
      on: { click: () => { adminState.userId = user.id; renderUserDetail(users, reload); markSelected(); } },
      "data-user-id": String(user.id)
    },
      h("td", { class: "src-cell" }, h("strong", { text: user.name || "--" }), h("span", { text: user.email })),
      h("td", { text: user.institution || "--" }),
      h("td", null, userBadge(user.status)),
      h("td", null, user.role === "admin" ? h("span", { class: "badge admin", text: t("adm_role_admin") }) : t("adm_role_user")),
      h("td", { class: "c-when", text: fmtDate(user.created_at) }),
      h("td", { class: "c-when", text: user.last_login_at ? fmtDate(user.last_login_at) : "--" }),
      h("td", { class: "c-num", text: String(usage.last_24h || 0) + quota }),
      h("td", null, h("div", { class: "row-actions" }, quick))
    );
    return tr;
  });
  const table = tableOf(
    ["adm_th_user", "adm_th_inst", "adm_th_status", "adm_th_role", "adm_th_created", "adm_th_last", "adm_th_quota", "adm_th_actions"],
    rows, { clickable: users.length > 0 }
  );
  const detail = h("div", { id: "adm-detail" });
  setAdminBody(toolbar, table, detail);
  if (adminState.userId !== null && users.some((u) => u.id === adminState.userId)) {
    renderUserDetail(users, reload);
  } else {
    adminState.userId = null;
    if (users.length > 0) detail.appendChild(h("div", { class: "adm-empty", text: t("adm_pick_user") }));
  }
}

function markSelected() {
  document.querySelectorAll("#admin-body tbody tr[data-user-id]").forEach((tr) => {
    if (Number(tr.dataset.userId) === adminState.userId) tr.setAttribute("aria-selected", "true");
    else tr.removeAttribute("aria-selected");
  });
}

function eventLabel(kind) {
  const key = "ev_" + kind;
  return Object.prototype.hasOwnProperty.call(I18N.pt, key) ? t(key) : String(kind);
}

function metaText(meta) {
  if (!meta || typeof meta !== "object") return "";
  const text = Object.entries(meta).map(([k, v]) => k + "=" + (typeof v === "object" ? JSON.stringify(v) : String(v))).join(" ");
  return text.length > 160 ? text.slice(0, 157) + "…" : text;
}

function timelineItem(ev) {
  const what = [eventLabel(ev.kind)];
  if (ev.view) what.push(ev.view);
  if (ev.source) what.push(ev.source);
  const details = [];
  if (ev.job_id) details.push("job " + String(ev.job_id).slice(0, 10));
  if (ev.ip) details.push(ev.ip);
  const meta = metaText(ev.meta);
  if (meta) details.push(meta);
  return h("li", { class: "k-" + String(ev.kind).replace(/[^a-z_]/g, "") },
    h("span", { class: "tl-when", text: fmtDate(ev.at) }),
    h("span", { class: "tl-what", text: what.join(" · ") }),
    details.length ? h("div", { class: "tl-meta", text: details.join(" · ") }) : null,
    ev.user_agent ? h("div", { class: "tl-meta", text: String(ev.user_agent).slice(0, 110) }) : null
  );
}

function renderUserDetail(users, reload) {
  const user = users.find((u) => u.id === adminState.userId);
  const box = byId("adm-detail");
  if (!user || !box) return;
  const call = (path, method, payload, message) => async () => {
    if (await adminCall(path, method, payload, message)) reload();
  };
  const base = "/admin/users/" + user.id;
  const actions = [];
  if (user.status === "pending") {
    actions.push(
      h("button", { type: "button", class: "btn btn-sm btn-sq btn-primary", text: t("adm_approve"), on: { click: call(base + "/status", "POST", { status: "approved" }, t("adm_updated")) } }),
      h("button", { type: "button", class: "btn btn-sm btn-sq btn-danger", text: t("adm_reject"), on: { click: call(base + "/status", "POST", { status: "rejected" }, t("adm_updated")) } })
    );
  } else if (user.status === "approved") {
    actions.push(h("button", { type: "button", class: "btn btn-sm btn-sq btn-warn", text: t("adm_disable"), on: { click: call(base + "/status", "POST", { status: "disabled" }, t("adm_updated")) } }));
  } else {
    actions.push(h("button", { type: "button", class: "btn btn-sm btn-sq", text: t("adm_reactivate"), on: { click: call(base + "/status", "POST", { status: "approved" }, t("adm_updated")) } }));
  }
  const makeAdmin = user.role !== "admin";
  actions.push(h("button", {
    type: "button", class: "btn btn-sm btn-sq", text: t(makeAdmin ? "adm_make_admin" : "adm_remove_admin"),
    on: { click: call(base + "/role", "POST", { role: makeAdmin ? "admin" : "user" }, t("adm_updated")) }
  }));

  const quotaInput = h("input", {
    type: "number", min: "0", step: "1", placeholder: t("adm_quota_default"),
    "aria-label": t("adm_quota_label"), value: user.quota_jobs_day === null || user.quota_jobs_day === undefined ? null : String(user.quota_jobs_day)
  });
  const quotaBox = h("span", { class: "adm-quota" },
    t("adm_quota_label"), quotaInput,
    h("button", {
      type: "button", class: "btn btn-sm btn-sq", text: t("adm_quota_save"),
      on: {
        click: () => {
          const raw = quotaInput.value.trim();
          const parsed = raw === "" ? null : Math.max(0, Math.floor(Number(raw)));
          if (parsed !== null && !Number.isFinite(parsed)) return;
          call(base + "/quota", "POST", { quota_jobs_day: parsed }, t("adm_updated"))();
        }
      }
    })
  );

  let armed = false;
  let armTimer = null;
  const del = h("button", { type: "button", class: "btn btn-sm btn-sq btn-danger", text: t("adm_delete") });
  del.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      del.textContent = t("adm_delete_confirm");
      armTimer = setTimeout(() => { armed = false; del.textContent = t("adm_delete"); }, 4000);
      return;
    }
    clearTimeout(armTimer);
    if (await adminCall(base, "DELETE", undefined, t("adm_deleted"))) {
      adminState.userId = null;
      reload();
    } else {
      armed = false;
      del.textContent = t("adm_delete");
    }
  });
  actions.push(del);

  const timeline = h("ul", { class: "timeline" }, h("li", { text: t("loading") }));
  box.replaceChildren(h("div", { class: "form-card adm-detail" },
    h("h3", { text: user.name || user.email }),
    h("div", { class: "adm-sub", text: [user.email, user.institution].filter(Boolean).join(" · ") }),
    h("div", { class: "adm-h", text: t("adm_purpose") }),
    h("p", { class: "adm-purpose", text: user.purpose || "--" }),
    h("div", { class: "adm-toolbar" }, actions, quotaBox),
    h("div", { class: "adm-h", text: t("adm_journey") }),
    timeline
  ));
  const wanted = user.id;
  adminGet("/admin/journey?user_id=" + wanted + "&limit=200").then((events) => {
    if (adminState.userId !== wanted || !timeline.isConnected) return;
    if (!events || events.length === 0) {
      timeline.replaceChildren(h("li", { text: t("adm_journey_empty") }));
      return;
    }
    timeline.replaceChildren(...events.map(timelineItem));
  });
}

/* --- coletas --- */
async function adminJobs(seq) {
  const [jobs, users] = await Promise.all([adminGet("/admin/jobs?limit=200"), adminGet("/admin/users")]);
  if (stale(seq)) return;
  if (!jobs) {
    setAdminBody(h("div", { class: "adm-empty", text: t("adm_load_fail") }));
    return;
  }
  const names = {};
  (users || []).forEach((u) => { names[String(u.id)] = u.name || u.email; });
  const rows = jobs.length === 0 ? [emptyRow(8, "adm_no_rows")] : jobs.map((job) => {
    const pct = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const owner = job.owner_id === null || job.owner_id === undefined ? "--" : (names[String(job.owner_id)] || tf("adm_user_n", { n: job.owner_id }));
    const badge = h("td");
    badge.innerHTML = badgeHtml(job.status); // rótulos fixos e já escapados
    const cancel = isTerminalStatus(job.status) ? null : h("button", {
      type: "button", class: "btn btn-sm btn-sq btn-danger", text: t("adm_cancel_job"),
      on: {
        click: async () => {
          if (await adminCall("/admin/jobs/" + encodeURIComponent(job.job_id) + "/cancel", "POST", undefined, t("adm_job_canceled"))) renderAdmin();
        }
      }
    });
    return h("tr", null,
      h("td", { class: "c-id", text: String(job.job_id).slice(0, 10) }),
      h("td", { text: owner }),
      h("td", { class: "src-cell" }, h("strong", { text: sourceTitle(job.source) }), h("span", { text: job.source })),
      badge,
      h("td", { class: "c-num", text: pct.toFixed(0) + "%" }),
      h("td", { class: "c-when", text: fmtDate(job.created_at) }),
      h("td", { class: "c-when", text: job.purged_at ? t("dl_expired") : (job.expires_at ? fmtDate(job.expires_at) : "--") }),
      h("td", null, h("div", { class: "row-actions" }, cancel))
    );
  });
  setAdminBody(tableOf(
    ["th_job", "adm_th_owner", "th_source", "th_status", h("th", { scope: "col", class: "c-num", text: t("th_progress") }), "lbl_created", "adm_th_expires", "adm_th_actions"],
    rows
  ));
}

/* --- eventos --- */
async function adminEvents(seq) {
  const kind = adminState.eventKind;
  const events = await adminGet("/admin/events?limit=200" + (kind ? "&kind=" + encodeURIComponent(kind) : ""));
  if (stale(seq)) return;
  if (!events) {
    setAdminBody(h("div", { class: "adm-empty", text: t("adm_load_fail") }));
    return;
  }
  const select = h("select", {
    "aria-label": t("adm_ev_filter"),
    on: { change: (event) => { adminState.eventKind = event.target.value; renderAdmin(); } }
  }, [h("option", { value: "", selected: !kind, text: t("ev_all") })].concat(
    EVENT_KINDS.map((key) => h("option", { value: key, selected: key === kind, text: eventLabel(key) }))
  ));
  const rows = events.length === 0 ? [emptyRow(7, "adm_no_rows")] : events.map((ev) => h("tr", null,
    h("td", { class: "c-when", text: fmtDate(ev.at) }),
    h("td", { text: eventLabel(ev.kind) }),
    h("td", { class: "c-id", text: [ev.view, ev.source].filter(Boolean).join(" · ") || "--" }),
    h("td", { class: "c-id", text: ev.job_id ? String(ev.job_id).slice(0, 10) : "--" }),
    h("td", { class: "c-id", text: ev.ip || "--" }),
    h("td", { text: ev.user_agent ? String(ev.user_agent).slice(0, 48) : "--" }),
    h("td", { text: metaText(ev.meta) || "--" })
  ));
  setAdminBody(
    h("div", { class: "adm-toolbar" }, h("span", { text: t("adm_ev_filter") + ":" }), select),
    tableOf(["adm_th_when", "adm_th_kind", "adm_th_what", "adm_th_job", "adm_th_ip", "adm_th_agent", h("th", { scope: "col", text: "meta" })], rows)
  );
}
