/* Guaraci, documentacao: catalogo detalhado das fontes.
   Textos vem de window.GUARACI_UI; o catalogo traduzido (GUARACI_I18N) e mesclado em site.js. */
(function () {
  "use strict";
  const G = window.GUARACI;
  if (!G || !G.catalogo) return;
  const CAT = G.catalogo, t = G.t, fmt = G.fmt, gi = G.gi, esc = G.esc, norm = G.norm;

  const root = document.getElementById("cat-root");
  const sideGroups = document.getElementById("side-groups");
  const countEl = document.getElementById("cat-count");
  const search = document.getElementById("cat-search");
  if (!root) return;

  const PHASE = {
    basico: t("phase_basic"), coleta: t("phase_collect"), download: t("phase_collect"),
    exportacao: t("phase_export"), export: t("phase_export"), tecnica: t("phase_tech"),
  };
  const slug = (k) => "src-" + k.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");

  // agrupa preservando a ordem editorial do catalogo
  const groups = [];
  const byGroup = new Map();
  for (const src of Object.values(CAT)) {
    if (!byGroup.has(src.g)) { byGroup.set(src.g, []); groups.push(src.g); }
    byGroup.get(src.g).push(src);
  }

  function paramRow(p) {
    let range = "";
    if (p.allowed) range = p.allowed.map((v) => "<code>" + esc(v) + "</code>").join(" ");
    else if (p.min != null || p.max != null)
      range = (p.min != null ? p.min : "...") + "-" + (p.max != null ? p.max : "...");
    const def = p.default === null || p.default === undefined || p.default === ""
      ? "-" : "<code>" + esc(JSON.stringify(p.default).replace(/^"|"$/g, "")) + "</code>";
    return "<tr><td><code>" + esc(p.name) + "</code></td><td>" + esc(p.type) +
      "</td><td>" + esc(PHASE[p.phase] || p.phase) + "</td><td>" + (p.required ? t("yes") : t("no")) +
      "</td><td>" + def + "</td><td>" + (range || "-") + "</td><td>" + esc(p.desc || "") + "</td></tr>";
  }

  function paramTable(list) {
    return '<div class="doc-table-wrap"><table class="doc-table params"><thead><tr><th>' + esc(t("th_param")) + "</th><th>" + esc(t("th_type")) +
      "</th><th>" + esc(t("th_phase")) + "</th><th>" + esc(t("th_required")) + "</th><th>" + esc(t("th_default")) + "</th><th>" + esc(t("th_values")) +
      "</th><th>" + esc(t("th_desc")) + "</th></tr></thead><tbody>" + list.map(paramRow).join("") + "</tbody></table></div>";
  }

  function discoverLine(src) {
    const d = src.discover;
    if (!d || !d.files) return "";
    let extra = "";
    if (d.byGroup && Object.keys(d.byGroup).length > 1)
      extra = " (" + Object.entries(d.byGroup).map(([g, n]) => g + ": " + n).join(" · ") + ")";
    return '<div class="src-live">' + gi("sinal", 16) + "<span>" +
      fmt(t("live_ftp_docs"), { y: "<strong>" + d.year + "</strong>", n: d.files, files: t(d.files > 1 ? "files" : "file") }) + esc(extra) + "</span></div>";
  }

  function fieldsBlock(src) {
    if (!src.fields.length) {
      let note = t("nofields_default");
      if (src.fieldStatus === "needs_credential") note = t("nofields_cred");
      else if (src.fieldStatus === "error") note = t("nofields_error");
      else if (src.fieldStatus === "empty") note = t("nofields_empty");
      else if (src.fieldStatus === "filters_only") note = t("nofields_filters");
      return '<div class="src-nofields">' + gi("info", 18) + "<span><strong>" + esc(t("nofields_title")) + "</strong> " + esc(note) + "</span></div>";
    }
    const csvText = src.fields.join(", ");
    const pyText = "[" + src.fields.map((f) => "'" + f + "'").join(", ") + "]";
    const sampled = src.rowsSampled
      ? fmt(t("sampled_rows"), { n: src.fields.length, r: src.rowsSampled }) : fmt(t("sampled_plain"), { n: src.fields.length });
    const LIMIT = 24;
    const chip = (f) => '<span class="field-chip" data-field="' + esc(norm(f)) + '"><code>' + esc(f) + "</code></span>";
    let html = '<div class="src-fields-block"><div class="src-fields-header"><h4>' + esc(t("fields_block")) +
      ' <span class="field-count-badge">' + fmt(t("n_columns"), { n: src.fields.length }) + "</span></h4>" +
      '<div class="field-actions">' +
      '<button class="copy-btn" type="button" data-copy="' + esc(csvText) + '" title="' + esc(t("copy_csv_title")) + '">' + gi("tabela", 14) + " " + esc(t("copy_csv")) + "</button>" +
      '<button class="copy-btn" type="button" data-copy="' + esc(pyText) + '" title="' + esc(t("copy_py_title")) + '">' + gi("codigo", 14) + " " + esc(t("copy_py")) + "</button>" +
      '</div></div><p class="src-fields-note">' + gi("tabela", 14) + " <span>" + esc(t("raw_names")) + esc(sampled) + ".</span></p>";
    if (src.fields.length > 10)
      html += '<div class="field-search-wrap">' + gi("busca", 16) + '<input type="search" class="field-filter-input" placeholder="' + esc(t("field_ph")) + '" aria-label="' + esc(t("field_label")) + '"></div>';
    if (src.fields.length > LIMIT) {
      html += '<div class="fields-wrap" data-collapsed="1"><div class="fields short">' + src.fields.slice(0, LIMIT).map(chip).join("") +
        '<span class="field-chip more">+' + (src.fields.length - LIMIT) + '</span></div><div class="fields full" hidden>' + src.fields.map(chip).join("") +
        '</div><button class="fields-toggle" type="button">' + gi("baixo", 14) + " " + fmt(t("show_all_cols"), { n: src.fields.length }) + "</button></div>";
    } else html += '<div class="fields full">' + src.fields.map(chip).join("") + "</div>";
    return html + "</div>";
  }

  function sourceCard(src) {
    const basic = src.params.filter((p) => ["basico", "coleta", "download"].includes(p.phase));
    const other = src.params.filter((p) => !["basico", "coleta", "download"].includes(p.phase));
    const minYearStr = src.minYear ? t("since") + " " + src.minYear : t("full_period");
    // O fim da cobertura so e afirmado quando um discover real confirmou arquivos naquele ano.
    const lastYear = src.discover && src.discover.files ? src.discover.year : null;
    let periodStr = t("native_avail");
    if (src.minYear && lastYear) periodStr = fmt(t("period_range"), { a: src.minYear, b: lastYear });
    else if (src.minYear) periodStr = t("since") + " " + src.minYear;

    return '<article class="src-card" id="' + slug(src.key) + '" data-text="' +
      esc(norm(src.n + " " + src.key + " " + src.d + " " + src.g + " " + src.m + " " + src.fields.join(" "))) + '">' +
      '<header class="src-head" role="button" tabindex="0" aria-expanded="false"><h3>' + esc(src.n) + "</h3>" +
      '<div class="src-badges"><span class="src-badge mode">' + esc(src.modeLabel) + "</span>" +
      '<span class="src-badge">' + gi("sol", 14) + " " + esc(t("update")) + " " + esc(src.cadence) + "</span>" +
      '<span class="src-badge">' + gi("calendario", 14) + " " + esc(minYearStr) + "</span>" +
      '<span class="src-chevron">' + gi("baixo", 16) + "</span></div></header>" +
      '<p class="src-desc">' + esc(src.d) + " · <em>" + esc(src.m) + "</em></p>" +
      (src.volume ? '<p class="vol-seal">' + gi("disco", 14) + " " + esc(src.volume) + "</p>" : "") +
      (src.sameAs && CAT[src.sameAs]
        ? '<p class="same-as">' + gi("sinal", 16) + "<span>" + esc(t("same_long")) + ' <a href="#' + slug(src.sameAs) + '">' +
          esc(CAT[src.sameAs].n) + "</a>, " + esc(t("other_path")) + ". " + esc(src.sameAsNote || "") + "</span></p>" : "") +
      '<div class="src-body"><div class="src-meta-panel">' +
      '<div><span class="meta-lbl">' + esc(t("meta_id")) + "</span> <code>" + esc(src.key) + '</code> <button class="copy-btn" type="button" data-copy="' + esc(src.key) + '">' + gi("copiar", 14) + " " + esc(t("copy")) + "</button></div>" +
      '<div><span class="meta-lbl">' + esc(t("meta_coverage")) + "</span> <strong>" + esc(periodStr) + "</strong></div>" +
      '<div><span class="meta-lbl">' + esc(t("meta_output")) + "</span> <strong>" + (src.fields.length ? fmt(t("n_raw_cols"), { n: src.fields.length }) : esc(t("no_sampling"))) + "</strong></div>" +
      "</div>" + discoverLine(src) +
      "<h4>" + fmt(t("collect_params"), { n: basic.length }) + "</h4>" + paramTable(basic) +
      (other.length ? '<details class="src-adv"><summary>' + fmt(t("export_opts"), { n: other.length }) + "</summary>" + paramTable(other) + "</details>" : "") +
      fieldsBlock(src) +
      "<h4>" + esc(t("cli_example")) + "</h4>" +
      '<div class="term cli-term"><div class="term-bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="title">terminal: ' + esc(src.key) + "</span>" +
      '<button class="copy-btn term-copy" type="button" data-copy="' + esc(src.cli) + '">' + gi("copiar", 14) + " " + esc(t("copy")) + "</button></div>" +
      '<div class="term-body"><div><span class="ps1">&gt;</span> <span class="cmd">' + esc(src.cli) + "</span></div></div></div>" +
      "</div></article>";
  }

  let html = "";
  let sideHtml = '<p class="side-title" style="margin-top:22px">' + esc(t("sources_by_group")) + "</p>";
  for (const g of groups) {
    const list = byGroup.get(g);
    const gid = "grp-" + norm(g).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    html += '<div class="src-group" id="' + gid + '"><h3 class="src-group-title">' + esc(g) +
      ' <span class="src-group-count">' + list.length + "</span></h3>" + list.map(sourceCard).join("") + "</div>";
    sideHtml += '<a href="#' + gid + '"><span class="n">' + list.length + "</span>" + esc(g) + "</a>";
  }
  root.innerHTML = html;
  if (sideGroups) sideGroups.innerHTML = sideHtml;

  const cards = Array.from(root.querySelectorAll(".src-card"));
  const groupsEls = Array.from(root.querySelectorAll(".src-group"));
  const total = cards.length;

  /* ── Cards recolhidos por padrao; expandem sob demanda ── */
  function setOpen(card, open) {
    card.classList.toggle("open", open);
    const head = card.querySelector(".src-head");
    if (head) head.setAttribute("aria-expanded", String(open));
  }
  root.addEventListener("click", (e) => {
    const head = e.target.closest(".src-head");
    if (head && !e.target.closest(".copy-btn")) {
      const card = head.closest(".src-card");
      setOpen(card, !card.classList.contains("open"));
    }
  });
  root.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const head = e.target.closest(".src-head");
    if (head) { e.preventDefault(); const card = head.closest(".src-card"); setOpen(card, !card.classList.contains("open")); }
  });
  const btnExpand = document.getElementById("cat-expand");
  const btnCollapse = document.getElementById("cat-collapse");
  if (btnExpand) btnExpand.addEventListener("click", () => cards.forEach((c) => { if (c.style.display !== "none") setOpen(c, true); }));
  if (btnCollapse) btnCollapse.addEventListener("click", () => cards.forEach((c) => setOpen(c, false)));

  function updateCount(visible) {
    countEl.innerHTML = visible === total
      ? fmt(t("documenting"), { n: "<b>" + total + "</b>" })
      : fmt(t("showing_src"), { a: "<b>" + visible + "</b>", b: "<b>" + total + "</b>" });
  }
  updateCount(total);

  if (search) search.addEventListener("input", () => {
    const q = norm(search.value.trim());
    let visible = 0;
    cards.forEach((c) => {
      const hit = !q || c.dataset.text.includes(q);
      c.style.display = hit ? "" : "none";
      if (hit) visible++;
    });
    groupsEls.forEach((g) => { g.style.display = g.querySelector('.src-card:not([style*="display: none"])') ? "" : "none"; });
    updateCount(visible);
  });

  // copiar, expandir campos e busca por coluna (delegacao)
  root.addEventListener("click", (e) => {
    const copy = e.target.closest(".copy-btn");
    if (copy) {
      if (navigator.clipboard && copy.dataset.copy) navigator.clipboard.writeText(copy.dataset.copy);
      const svg = copy.querySelector("svg");
      if (svg) {
        const prev = svg.innerHTML;
        svg.innerHTML = (window.GUARACI_ICONS.glifos.copiado || prev);
        setTimeout(() => { svg.innerHTML = prev; }, 1400);
      }
      return;
    }
    const tg = e.target.closest(".fields-toggle");
    if (tg) {
      const wrap = tg.closest(".fields-wrap");
      const collapsed = wrap.dataset.collapsed === "1";
      wrap.dataset.collapsed = collapsed ? "0" : "1";
      wrap.querySelector(".fields.short").hidden = collapsed;
      wrap.querySelector(".fields.full").hidden = !collapsed;
      const n = wrap.querySelectorAll(".fields.full .field-chip").length;
      tg.innerHTML = collapsed ? gi("cima", 14) + " " + esc(t("collapse_fields")) : gi("baixo", 14) + " " + fmt(t("show_all_cols"), { n });
    }
  });

  root.addEventListener("input", (e) => {
    const input = e.target.closest(".field-filter-input");
    if (!input) return;
    const q = norm(input.value.trim());
    const block = input.closest(".src-fields-block");
    const chips = block.querySelectorAll(".fields.full .field-chip");
    const wrap = block.querySelector(".fields-wrap");
    if (wrap && q) {
      wrap.querySelector(".fields.short").hidden = true;
      wrap.querySelector(".fields.full").hidden = false;
      const tg = wrap.querySelector(".fields-toggle"); if (tg) tg.style.display = "none";
    } else if (wrap && !q) {
      const collapsed = wrap.dataset.collapsed === "1";
      wrap.querySelector(".fields.short").hidden = !collapsed;
      wrap.querySelector(".fields.full").hidden = collapsed;
      const tg = wrap.querySelector(".fields-toggle"); if (tg) tg.style.display = "";
    }
    chips.forEach((c) => { c.style.display = !q || (c.dataset.field || "").includes(q) ? "" : "none"; });
  });

  // deep-link: expande e rola ate a fonte da ancora
  function goToHash() {
    if (!location.hash) return;
    const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (!el) return;
    if (el.classList.contains("src-card")) setOpen(el, true);
    setTimeout(() => el.scrollIntoView({ behavior: "instant", block: "start" }), 250);
  }
  window.addEventListener("hashchange", goToHash);
  goToHash();
})();
