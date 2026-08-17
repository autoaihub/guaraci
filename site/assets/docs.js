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
      let note = "Consulte o dicionário da fonte oficial.";
      if (src.fieldStatus === "needs_credential") note = "Exige credencial de acesso configurada em variável de ambiente.";
      else if (src.fieldStatus === "error") note = "Endpoint indisponível no momento do amostragem (HTTP 404/500).";
      else if (src.fieldStatus === "empty") note = "Sem registros retornados na janela curta de amostragem.";
      else if (src.fieldStatus === "filters_only") note = "Endpoint parametrizado por sub-recurso.";
      return '<div class="src-nofields"><i class="bi bi-info-circle"></i> <strong>Colunas brutas não amostradas:</strong> ' + esc(note) + '</div>';
    }

    const csvText = src.fields.join(", ");
    const pyText = "[" + src.fields.map(f => "'" + f + "'").join(", ") + "]";
    const sampled = src.rowsSampled ? " — " + src.fields.length + " colunas brutas observadas em amostra real (" + src.rowsSampled + " registros)" : " — " + src.fields.length + " colunas brutas";
    const LIMIT = 24;
    const allChips = src.fields.map((f) => '<span class="field-chip" data-field="' + esc(norm(f)) + '"><code>' + esc(f) + "</code></span>").join("");
    const headChips = src.fields.slice(0, LIMIT).map((f) => '<span class="field-chip" data-field="' + esc(norm(f)) + '"><code>' + esc(f) + "</code></span>").join("");

    let html = '<div class="src-fields-block">' +
      '<div class="src-fields-header">' +
      '<h4>Campos / Colunas da base <span class="field-count-badge">' + src.fields.length + ' colunas</span></h4>' +
      '<div class="field-actions">' +
      '<button class="copy-btn copy-csv-btn" type="button" data-copy="' + esc(csvText) + '" title="Copiar nomes de colunas separados por vírgula"><i class="bi bi-file-earmark-spreadsheet"></i> Copiar colunas (CSV)</button>' +
      '<button class="copy-btn copy-py-btn" type="button" data-copy="' + esc(pyText) + '" title="Copiar lista de colunas formatada para Python/Pandas/Polars"><i class="bi bi-code-square"></i> Copiar lista (Python)</button>' +
      '</div></div>' +
      '<p class="src-fields-note"><i class="bi bi-table"></i> Nomes crus das colunas conforme retornado pela fonte original' + esc(sampled) + '.</p>';

    if (src.fields.length > 10) {
      html += '<div class="field-search-wrap"><i class="bi bi-search"></i><input type="search" class="field-filter-input" placeholder="Buscar coluna nesta base... (ex: sexo, dt_, uf, id)" aria-label="Filtrar colunas nesta base"></div>';
    }

    if (src.fields.length > LIMIT) {
      html += '<div class="fields-wrap" data-collapsed="1">' +
        '<div class="fields short">' + headChips + '<span class="field-chip more">+' + (src.fields.length - LIMIT) + "</span></div>" +
        '<div class="fields full" hidden>' + allChips + "</div>" +
        '<button class="fields-toggle" type="button"><i class="bi bi-chevron-down"></i> Mostrar todas as ' + src.fields.length + " colunas</button></div>";
    } else {
      html += '<div class="fields full">' + allChips + "</div>";
    }
    html += '</div>';
    return html;
  }

  function sourceCard(src) {
    const basic = src.params.filter((p) => ["basico", "coleta", "download"].includes(p.phase));
    const other = src.params.filter((p) => !["basico", "coleta", "download"].includes(p.phase));
    const minYearStr = src.minYear ? "desde " + src.minYear : "período completo";
    const currentYear = new Date().getFullYear();
    const periodStr = src.minYear ? src.minYear + " a " + currentYear + " (corrente)" : "disponibilidade nativa da fonte";

    return '<article class="src-card" id="' + slug(src.key) + '" data-text="' +
      esc(norm(src.n + " " + src.key + " " + src.d + " " + src.g + " " + src.m + " " + src.fields.join(" "))) + '">' +
      '<header class="src-head" role="button" tabindex="0" aria-expanded="false"><h3>' + esc(src.n) + "</h3>" +
      '<div class="src-badges"><span class="src-badge mode">' + esc(src.modeLabel) + "</span>" +
      '<span class="src-badge"><i class="bi bi-arrow-repeat"></i> atualização ' + esc(src.cadence) + "</span>" +
      '<span class="src-badge year-badge"><i class="bi bi-calendar3"></i> ' + esc(minYearStr) + "</span>" +
      '<span class="src-chevron"><i class="bi bi-chevron-down"></i></span></div></header>' +
      '<p class="src-desc">' + esc(src.d) + " · <em>" + esc(src.m) + "</em></p>" +
      '<div class="src-body">' +
      '<div class="src-meta-panel">' +
      '<div class="meta-item"><span class="meta-lbl">Identificador CLI / API:</span> <code>' + esc(src.key) + '</code> <button class="copy-btn" type="button" data-copy="' + esc(src.key) + '"><i class="bi bi-clipboard"></i> copiar</button></div>' +
      '<div class="meta-item"><span class="meta-lbl">Cobertura Histórica:</span> <strong>' + esc(periodStr) + '</strong></div>' +
      '<div class="meta-item"><span class="meta-lbl">Estrutura de Saída:</span> <strong>' + (src.fields.length ? src.fields.length + ' colunas brutas' : 'sem amostragem') + '</strong></div>' +
      '</div>' +

      discoverLine(src) +
      "<h4>Parâmetros de coleta (" + basic.length + ")</h4>" +
      '<div class="doc-table-wrap"><table class="doc-table params"><thead><tr><th>Parâmetro</th><th>Tipo</th><th>Fase</th><th>Obrig.</th><th>Padrão</th><th>Valores</th><th>Descrição</th></tr></thead><tbody>' +
      basic.map(paramRow).join("") + "</tbody></table></div>" +
      (other.length ? '<details class="src-adv"><summary>Exportação e opções técnicas (' + other.length + " parâmetros)</summary>" +
        '<div class="doc-table-wrap"><table class="doc-table params"><thead><tr><th>Parâmetro</th><th>Tipo</th><th>Fase</th><th>Obrig.</th><th>Padrão</th><th>Valores</th><th>Descrição</th></tr></thead><tbody>' +
        other.map(paramRow).join("") + "</tbody></table></div></details>" : "") +
      fieldsBlock(src) +
      "<h4>Exemplo na linha de comando</h4>" +
      '<div class="term cli-term"><div class="term-bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="title">terminal — ' + esc(src.key) + '</span>' +
      '<button class="copy-btn term-copy" type="button" data-copy="' + esc(src.cli) + '"><i class="bi bi-clipboard"></i> copiar</button></div>' +
      '<div class="term-body"><div><span class="ps1">&gt;</span> <span class="cmd">' + esc(src.cli) + "</span></div></div></div>" +
      "</div></article>";
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

  /* ── Cards recolhidos por padrão; expandem sob demanda ── */
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
    if (head) {
      e.preventDefault();
      const card = head.closest(".src-card");
      setOpen(card, !card.classList.contains("open"));
    }
  });
  const btnExpand = document.getElementById("cat-expand");
  const btnCollapse = document.getElementById("cat-collapse");
  if (btnExpand) btnExpand.addEventListener("click", () =>
    cards.forEach((c) => { if (c.style.display !== "none") setOpen(c, true); }));
  if (btnCollapse) btnCollapse.addEventListener("click", () =>
    cards.forEach((c) => setOpen(c, false)));

  function updateCount(visible) {
    countEl.innerHTML = visible === total
      ? "Documentando <b>" + total + "</b> fontes com parâmetros e colunas brutas mapeadas."
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

  // copiar + expandir campos + busca por coluna (delegação)
  root.addEventListener("click", (e) => {
    const copy = e.target.closest(".copy-btn");
    if (copy) {
      if (navigator.clipboard && copy.dataset.copy) {
        navigator.clipboard.writeText(copy.dataset.copy);
      }
      const icon = copy.querySelector("i");
      if (icon) {
        const prev = icon.className;
        icon.className = "bi bi-clipboard-check";
        setTimeout(() => { icon.className = prev; }, 1400);
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
      tg.innerHTML = collapsed ? '<i class="bi bi-chevron-up"></i> Recolher campos' : '<i class="bi bi-chevron-down"></i> Mostrar todas as ' + wrap.querySelectorAll(".fields.full .field-chip").length + " colunas";
    }
  });

  root.addEventListener("input", (e) => {
    const input = e.target.closest(".field-filter-input");
    if (input) {
      const q = norm(input.value.trim());
      const block = input.closest(".src-fields-block");
      const chips = block.querySelectorAll(".fields.full .field-chip");
      const wrap = block.querySelector(".fields-wrap");
      if (wrap && q) {
        wrap.querySelector(".fields.short").hidden = true;
        wrap.querySelector(".fields.full").hidden = false;
        const tg = wrap.querySelector(".fields-toggle");
        if (tg) tg.style.display = "none";
      } else if (wrap && !q) {
        const collapsed = wrap.dataset.collapsed === "1";
        wrap.querySelector(".fields.short").hidden = !collapsed;
        wrap.querySelector(".fields.full").hidden = collapsed;
        const tg = wrap.querySelector(".fields-toggle");
        if (tg) tg.style.display = "";
      }
      chips.forEach((c) => {
        const name = c.dataset.field || "";
        c.style.display = !q || name.includes(q) ? "" : "none";
      });
    }
  });

  // deep-link: expande e rola até a fonte da âncora (no load e em navegação interna)
  function goToHash() {
    if (!location.hash) return;
    const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (!el) return;
    if (el.classList.contains("src-card")) setOpen(el, true);
    // instantâneo e tardio: vence a disputa com o scroll nativo de fragmento
    setTimeout(() => el.scrollIntoView({ behavior: "instant", block: "start" }), 250);
  }
  window.addEventListener("hashchange", goToHash);
  goToHash();
})();

