/* ═══════════ Guaraci — documentação: catálogo das 91 fontes ═══════════ */
(function () {
  "use strict";
  if (typeof GUARACI_CATALOG === "undefined") return;

  const root = document.getElementById("cat-root");
  const sideGroups = document.getElementById("side-groups");
  const countEl = document.getElementById("cat-count");
  const search = document.getElementById("cat-search");
  if (!root) return;

  const PHASE = {
    basico: "coleta (básico)", coleta: "coleta", download: "coleta",
    exportacao: "exportação", export: "exportação", tecnica: "técnico",
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const slug = (k) => "src-" + k.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // agrupa preservando a ordem editorial do catálogo
  const groups = [];
  const byGroup = new Map();
  for (const src of Object.values(GUARACI_CATALOG)) {
    if (!byGroup.has(src.g)) { byGroup.set(src.g, []); groups.push(src.g); }
    byGroup.get(src.g).push(src);
  }

  function paramRow(p) {
    let range = "";
    if (p.allowed) range = p.allowed.map((v) => "<code>" + esc(v) + "</code>").join(" ");
    else if (p.min != null || p.max != null)
      range = (p.min != null ? p.min : "…") + " – " + (p.max != null ? p.max : "…");
    const def = p.default === null || p.default === undefined || p.default === ""
      ? "—" : "<code>" + esc(JSON.stringify(p.default).replace(/^"|"$/g, "")) + "</code>";
    return "<tr><td><code>" + esc(p.name) + "</code></td><td>" + esc(p.type) +
      "</td><td>" + esc(PHASE[p.phase] || p.phase) + "</td><td>" + (p.required ? "sim" : "não") +
      "</td><td>" + def + "</td><td>" + (range || "—") + "</td><td>" + esc(p.desc || "") + "</td></tr>";
  }

  function discoverLine(src) {
    const d = src.discover;
    if (!d || !d.files) return "";
    let extra = "";
    if (d.byGroup && Object.keys(d.byGroup).length > 1) {
      extra = " (" + Object.entries(d.byGroup).map(([g, n]) => g + ": " + n).join(" · ") + ")";
    }
    return '<div class="src-live"><i class="bi bi-broadcast"></i> Conferido ao vivo no FTP do DATASUS: <strong>' +
      d.files + " arquivo" + (d.files > 1 ? "s" : "") + " em " + d.year + "</strong>" + esc(extra) + "</div>";
  }

  function fieldsBlock(src) {
    if (!src.fields.length) {
      return '<p class="src-nofields"><i class="bi bi-info-circle"></i> Campos não amostrados automaticamente' +
        (src.fieldStatus && src.fieldStatus !== "ok" ? " (" + esc(src.fieldStatus) + ")" : "") +
        " — consulte o dicionário da fonte oficial.</p>";
    }
    const LIMIT = 24;
    const all = src.fields.map((f) => '<span class="field-chip">' + esc(f) + "</span>").join("");
    const head = src.fields.slice(0, LIMIT).map((f) => '<span class="field-chip">' + esc(f) + "</span>").join("");
    const sampled = src.rowsSampled ? " — observados em amostra real de " + src.rowsSampled + " registros" : "";
    let html = "<h4>Campos do dado (" + src.fields.length + sampled + ")</h4>";
    if (src.fields.length > LIMIT) {
      html += '<div class="fields-wrap" data-collapsed="1"><div class="fields short">' + head +
        '<span class="field-chip more">+' + (src.fields.length - LIMIT) + "</span></div>" +
        '<div class="fields full" hidden>' + all + "</div>" +
        '<button class="fields-toggle" type="button">Mostrar todos os ' + src.fields.length + " campos</button></div>";
    } else {
      html += '<div class="fields">' + all + "</div>";
    }
    return html;
  }

  function sourceCard(src) {
    const basic = src.params.filter((p) => ["basico", "coleta", "download"].includes(p.phase));
    const other = src.params.filter((p) => !["basico", "coleta", "download"].includes(p.phase));
    const minYear = src.minYear ? '<span class="src-badge"><i class="bi bi-clock-history"></i> desde ' + src.minYear + "</span>" : "";
    return '<article class="src-card" id="' + slug(src.key) + '" data-text="' +
      esc(norm(src.n + " " + src.key + " " + src.d + " " + src.g + " " + src.m + " " + src.fields.join(" "))) + '">' +
      '<header class="src-head"><h3>' + esc(src.n) + "</h3>" +
      '<div class="src-badges"><span class="src-badge mode">' + esc(src.modeLabel) + "</span>" +
      '<span class="src-badge"><i class="bi bi-arrow-repeat"></i> atualização ' + esc(src.cadence) + "</span>" + minYear + "</div></header>" +
      '<p class="src-desc">' + esc(src.d) + " · <em>" + esc(src.m) + "</em></p>" +
      '<div class="src-meta"><span>Identificador: <code>' + esc(src.key) + "</code></span>" +
      '<button class="copy-btn" type="button" data-copy="' + esc(src.key) + '"><i class="bi bi-clipboard"></i> copiar</button></div>' +
      discoverLine(src) +
      "<h4>Parâmetros de coleta (" + basic.length + ")</h4>" +
      '<div class="doc-table-wrap"><table class="doc-table params"><thead><tr><th>Parâmetro</th><th>Tipo</th><th>Fase</th><th>Obrig.</th><th>Padrão</th><th>Valores</th><th>Descrição</th></tr></thead><tbody>' +
      basic.map(paramRow).join("") + "</tbody></table></div>" +
      (other.length ? '<details class="src-adv"><summary>Exportação e opções técnicas (' + other.length + " parâmetros)</summary>" +
        '<div class="doc-table-wrap"><table class="doc-table params"><thead><tr><th>Parâmetro</th><th>Tipo</th><th>Fase</th><th>Obrig.</th><th>Padrão</th><th>Valores</th><th>Descrição</th></tr></thead><tbody>' +
        other.map(paramRow).join("") + "</tbody></table></div></details>" : "") +
      fieldsBlock(src) +
      "<h4>Exemplo na linha de comando</h4>" +
      '<div class="cli-box"><code>' + esc(src.cli) + '</code><button class="copy-btn" type="button" data-copy="' + esc(src.cli) + '"><i class="bi bi-clipboard"></i></button></div>' +
      "</article>";
  }

  // render
  let html = "";
  let sideHtml = '<p class="side-title" style="margin-top:22px;">Fontes por grupo</p>';
  for (const g of groups) {
    const list = byGroup.get(g);
    const gid = "grp-" + norm(g).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    html += '<div class="src-group" id="' + gid + '"><h3 class="src-group-title">' + esc(g) +
      ' <span class="src-group-count">' + list.length + "</span></h3>" + list.map(sourceCard).join("") + "</div>";
    sideHtml += '<a href="#' + gid + '">' + esc(g) + " <span>" + list.length + "</span></a>";
  }
  root.innerHTML = html;
  if (sideGroups) sideGroups.innerHTML = sideHtml;

  const cards = Array.from(root.querySelectorAll(".src-card"));
  const groupsEls = Array.from(root.querySelectorAll(".src-group"));
  const total = cards.length;

  function updateCount(visible) {
    countEl.innerHTML = visible === total
      ? "Documentando <b>" + total + "</b> fontes, todas listadas abaixo por grupo."
      : "Mostrando <b>" + visible + "</b> de <b>" + total + "</b> fontes.";
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
    groupsEls.forEach((g) => {
      g.style.display = g.querySelector('.src-card:not([style*="display: none"])') ? "" : "none";
    });
    updateCount(visible);
  });

  // copiar + expandir campos (delegação)
  root.addEventListener("click", (e) => {
    const copy = e.target.closest(".copy-btn");
    if (copy) {
      navigator.clipboard && navigator.clipboard.writeText(copy.dataset.copy);
      const icon = copy.querySelector("i");
      if (icon) { icon.className = "bi bi-clipboard-check"; setTimeout(() => { icon.className = "bi bi-clipboard"; }, 1400); }
      return;
    }
    const tg = e.target.closest(".fields-toggle");
    if (tg) {
      const wrap = tg.closest(".fields-wrap");
      const collapsed = wrap.dataset.collapsed === "1";
      wrap.dataset.collapsed = collapsed ? "0" : "1";
      wrap.querySelector(".fields.short").hidden = collapsed;
      wrap.querySelector(".fields.full").hidden = !collapsed;
      tg.textContent = collapsed ? "Recolher campos" : "Mostrar todos os " + wrap.querySelectorAll(".fields.full .field-chip").length + " campos";
    }
  });

  // deep-link: rola até a fonte da âncora depois do render
  if (location.hash) {
    const el = document.getElementById(location.hash.slice(1));
    if (el) setTimeout(() => el.scrollIntoView({ block: "start" }), 60);
  }
})();
