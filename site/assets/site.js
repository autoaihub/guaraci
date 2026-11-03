/* Guaraci, site publico: tema, particulas, catalogo, modal e demais interacoes.
   Textos de interface vem de window.GUARACI_UI (gerado por scripts/build_site_pages.py). */
(function () {
  "use strict";
  const UI = window.GUARACI_UI || {};
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;
  const fmt = (s, v) => String(s || "").replace(/\{(\w+)\}/g, (m, k) => (v && k in v ? v[k] : m));
  const t = (k, v) => fmt(UI[k] != null ? UI[k] : k, v);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  /* ── Icones: pecas de azulejo e glifos, vindos de assets/icons.js ── */
  const IC = window.GUARACI_ICONS || { glifos: {}, pecas: {} };
  const gi = (name, size) => '<svg class="mini" viewBox="0 0 48 48"' + (size ? ' width="' + size + '" height="' + size + '"' : "") +
    ' aria-hidden="true">' + (IC.glifos[name] || "") + "</svg>";
  const peca = (name, size, cls) => '<svg class="peca ' + (cls || "") + '" viewBox="0 0 48 48" width="' + size + '" height="' + size +
    '" aria-hidden="true"><rect width="48" height="48" fill="#f3ead6"/>' + (IC.pecas[name] || "") + "</svg>";
  window.GUARACI = { t, fmt, esc, norm, gi, peca };

  /* ── Catalogo: PT por padrao, com a traducao por cima quando existir ── */
  function catalogo() {
    if (typeof GUARACI_CATALOG === "undefined") return null;
    const tr = (typeof GUARACI_I18N !== "undefined" && GUARACI_I18N) || {};
    const out = {};
    for (const k of Object.keys(GUARACI_CATALOG)) out[k] = tr[k] ? Object.assign({}, GUARACI_CATALOG[k], tr[k]) : GUARACI_CATALOG[k];
    return out;
  }
  const CAT = catalogo();
  window.GUARACI.catalogo = CAT;
  const BASES = CAT ? Object.values(CAT) : [];

  /* ── Tema: o script do head ja aplicou a classe; aqui so o seletor ── */
  function marcarTema() {
    const atual = root.classList.contains("tema-claro") ? "claro" : "escuro";
    document.querySelectorAll(".tema-sel button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tema === atual)));
  }
  marcarTema();
  document.querySelectorAll(".tema-sel button").forEach((b) => b.addEventListener("click", () => {
    root.classList.remove("tema-escuro", "tema-claro");
    root.classList.add("tema-" + b.dataset.tema);
    try { localStorage.setItem("guaraci-tema", b.dataset.tema); } catch (e) { /* sem armazenamento */ }
    marcarTema();
    document.dispatchEvent(new Event("tema"));
  }));

  /* ── Navegacao ── */
  const nav = document.querySelector(".nav");
  const bar = document.getElementById("scroll-progress");
  const onScroll = () => {
    if (!bar) return;
    const h = root.scrollHeight - window.innerHeight;
    bar.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + "%";
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", () => {
      const open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    links.addEventListener("click", (e) => { if (e.target.closest("a[href^='#']")) links.classList.remove("open"); });
  }

  /* ── Particulas da abertura: peças de azulejo bem apagadas, fora da area do texto ── */
  const hero = document.querySelector(".hero");
  const cv = hero && hero.querySelector(".particulas");
  if (cv && cv.getContext) {
    const ctx = cv.getContext("2d");
    const rng = (s) => () => { s |= 0; s = s + 0x6D2B79F5 | 0; let x = Math.imul(s ^ s >>> 15, 1 | s); x = x + Math.imul(x ^ x >>> 7, 61 | x) ^ x; return ((x ^ x >>> 14) >>> 0) / 4294967296; };
    const R = rng(11), formas = ["quarto", "tri", "ponto", "meia"];
    let cores, rede, alfa, alfaFio, W, H, dpr, ps = [], zonas = [], vivo = false, raf = 0;
    const lerCores = () => {
      const st = getComputedStyle(cv);
      cores = [st.getPropertyValue("--p1").trim(), st.getPropertyValue("--p2").trim(), st.getPropertyValue("--p3").trim()];
      rede = st.getPropertyValue("--rede").trim();
      alfa = parseFloat(st.getPropertyValue("--alfa")) || .15;
      alfaFio = parseFloat(st.getPropertyValue("--alfa-fio")) || .1;
      ps.forEach((p, i) => { p.c = cores[i % 3]; });
    };
    const medir = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = hero.clientWidth; H = hero.clientHeight;
      cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const b = hero.getBoundingClientRect(); zonas = [];
      hero.querySelectorAll(".selo,h1,.hero-sub").forEach((el) => {
        const r = el.getBoundingClientRect(), m = 24;
        zonas.push([r.left - b.left - m, r.top - b.top - m, r.width + 2 * m, r.height + 2 * m]);
      });
      const n = W < 700 ? 8 : Math.min(18, Math.round(W * H / 40000));
      ps = [];
      for (let i = 0; i < n; i++) ps.push({ x: R() * W, y: R() * H, vx: (R() - .5) * .12, vy: (R() - .5) * .12, a: R() * 6.28, va: (R() - .5) * .003, t: 6 + R() * 6, f: formas[i % 4] });
      lerCores();
    };
    const forma = (p) => {
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.a); ctx.fillStyle = p.c; ctx.globalAlpha = alfa;
      const s = p.t; ctx.beginPath();
      if (p.f === "quarto") { ctx.moveTo(-s / 2, s / 2); ctx.lineTo(-s / 2, -s / 2); ctx.arc(-s / 2, s / 2, s, -Math.PI / 2, 0); ctx.closePath(); }
      else if (p.f === "tri") { ctx.moveTo(-s / 2, -s / 2); ctx.lineTo(s / 2, -s / 2); ctx.lineTo(-s / 2, s / 2); ctx.closePath(); }
      else if (p.f === "meia") { ctx.arc(0, s / 4, s / 2, Math.PI, 0); ctx.closePath(); }
      else ctx.arc(0, 0, s / 4, 0, 6.283);
      ctx.fill(); ctx.restore();
    };
    const quadro = (mover) => {
      ctx.clearRect(0, 0, W, H); ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, H);
      zonas.forEach((z) => ctx.rect(z[0], z[1], z[2], z[3]));
      ctx.clip("evenodd"); ctx.lineWidth = .6;
      for (let i = 0; i < ps.length; i++) {
        const p = ps[i];
        if (mover) {
          p.x += p.vx; p.y += p.vy; p.a += p.va;
          if (p.x < -20) p.x = W + 20; if (p.x > W + 20) p.x = -20;
          if (p.y < -20) p.y = H + 20; if (p.y > H + 20) p.y = -20;
        }
        for (let k = i + 1; k < ps.length; k++) {
          const q = ps[k], dx = p.x - q.x, dy = p.y - q.y, d = dx * dx + dy * dy;
          if (d < 16900) {
            ctx.strokeStyle = "rgba(" + rede + "," + (alfaFio * (1 - d / 16900)).toFixed(3) + ")";
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
          }
        }
      }
      ps.forEach(forma); ctx.restore();
    };
    const laco = () => { if (!vivo) return; quadro(true); raf = requestAnimationFrame(laco); };
    const liga = (v) => {
      if (reduced) return;
      if (v && !vivo) { vivo = true; raf = requestAnimationFrame(laco); }
      else if (!v && vivo) { vivo = false; cancelAnimationFrame(raf); }
    };
    medir(); quadro(false);
    if ("IntersectionObserver" in window) new IntersectionObserver((e) => liga(e[0].isIntersecting && !document.hidden)).observe(hero);
    else liga(true);
    document.addEventListener("visibilitychange", () => liga(!document.hidden && true));
    let to; window.addEventListener("resize", () => { clearTimeout(to); to = setTimeout(() => { medir(); quadro(false); }, 200); });
    document.addEventListener("tema", () => { lerCores(); quadro(false); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { medir(); quadro(false); });
  }

  /* ── Aparecer ao rolar (so com html.js; prazo de seguranca mostra tudo) ── */
  const alvos = document.querySelectorAll(".reveal");
  if (alvos.length) {
    if ("IntersectionObserver" in window && !reduced) {
      const obs = new IntersectionObserver((es) => es.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add("in"); obs.unobserve(e.target); }
      }), { threshold: 0.08 });
      alvos.forEach((el) => obs.observe(el));
      setTimeout(() => root.classList.add("reveal-fim"), 4000);
    } else root.classList.add("reveal-fim");
  }

  /* ── Numeros: o HTML ja traz o valor; aqui vem do catalogo e conta ate ele ── */
  const grupos = new Set(BASES.map((b) => b.g)).size;
  const valores = {
    d: typeof GUARACI_DISTINCT !== "undefined" ? GUARACI_DISTINCT : null,
    e: BASES.length || null,
    g: grupos || null,
    all: BASES.length || null,
  };
  ["saude", "pop", "clima", "san"].forEach((a) => { valores[a] = BASES.length ? BASES.filter((b) => b.area === a).length : null; });
  const contar = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    contar.unobserve(e.target);
    const el = e.target, alvo = parseInt(el.dataset.alvo, 10);
    if (reduced) { el.textContent = alvo; return; }
    let ini = null;
    const passo = (ts) => {
      if (!ini) ini = ts;
      const p = Math.min((ts - ini) / 1300, 1);
      el.textContent = Math.round((0.5 - Math.cos(p * Math.PI) / 2) * alvo);
      if (p < 1) requestAnimationFrame(passo); else el.textContent = alvo;
    };
    requestAnimationFrame(passo);
  }), { threshold: 0.6 });
  document.querySelectorAll("[data-n]").forEach((el) => {
    const v = valores[el.dataset.n];
    if (v != null) el.textContent = v;
    if (el.hasAttribute("data-anim")) {
      el.dataset.alvo = v != null ? v : parseInt(el.textContent, 10);
      contar.observe(el);
    }
  });
  document.querySelectorAll("[data-anim-fixo]").forEach((el) => { el.dataset.alvo = parseInt(el.textContent, 10); contar.observe(el); });

  /* ── Terminais digitados ── */
  function rodarTerminal(body) {
    const nodes = Array.from(body.querySelectorAll("[data-type],[data-print]"));
    if (reduced) { nodes.forEach((n) => { n.style.visibility = "visible"; }); return; }
    const caret = document.createElement("span"); caret.className = "term-caret";
    let i = 0;
    const prox = () => {
      if (i >= nodes.length) { caret.remove(); return; }
      const node = nodes[i++]; node.style.visibility = "visible";
      if (node.hasAttribute("data-print")) { setTimeout(prox, parseInt(node.dataset.print, 10) || 350); return; }
      const full = node.textContent; node.textContent = ""; node.appendChild(caret);
      let c = 0;
      const dig = () => { if (c < full.length) { caret.before(full[c++]); setTimeout(dig, 20 + Math.random() * 30); } else setTimeout(prox, 320); };
      dig();
    };
    prox();
  }
  const termObs = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { rodarTerminal(e.target); termObs.unobserve(e.target); }
  }), { threshold: 0.45 });
  document.querySelectorAll(".term-body").forEach((tb) => {
    if (!tb.querySelector("[data-type],[data-print]")) return;
    tb.querySelectorAll("[data-type],[data-print]").forEach((n) => { n.style.visibility = "hidden"; });
    termObs.observe(tb);
  });

  /* ── FAQ ── */
  document.querySelectorAll(".faq-item").forEach((item) => {
    const q = item.querySelector(".faq-q"), a = item.querySelector(".faq-a");
    q.addEventListener("click", () => {
      const open = item.classList.toggle("open");
      q.setAttribute("aria-expanded", String(open));
      a.style.maxHeight = open ? a.scrollHeight + "px" : 0;
    });
  });

  /* ── Explorador do catalogo ── */
  const grid = document.getElementById("bases-grid");
  if (grid && CAT) {
    const input = document.getElementById("bases-search");
    const countEl = document.getElementById("bases-count");
    const empty = document.getElementById("bases-empty");
    const moreWrap = document.getElementById("bases-more");
    const moreBtn = document.getElementById("bases-more-btn");
    const chips = Array.from(document.querySelectorAll("#bases-chips .filtro"));
    const PAGE = 18;
    let area = "all", query = "", shown = PAGE;
    const PECA = { saude: "saude", pop: "pop", clima: "clima", san: "san" };

    chips.forEach((c) => {
      const em = c.querySelector("em");
      const v = valores[c.dataset.area];
      if (em && v != null) em.textContent = v;
    });

    const matches = (b) => {
      if (area !== "all" && b.area !== area) return false;
      return !query || norm(b.n + " " + b.d + " " + b.g + " " + b.m).includes(query);
    };
    const sameAsLine = (b) => {
      const canon = b.sameAs && CAT[b.sameAs];
      return canon ? '<p class="same">' + gi("sinal", 14) + " " + esc(t("same_as")) + " <b>" + esc(canon.n) + "</b></p>" : "";
    };
    const volumeLine = (b) => b.volume ? '<p class="vol-seal">' + gi("disco", 14) + " " + esc(b.volume) + "</p>" : "";
    const card = (b) =>
      '<article class="cartao" data-key="' + esc(b.key || "") + '" tabindex="0" role="button" aria-label="' + esc(t("details_of", { n: b.n })) + '">' +
      '<div class="c-top">' + peca(PECA[b.area] || "todas", 52, "c-peca") + '<div><span class="c-area">' + esc(t("area_" + b.area)) + "</span><h4>" + esc(b.n) + "</h4></div></div>" +
      '<p class="c-desc">' + esc(b.d) + "</p>" + sameAsLine(b) + volumeLine(b) +
      "<dl><div><dt>" + esc(t("group")) + "</dt><dd>" + esc(b.g) + "</dd></div><div><dt>" + esc(t("maintainer")) + "</dt><dd>" + esc(b.m) + "</dd></div></dl>" +
      '<span class="c-cta">' + esc(t("consult")) + " " + gi("ext", 14) + "</span></article>";

    function render() {
      const list = BASES.filter(matches);
      grid.innerHTML = list.slice(0, shown).map(card).join("");
      const a = Math.min(shown, list.length);
      countEl.innerHTML = fmt(UI.showing, { a: "<b>" + a + "</b>", b: "<b>" + list.length + "</b>" }) +
        (list.length !== BASES.length ? " " + fmt(UI.of_total, { n: BASES.length }) : " · " + fmt(UI.distinct, { n: valores.d }));
      empty.style.display = list.length ? "none" : "block";
      moreWrap.style.display = list.length > shown ? "block" : "none";
    }
    input.addEventListener("input", () => { query = norm(input.value.trim()); shown = PAGE; render(); });
    chips.forEach((c) => c.addEventListener("click", () => {
      chips.forEach((x) => x.setAttribute("aria-pressed", "false"));
      c.setAttribute("aria-pressed", "true");
      area = c.dataset.area; shown = PAGE; render();
    }));
    moreBtn.addEventListener("click", () => { shown += 1000; render(); });
    render();

    /* ── Detalhe da base ── */
    const backdrop = document.getElementById("base-modal");
    const modalBody = document.getElementById("modal-body");
    const slug = (k) => "src-" + k.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");
    let voltarFoco = null;

    function openModal(key) {
      const s = CAT[key];
      if (!s || !backdrop) return;
      const basic = s.params.filter((p) => ["basico", "coleta", "download"].includes(p.phase));
      const fieldsPrev = s.fields.slice(0, 14).map((f) => '<span class="field-chip">' + esc(f) + "</span>").join("");
      const extra = s.fields.length > 14 ? '<span class="field-chip more">+' + (s.fields.length - 14) + "</span>" : "";
      const live = s.discover && s.discover.files
        ? '<div class="src-live">' + gi("sinal", 16) + "<span>" + fmt(t("live_ftp"), { y: "<strong>" + s.discover.year + "</strong>", n: s.discover.files, files: t(s.discover.files > 1 ? "files" : "file") }) + "</span></div>" : "";
      modalBody.innerHTML =
        '<span class="kicker">' + esc(s.g) + "</span>" +
        '<h3 id="modal-title">' + esc(s.n) + "</h3>" +
        '<p class="src-desc">' + esc(s.d) + " · <em>" + esc(s.m) + "</em></p>" +
        (s.sameAs && CAT[s.sameAs]
          ? '<p class="same-as">' + gi("sinal", 16) + "<span>" + esc(t("same_long")) + " <b>" + esc(CAT[s.sameAs].n) +
            "</b> (<code>" + esc(s.sameAs) + "</code>), " + esc(t("other_path")) + ". " + esc(s.sameAsNote || "") + "</span></p>" : "") +
        '<div class="src-badges" style="margin-bottom:14px"><span class="src-badge mode">' + esc(s.modeLabel) + "</span>" +
        '<span class="src-badge">' + gi("sol", 14) + " " + esc(t("update")) + " " + esc(s.cadence) + "</span>" +
        (s.minYear ? '<span class="src-badge">' + gi("relogio", 14) + " " + esc(t("since")) + " " + s.minYear + "</span>" : "") + "</div>" +
        volumeLine(s) +
        '<div class="src-meta">' + esc(t("identifier")) + ": <code>" + esc(s.key) + "</code></div>" + live +
        "<h4>" + fmt(t("params_title"), { b: basic.length, a: s.params.length - basic.length }) + "</h4>" +
        '<div class="fields">' + basic.map((p) => '<span class="field-chip">' + esc(p.name) + "</span>").join("") + "</div>" +
        (s.fields.length ? "<h4>" + fmt(t("fields_title"), { n: s.fields.length }) + "</h4><div class='fields'>" + fieldsPrev + extra + "</div>" : "") +
        "<h4>" + esc(t("cli_title")) + "</h4>" +
        '<div class="term"><div class="term-bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="title">terminal: ' + esc(s.key) + "</span></div>" +
        '<div class="term-body"><div><span class="ps1">&gt;</span> <span class="cmd">' + esc(s.cli) + "</span></div></div></div>" +
        '<a class="bt bt-sol" style="margin-top:22px" href="docs.html#' + slug(s.key) + '">' + esc(t("full_docs")) + " " + gi("seta", 16) + "</a>";
      voltarFoco = document.activeElement;
      backdrop.hidden = false;
      document.body.style.overflow = "hidden";
      const fechar = backdrop.querySelector(".modal-close");
      if (fechar) fechar.focus();
    }
    function closeModal() {
      if (!backdrop || backdrop.hidden) return;
      backdrop.hidden = true;
      document.body.style.overflow = "";
      if (voltarFoco && voltarFoco.focus) voltarFoco.focus();
    }
    grid.addEventListener("click", (e) => { const c = e.target.closest(".cartao"); if (c && c.dataset.key) openModal(c.dataset.key); });
    grid.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const c = e.target.closest(".cartao");
      if (c && c.dataset.key) { e.preventDefault(); openModal(c.dataset.key); }
    });
    if (backdrop) {
      backdrop.addEventListener("click", (e) => { if (e.target === backdrop || e.target.closest(".modal-close")) closeModal(); });
      document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
    }
  }

  /* ── Video: o player do YouTube so carrega no clique ── */
  document.querySelectorAll(".video-play[data-yt]").forEach((btn) => btn.addEventListener("click", () => {
    const f = document.createElement("iframe");
    f.src = "https://www.youtube-nocookie.com/embed/" + btn.dataset.yt + "?autoplay=1&rel=0";
    f.title = t("video_title");
    f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    f.allowFullscreen = true;
    btn.replaceWith(f);
  }));
})();
