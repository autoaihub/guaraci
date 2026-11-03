#!/usr/bin/env python3
"""Gera as paginas publicas do site (PT, EN, ES) a partir do molde em site-src/.

Entrada:  site-src/index.tpl.html, site-src/docs.tpl.html, site-src/icons.json,
          site-src/i18n/{pt,en,es}.json
Saida:    site/index.html, site/docs.html (pt, raiz), site/en/*.html, site/es/*.html,
          site/assets/icons.js e site/sitemap.xml.

O molde fica fora de site/ porque site/ e publicado inteiro. Os numeros (conjuntos distintos,
entradas, grupos, contagem por area) saem de site/assets/catalog-data.js, para o HTML estatico
trazer o mesmo valor que o JS exibe depois. Chaves ausentes em en/es caem para o PT, com aviso.

Entre os marcadores jsonld:catalogo do docs.html fica o bloco escrito por
scripts/build_site_catalog.py: este gerador preserva o que ja estiver la.

Uso: python scripts/build_site_pages.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site-src"
SITE = ROOT / "site"
BASE_URL = "https://sabiadatalake.com.br/guaraci/"
LASTMOD = "2026-11-03"
VERSAO = "20261103a"
LANGS = ["pt", "en", "es"]
META = {
    "pt": {"html": "pt-BR", "hreflang": "pt-BR", "og": "pt_BR", "dir": ""},
    "en": {"html": "en", "hreflang": "en", "og": "en_US", "dir": "en/"},
    "es": {"html": "es", "hreflang": "es", "og": "es_ES", "dir": "es/"},
}
JSONLD_INI = "<!-- jsonld:catalogo:inicio (gerado por scripts/build_site_catalog.py) -->"
JSONLD_FIM = "<!-- jsonld:catalogo:fim -->"

TEMA_SCRIPT = (
    "<script>(function(){var d=document.documentElement;d.classList.add('js');var t;"
    "try{t=localStorage.getItem('guaraci-tema')}catch(e){}"
    "if(t!=='claro'&&t!=='escuro')t=(window.matchMedia&&matchMedia('(prefers-color-scheme: light)').matches)?'claro':'escuro';"
    "d.classList.add('tema-'+t)})()</script>"
)


def flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, prefix + k + "."))
        else:
            out[prefix + k] = v
    return out


def ler_catalogo() -> dict:
    txt = (SITE / "assets" / "catalog-data.js").read_text(encoding="utf-8")
    ini = txt.index("const GUARACI_CATALOG = ") + len("const GUARACI_CATALOG = ")
    fim = txt.index(";\nconst GUARACI_BASES")
    cat = json.loads(txt[ini:fim])
    distintos = int(re.search(r"GUARACI_DISTINCT\s*=\s*(\d+)", txt).group(1))
    areas = {}
    for e in cat.values():
        areas[e["area"]] = areas.get(e["area"], 0) + 1
    return {
        "d": distintos,
        "e": len(cat),
        "g": len({e["g"] for e in cat.values()}),
        "areas": areas,
    }


ICONES = json.loads((SRC / "icons.json").read_text(encoding="utf-8"))


def glifo(nome: str, tam: str | None = None) -> str:
    miolo = ICONES["glifos"][nome]
    dim = f' width="{tam}" height="{tam}"' if tam else ""
    return f'<svg class="mini" viewBox="0 0 48 48"{dim} aria-hidden="true">{miolo}</svg>'


def peca(nome: str, tam: str | None = None, fundo: str = "#f3ead6") -> str:
    miolo = ICONES["pecas"][nome]
    dim = f' width="{tam}" height="{tam}"' if tam else ""
    return (f'<svg class="peca" viewBox="0 0 48 48"{dim} aria-hidden="true">'
            f'<rect width="48" height="48" fill="{fundo}"/>{miolo}</svg>')


def faixa() -> str:
    seq = [("meia", 90), ("quarto", 0), ("meia", 270), ("tri", 180), ("sol", 90), ("quarto", 0), ("ondas", 270), ("tri", 180)]
    out = []
    for nome, rot in seq * 2:
        out.append(f'<span class="az" style="--r:{rot}deg">{peca(nome, None, "var(--azulejo)")}</span>')
    return "".join(out)


def imp_az() -> str:
    t = "#04120f"
    c = "#f3ead6"
    figs = [
        (0, f'<path d="M0 48V0A48 48 0 0 1 48 48Z" fill="{t}"/>'),
        (90, f'<path d="M0 48A24 24 0 0 1 48 48Z" fill="{t}"/><rect width="48" height="8" fill="{c}"/>'),
        (0, f'<path d="M0 0H48L0 48Z" fill="{t}"/><circle cx="36" cy="36" r="7" fill="{c}"/>'),
        (180, f'<path d="M0 48V0A48 48 0 0 1 48 48Z" fill="{t}"/>'),
        (90, f'<path d="M0 0H48L0 48Z" fill="{t}"/><circle cx="36" cy="36" r="7" fill="{c}"/>'),
        (0, f'<circle cx="24" cy="24" r="11" fill="{t}"/><path d="M0 0H12A12 12 0 0 1 0 12Z M48 48H36A12 12 0 0 1 48 36Z" fill="{c}"/>'),
        (270, f'<path d="M0 48A24 24 0 0 1 48 48Z" fill="{t}"/><rect width="48" height="8" fill="{c}"/>'),
        (90, f'<path d="M0 48V0A48 48 0 0 1 48 48Z" fill="{t}"/>'),
        (0, f'<rect y="18" width="48" height="12" fill="{c}"/><path d="M24 0A12 12 0 0 1 12 12 12 12 0 0 1 24 0Z" fill="{t}"/><path d="M24 48A12 12 0 0 1 36 36 12 12 0 0 1 24 48Z" fill="{t}"/>'),
    ]
    return "".join(f'<svg class="peca" viewBox="0 0 48 48" style="--r:{r}deg" aria-hidden="true">{m}</svg>' for r, m in figs)


def lista_inst(nomes: list[str]) -> str:
    ciclo = ["quarto", "meia", "tri", "ondas"]
    cores = {"quarto": "#f7a41d", "meia": "#14b8a6", "tri": "#f7a41d", "ondas": "#14b8a6"}
    out = []
    for i, n in enumerate(nomes):
        forma = ciclo[i % 4]
        miolo = ICONES["pecas"][forma]
        out.append(f'<li><svg class="mini" viewBox="0 0 48 48" aria-hidden="true">{miolo}</svg>{html.escape(n)}</li>')
    return "".join(out)


TEMA_SEL = (
    '<div class="tema-sel" role="group" aria-label="{label}">'
    '<button type="button" data-tema="escuro" aria-pressed="true" aria-label="{dark}" title="{dark}">'
    '<svg viewBox="0 0 48 48" aria-hidden="true"><rect x="2" y="2" width="44" height="44" fill="#0b302b" stroke="currentColor" stroke-width="4"/><path d="M4 44V4A40 40 0 0 1 44 44Z" fill="#f3ead6"/></svg></button>'
    '<button type="button" data-tema="claro" aria-pressed="false" aria-label="{light}" title="{light}">'
    '<svg viewBox="0 0 48 48" aria-hidden="true"><rect x="2" y="2" width="44" height="44" fill="#f3ead6" stroke="currentColor" stroke-width="4"/><path d="M4 44V4A40 40 0 0 1 44 44Z" fill="#04120f"/></svg></button></div>'
)


def url_pagina(lang: str, pagina: str, de: str) -> str:
    """Link relativo da pagina `pagina` (index|docs) em `lang`, visto de uma pagina em `de`."""
    prefixo = "" if de == "pt" else "../"
    destino = META[lang]["dir"]
    if pagina == "index":
        return (prefixo + destino) or "./"
    return prefixo + destino + "docs.html"


def url_abs(lang: str, pagina: str) -> str:
    return BASE_URL + META[lang]["dir"] + ("" if pagina == "index" else "docs.html")


def seletor_idioma(lang: str, pagina: str, rot: dict) -> str:
    partes = []
    for l in LANGS:
        atual = ' aria-current="true"' if l == lang else ""
        partes.append(f'<a href="{url_pagina(l, pagina, lang)}" lang="{l}" hreflang="{META[l]["hreflang"]}"{atual}>{l.upper()}</a>')
    return f'<div class="lang" role="group" aria-label="{html.escape(rot["lang_label"])}">' + "".join(partes) + "</div>"


def head(lang: str, pagina: str) -> str:
    m = META[lang]
    pre = "" if lang == "pt" else "../"
    ass = pre + "assets/"
    linhas = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        TEMA_SCRIPT,
        f'<link rel="canonical" href="{url_abs(lang, pagina)}">',
    ]
    for l in LANGS:
        linhas.append(f'<link rel="alternate" hreflang="{META[l]["hreflang"]}" href="{url_abs(l, pagina)}">')
    linhas.append(f'<link rel="alternate" hreflang="x-default" href="{url_abs("pt", pagina)}">')
    linhas += [
        '<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{url_abs(lang, pagina)}">',
        '<meta property="og:site_name" content="Guaraci">',
        f'<meta property="og:locale" content="{m["og"]}">',
    ]
    for l in LANGS:
        if l != lang:
            linhas.append(f'<meta property="og:locale:alternate" content="{META[l]["og"]}">')
    linhas += [
        f'<meta property="og:image" content="{BASE_URL}assets/video-capa.jpg">',
        '<meta property="og:image:width" content="1280">',
        '<meta property="og:image:height" content="720">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<link rel="icon" type="image/svg+xml" href="{ass}logo-guaraci.svg">',
        f'<link rel="preload" href="{ass}fonts/space-grotesk-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>',
        f'<link rel="preload" href="{ass}fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>',
        f'<link href="{ass}site.css?v={VERSAO}" rel="stylesheet">',
    ]
    return "\n".join(linhas)


def jsonld(lang: str, rot: dict) -> str:
    dados = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "Guaraci",
        "url": url_abs(lang, "index"),
        "description": rot["ld_desc"],
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Windows, macOS, Linux",
        "inLanguage": META[lang]["html"],
        "isAccessibleForFree": True,
        "license": "https://opensource.org/licenses/MIT",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "BRL"},
        "image": BASE_URL + "assets/video-capa.jpg",
        "sameAs": ["https://github.com/autoaihub/guaraci"],
        "publisher": {
            "@type": "Organization",
            "name": "AutoAI-Pandemics (ICMC-USP)",
            "url": "https://autoaipandemics.icmc.usp.br/",
        },
    }
    return json.dumps(dados, ensure_ascii=False, indent=2)


def scripts(lang: str, pagina: str, ui: dict) -> str:
    ass = ("" if lang == "pt" else "../") + "assets/"
    cfg = json.dumps(ui, ensure_ascii=False)
    out = [f'<script>window.GUARACI_LANG="{lang}";window.GUARACI_UI={cfg};</script>',
           f'<script src="{ass}icons.js?v={VERSAO}"></script>',
           f'<script src="{ass}catalog-data.js?v=20260825a"></script>']
    if lang != "pt":
        out.append(f'<script src="{ass}catalog-i18n.{lang}.js?v={VERSAO}"></script>')
    out.append(f'<script src="{ass}site.js?v={VERSAO}"></script>')
    if pagina == "docs":
        out.append(f'<script src="{ass}docs.js?v={VERSAO}"></script>')
    return "\n".join(out)


def faq(itens: list[dict]) -> str:
    out = []
    for it in itens:
        out.append(
            '<div class="faq-item reveal">'
            f'<button class="faq-q" type="button" aria-expanded="false">{it["q"]}{glifo("mais", "18")}</button>'
            f'<div class="faq-a"><div class="faq-a-inner">{it["a"]}</div></div></div>'
        )
    return "\n      ".join(out)


def gerar_pagina(lang: str, pagina: str, textos: dict, base_pt: dict, nums: dict, avisos: set) -> str:
    tpl = (SRC / f"{pagina}.tpl.html").read_text(encoding="utf-8")

    def valor(chave: str) -> str:
        if chave in textos:
            return textos[chave]
        if chave in base_pt:
            avisos.add(f"{lang}: {chave}")
            return base_pt[chave]
        raise KeyError(f"chave de i18n inexistente: {chave}")

    def com_numeros(s: str, html_ctx: bool) -> str:
        if not isinstance(s, str):
            return s
        if html_ctx:
            s = s.replace("{D}", f'<span data-n="d">{nums["d"]}</span>').replace("{E}", f'<span data-n="e">{nums["e"]}</span>')
            s = s.replace("{G}", f'<span data-n="g">{nums["g"]}</span>')
        else:
            s = s.replace("{D}", str(nums["d"])).replace("{E}", str(nums["e"])).replace("{G}", str(nums["g"]))
        def area(m: re.Match) -> str:
            n = nums["areas"].get(m.group(1), 0)
            return f'<span data-n="{m.group(1)}">{n}</span>' if html_ctx else str(n)

        s = re.sub(r"\{A:(\w+)\}", area, s)
        return s.replace("{I}", "32")

    ui = {k[3:]: valor(k) for k in base_pt if k.startswith("ui.")}
    ui = {k: com_numeros(v, False) for k, v in ui.items()}
    rot = {"lang_label": valor("lang_label"), "ld_desc": com_numeros(valor("ld_desc"), False)}
    cat_areas = nums["areas"]
    ctx = {
        "LANG_HTML": META[lang]["html"],
        "HEAD": head(lang, pagina),
        "ASSETS": ("" if lang == "pt" else "../") + "assets/",
        "URL_DOCS": "docs.html",
        "URL_INDEX": "index.html",
        "LANG_SWITCH": seletor_idioma(lang, pagina, rot),
        "THEME_SWITCH": TEMA_SEL.format(label=html.escape(valor("theme_label")), dark=html.escape(valor("theme_dark")), light=html.escape(valor("theme_light"))),
        "JSONLD": jsonld(lang, rot),
        "SCRIPTS": scripts(lang, pagina, ui),
        "FAQ": faq(valor("faq")) if pagina == "index" else "",
        "FAIXA": faixa(),
        "IMP_AZ": imp_az(),
        "INST": lista_inst(valor("inst")),
        "D_ANIM": f'<span data-n="d" data-anim>{nums["d"]}</span>',
        "G_ANIM": f'<span data-n="g" data-anim>{nums["g"]}</span>',
        "I_NUM": "32",
        "E_NUM": str(nums["e"]),
        "N_SAUDE": str(cat_areas.get("saude", 0)),
        "N_POP": str(cat_areas.get("pop", 0)),
        "N_CLIMA": str(cat_areas.get("clima", 0)),
        "N_SAN": str(cat_areas.get("san", 0)),
    }

    def sub(m: re.Match) -> str:
        k = m.group(1).strip()
        if k in ctx:
            return ctx[k]
        if k.startswith("="):
            return html.escape(com_numeros(valor(k[1:]), False), quote=True)
        if k.startswith("i:"):
            p = k.split(":")
            return glifo(p[1], p[2] if len(p) > 2 else None)
        if k.startswith("p:"):
            p = k.split(":")
            return peca(p[1], p[2] if len(p) > 2 else None)
        if k.startswith("g:"):
            return ICONES["pecas"][k[2:]]
        return com_numeros(valor(k), True)

    saida = re.sub(r"\{\{([^{}]+)\}\}", sub, tpl)
    if pagina == "docs":
        saida = preservar_jsonld(saida, SITE / META[lang]["dir"] / "docs.html")
    return saida


def preservar_jsonld(novo: str, destino: Path) -> str:
    """Mantem o que build_site_catalog.py ja escreveu entre os marcadores do docs.html."""
    if not destino.exists():
        return novo
    antigo = destino.read_text(encoding="utf-8")
    if JSONLD_INI not in antigo or JSONLD_FIM not in antigo:
        return novo
    miolo = antigo.split(JSONLD_INI, 1)[1].split(JSONLD_FIM, 1)[0]
    return novo.replace(JSONLD_INI + "\n" + JSONLD_FIM, JSONLD_INI + miolo + JSONLD_FIM)


def sitemap() -> str:
    def entrada(pagina: str, lang: str) -> str:
        alt = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{META[l]["hreflang"]}" href="{url_abs(l, pagina)}"/>' for l in LANGS
        ) + f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{url_abs("pt", pagina)}"/>'
        return f"  <url>\n    <loc>{url_abs(lang, pagina)}</loc>\n    <lastmod>{LASTMOD}</lastmod>{alt}\n  </url>"

    corpo = "\n".join(entrada(p, l) for p in ("index", "docs") for l in LANGS)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
            + corpo + "\n</urlset>\n")


def main() -> int:
    nums = ler_catalogo()
    i18n = {l: flatten(json.loads((SRC / "i18n" / f"{l}.json").read_text(encoding="utf-8"))) for l in LANGS}
    base_pt = i18n["pt"]
    avisos: set[str] = set()
    # icons.js para o JS
    (SITE / "assets" / "icons.js").write_text(
        "/* GERADO por scripts/build_site_pages.py a partir de site-src/icons.json. Nao editar. */\n"
        "window.GUARACI_ICONS = " + json.dumps(ICONES, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")
    for lang in LANGS:
        destino = SITE / META[lang]["dir"]
        destino.mkdir(parents=True, exist_ok=True)
        for pagina in ("index", "docs"):
            saida = gerar_pagina(lang, pagina, i18n[lang], base_pt, nums, avisos)
            if "{{" in saida:
                print("molde com marcador sem resolver em", lang, pagina, file=sys.stderr)
                return 1
            (destino / f"{pagina}.html").write_text(saida, encoding="utf-8", newline="\n")
            print("escrito", (destino / f"{pagina}.html").relative_to(ROOT))
    (SITE / "sitemap.xml").write_text(sitemap(), encoding="utf-8", newline="\n")
    if avisos:
        print(f"aviso: {len(avisos)} chave(s) sem traducao, usando o PT:")
        for a in sorted(avisos)[:40]:
            print("  ", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
