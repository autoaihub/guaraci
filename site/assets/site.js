/* ═══════════ Guaraci — interações ═══════════ */
(function () {
  "use strict";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Navbar: sombra, progresso e menu mobile ── */
  const nav = document.querySelector(".nav");
  const bar = document.getElementById("scroll-progress");
  const onScroll = () => {
    nav.classList.toggle("scrolled", window.scrollY > 30);
    const h = document.documentElement.scrollHeight - window.innerHeight;
    bar.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + "%";
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  toggle.addEventListener("click", () => links.classList.toggle("open"));
  links.addEventListener("click", (e) => { if (e.target.tagName === "A") links.classList.remove("open"); });

  /* ── Hero: rede de dados em canvas ── */
  const canvas = document.getElementById("hero-canvas");
  if (canvas && !reduced) {
    const ctx = canvas.getContext("2d");
    let W, H, pts = [], raf;
    const DENSITY = 1 / 16000;

    function resize() {
      W = canvas.width = canvas.offsetWidth * devicePixelRatio;
      H = canvas.height = canvas.offsetHeight * devicePixelRatio;
      const n = Math.min(110, Math.floor((canvas.offsetWidth * canvas.offsetHeight) * DENSITY));
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - .5) * .18 * devicePixelRatio,
        vy: (Math.random() - .5) * .18 * devicePixelRatio,
        r: (Math.random() * 1.6 + .8) * devicePixelRatio,
        warm: Math.random() < .3
      }));
    }

    function tick() {
      ctx.clearRect(0, 0, W, H);
      const linkDist = 130 * devicePixelRatio;
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > W) p.vx *= -1;
        if (p.y < 0 || p.y > H) p.vy *= -1;
        for (let j = i + 1; j < pts.length; j++) {
          const q = pts[j], dx = p.x - q.x, dy = p.y - q.y, d = Math.hypot(dx, dy);
          if (d < linkDist) {
            ctx.strokeStyle = "rgba(20,184,166," + (0.14 * (1 - d / linkDist)).toFixed(3) + ")";
            ctx.lineWidth = devicePixelRatio * .7;
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
          }
        }
      }
      for (const p of pts) {
        ctx.fillStyle = p.warm ? "rgba(247,164,29,.75)" : "rgba(20,184,166,.65)";
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(tick);
    }

    resize();
    window.addEventListener("resize", resize);
    // pausa quando o hero sai da tela
    new IntersectionObserver((en) => {
      if (en[0].isIntersecting) { if (!raf) raf = requestAnimationFrame(tick); }
      else { cancelAnimationFrame(raf); raf = null; }
    }).observe(canvas);
  }

  /* ── Reveal on scroll ── */
  const revealObs = new IntersectionObserver((entries) => {
    entries.forEach((e, i) => {
      if (e.isIntersecting) {
        e.target.style.transitionDelay = Math.min(e.target.dataset.delay || 0, 400) + "ms";
        e.target.classList.add("in");
        revealObs.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll(".reveal").forEach((el) => revealObs.observe(el));

  /* ── Contadores animados ── */
  const countObs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const el = e.target, target = parseInt(el.dataset.to, 10);
      countObs.unobserve(el);
      if (reduced) { el.textContent = target; return; }
      const dur = 1500; let start = null;
      const step = (t) => {
        if (!start) start = t;
        const p = Math.min((t - start) / dur, 1);
        el.textContent = Math.floor((0.5 - Math.cos(p * Math.PI) / 2) * target);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }, { threshold: 0.6 });
  document.querySelectorAll("[data-to]").forEach((el) => countObs.observe(el));

  /* ── Terminais digitados ── */
  // Cada .term-body contém spans com data-type (digitado) ou data-print (aparece de uma vez)
  function runTerminal(body) {
    const nodes = Array.from(body.querySelectorAll("[data-type],[data-print]"));
    if (reduced) { nodes.forEach((n) => { n.style.visibility = "visible"; }); return; }
    const caret = document.createElement("span");
    caret.className = "term-caret";
    let i = 0;
    function next() {
      if (i >= nodes.length) { caret.remove(); return; }
      const node = nodes[i++];
      node.style.visibility = "visible";
      if (node.hasAttribute("data-print")) {
        setTimeout(next, parseInt(node.dataset.print, 10) || 350);
        return;
      }
      const full = node.textContent;
      node.textContent = "";
      node.appendChild(caret);
      let c = 0;
      const typeChar = () => {
        if (c < full.length) {
          caret.before(full[c++]);
          setTimeout(typeChar, 26 + Math.random() * 40);
        } else { setTimeout(next, 380); }
      };
      typeChar();
    }
    next();
  }
  const termObs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) { runTerminal(e.target); termObs.unobserve(e.target); }
    });
  }, { threshold: 0.45 });
  document.querySelectorAll(".term-body").forEach((t) => {
    t.querySelectorAll("[data-type],[data-print]").forEach((n) => { n.style.visibility = "hidden"; });
    termObs.observe(t);
  });

  /* ── FAQ ── */
  document.querySelectorAll(".faq-item").forEach((item) => {
    const q = item.querySelector(".faq-q"), a = item.querySelector(".faq-a");
    q.addEventListener("click", () => {
      const open = item.classList.toggle("open");
      q.setAttribute("aria-expanded", open);
      a.style.maxHeight = open ? a.scrollHeight + "px" : 0;
    });
  });

  /* ── Explorador das 91 bases ── */
  const grid = document.getElementById("bases-grid");
  if (grid && typeof GUARACI_BASES !== "undefined") {
    const input = document.getElementById("bases-search");
    const countEl = document.getElementById("bases-count");
    const empty = document.getElementById("bases-empty");
    const moreWrap = document.getElementById("bases-more");
    const moreBtn = document.getElementById("bases-more-btn");
    const chips = Array.from(document.querySelectorAll("#bases-chips .chip"));
    const PAGE = 18;
    let area = "all", query = "", shown = PAGE;

    const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

    // contagem por área nos chips
    chips.forEach((c) => {
      const a = c.dataset.area;
      const n = a === "all" ? GUARACI_BASES.length : GUARACI_BASES.filter((b) => b.area === a).length;
      c.innerHTML += ' <span style="opacity:.65">' + n + "</span>";
    });

    function matches(b) {
      if (area !== "all" && b.area !== area) return false;
      if (!query) return true;
      return norm(b.n + " " + b.d + " " + b.g + " " + b.m).includes(query);
    }

    function card(b) {
      return '<article class="base-card"><h4>' + b.n + "</h4><p>" + b.d +
        '</p><div class="tags"><span class="base-tag">' + b.g +
        '</span><span class="base-tag org">' + b.m + "</span></div></article>";
    }

    function render() {
      const list = GUARACI_BASES.filter(matches);
      grid.innerHTML = list.slice(0, shown).map(card).join("");
      countEl.innerHTML = "Mostrando <b>" + Math.min(shown, list.length) + "</b> de <b>" + list.length + "</b> conjuntos" +
        (list.length !== GUARACI_BASES.length ? " (de " + GUARACI_BASES.length + " no total)" : "");
      empty.style.display = list.length ? "none" : "block";
      moreWrap.style.display = list.length > shown ? "block" : "none";
    }

    input.addEventListener("input", () => { query = norm(input.value.trim()); shown = PAGE; render(); });
    chips.forEach((c) => c.addEventListener("click", () => {
      chips.forEach((x) => x.classList.remove("active"));
      c.classList.add("active");
      area = c.dataset.area; shown = PAGE; render();
    }));
    moreBtn.addEventListener("click", () => { shown += 1000; render(); });
    render();
  }

  /* ── Logo: fallback enquanto a arte final não existe ── */
  document.querySelectorAll("img[data-logo]").forEach((img) => {
    img.addEventListener("error", () => {
      img.style.display = "none";
      const fb = img.nextElementSibling;
      if (fb && fb.hasAttribute("data-logo-fallback")) fb.style.display = "grid";
    });
  });
})();
