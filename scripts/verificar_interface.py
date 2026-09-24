"""Percorre a interface web do Guaraci num Chromium real (Playwright).

Para cada fonte do catálogo: abre "Nova coleta", clica no cartão, espera o
formulário, confere que todo parâmetro do schema virou campo, clica em
"Estimar volume" quando a fonte oferece, e clica em "Baixar" com o
formulário intocado. O POST /jobs é interceptado: o corpo que a interface
montou é guardado e a coleta não acontece. Depois, uma coleta de verdade de
ponta a ponta (fila, gaveta, log, saída) numa fonte pequena.

Qualquer erro de console, exceção de página ou resposta 5xx conta como falha.
Precisa do pacote ``playwright`` (fora das dependências do projeto) e da API
rodando com GUARACI_DATA_ROOT temporário:

    GUARACI_DATA_ROOT=/tmp/x python -m uvicorn guaraci.api.main:app --port 8766
    python scripts/verificar_interface.py --url http://127.0.0.1:8766
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # --validar roda no venv do projeto, sem Playwright
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--fontes", default="")
    parser.add_argument("--coleta-real", default="ibge_area_territorial")
    parser.add_argument("--saida", default=str(ROOT / "reports" / "verificacao_interface"))
    parser.add_argument("--validar", action="store_true",
                        help="Só valida os corpos já capturados (venv do projeto).")
    args = parser.parse_args()
    shots = Path(args.saida)
    if args.validar:
        return validar(shots)
    shots.mkdir(parents=True, exist_ok=True)

    problemas: List[Dict[str, Any]] = []
    capturados: Dict[str, Any] = {}
    estimativas: Dict[str, str] = {}
    contexto = {"fonte": "(carga)"}

    with sync_playwright() as pw:
        # Chrome instalado: o Chromium do Playwright pode estar em outra versão.
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # O 400 devolvido de propósito pela interceptação também vira erro de
        # console; esse é ignorado, o resto não.
        page.on("console", lambda m: m.type == "error" and not (
            contexto.get("interceptando") and "status of 400" in m.text) and problemas.append(
            {"fonte": contexto["fonte"], "tipo": "console", "msg": m.text}))
        page.on("pageerror", lambda e: problemas.append(
            {"fonte": contexto["fonte"], "tipo": "pageerror", "msg": str(e)}))
        page.on("response", lambda r: r.status >= 500 and problemas.append(
            {"fonte": contexto["fonte"], "tipo": "http", "msg": f"{r.status} {r.url}"}))

        def intercepta(route, request):
            if request.method == "POST":
                capturados[contexto["fonte"]] = json.loads(request.post_data or "{}")
                route.fulfill(status=400, content_type="application/json",
                              body=json.dumps({"detail": "interceptado pelo verificador"}))
            else:
                route.continue_()

        page.goto(args.url + "/")
        page.wait_for_selector("#jobs-body")
        page.screenshot(path=str(shots / "01_jobs.png"))

        fontes = page.evaluate("fetch('/sources').then(r => r.json())")
        if args.fontes:
            wanted = set(args.fontes.split(","))
            fontes = [f for f in fontes if f["source"] in wanted]

        page.route("**/jobs", intercepta)
        contexto["interceptando"] = True
        for i, fonte in enumerate(fontes):
            s = fonte["source"]
            contexto["fonte"] = s
            try:
                # Menu lateral: o "Nova coleta" do topo some dentro da própria tela.
                page.click("[data-view='new']")
                if page.is_visible("#btn-back-catalog"):
                    page.click("#btn-back-catalog")
                page.fill("#nc-search", s)
                card = page.locator("#nc-catalog .src-card", has=page.locator(f"p:text-is('{s}')"))
                card.first.click()
                page.wait_for_selector("#nc-step2:not([hidden])")
                page.wait_for_function(
                    "document.querySelectorAll('[data-param-name]').length > 0", timeout=15000)
                schema = page.evaluate(f"fetch('/sources/{s}/schema').then(r => r.json())")
                campos = set(page.evaluate(
                    "[...document.querySelectorAll('[data-param-name]')].map(e => e.dataset.paramName)"))
                faltam = [p["name"] for p in schema["params"] if p["name"] not in campos]
                if faltam:
                    problemas.append({"fonte": s, "tipo": "form", "msg": f"campos sem controle: {faltam}"})
                if i == 0:
                    page.screenshot(path=str(shots / "02_formulario.png"))

                if fonte.get("supports_discovery"):
                    if not page.is_visible("#btn-estimate"):
                        problemas.append({"fonte": s, "tipo": "form", "msg": "botão Estimar oculto"})
                    else:
                        page.click("#btn-estimate")
                        page.wait_for_function(
                            "(() => { const b = document.getElementById('estimate-box');"
                            " return !b.hidden && !/Estimando|Estimating/i.test(b.textContent); })()",
                            timeout=120000)
                        texto = page.inner_text("#estimate-box").strip()
                        estimativas[s] = texto
                        if "falh" in texto.lower() or "fail" in texto.lower():
                            problemas.append({"fonte": s, "tipo": "estimativa", "msg": texto})

                page.click("#btn-submit")
                page.wait_for_function(
                    "!document.getElementById('btn-submit').disabled", timeout=15000)
                if s not in capturados:
                    problemas.append({"fonte": s, "tipo": "form", "msg": "Baixar não enviou POST /jobs"})
            except Exception as exc:  # noqa: BLE001
                problemas.append({"fonte": s, "tipo": "fluxo", "msg": str(exc).splitlines()[0][:300]})
                page.screenshot(path=str(shots / f"erro_{s}.png"))
                page.goto(args.url + "/")
                page.wait_for_selector("#jobs-body")
        page.unroute("**/jobs", intercepta)
        contexto["interceptando"] = False

        # Coleta real de ponta a ponta pela interface.
        s = args.coleta_real
        contexto["fonte"] = f"{s} (real)"
        page.goto(args.url + "/")
        page.click("[data-view='new']")
        page.fill("#nc-search", s)
        page.locator("#nc-catalog .src-card", has=page.locator(f"p:text-is('{s}')")).first.click()
        page.wait_for_function("document.querySelectorAll('[data-param-name]').length > 0")
        page.click("#btn-submit")
        fim = time.monotonic() + 300
        status = ""
        while time.monotonic() < fim:
            status = page.inner_text("#drawer-badge").strip().lower()
            if any(k in status for k in ("conclu", "complet", "falh", "fail", "cancel")):
                break
            time.sleep(2)
        page.screenshot(path=str(shots / "03_gaveta_job.png"))
        log = page.inner_text("#log-box")
        exportados = page.inner_text("#d-exported")
        if not any(k in status for k in ("conclu", "complet")):
            problemas.append({"fonte": s, "tipo": "coleta", "msg": f"estado final {status!r}; log: {log[-300:]}"})
        if not exportados.strip() or exportados.strip() in ("-", "--"):
            problemas.append({"fonte": s, "tipo": "coleta", "msg": "gaveta sem arquivos exportados"})

        # Outras telas e alternâncias.
        contexto["fonte"] = "(telas)"
        page.keyboard.press("Escape")
        time.sleep(0.5)
        # A gaveta fecha deslizando para fora da tela, sem sumir do DOM.
        caixa = page.locator("#drawer-close").bounding_box()
        if caixa and caixa["x"] < 1440:
            problemas.append({"fonte": "(telas)", "tipo": "layout", "msg": "Esc não fechou a gaveta"})
            page.click("#drawer-close", force=True)
        for view in ("sources", "jobs"):
            page.click(f"[data-view='{view}']")
            time.sleep(0.5)
        page.fill("#sources-search", "anvisa") if page.is_visible("#sources-search") else None
        page.click("#lang-toggle")
        page.click("#theme-toggle")
        time.sleep(0.5)
        rotulo = page.inner_text("#api-label")
        if "connecting" in rotulo.lower() or "conectando" in rotulo.lower():
            problemas.append({"fonte": "(telas)", "tipo": "i18n", "msg": f"rótulo da API após trocar idioma: {rotulo}"})
        page.screenshot(path=str(shots / "04_en_tema.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(args.url + "/")
        page.wait_for_selector("#jobs-body")
        time.sleep(2)  # animação de entrada dos painéis
        page.screenshot(path=str(shots / "05_celular.png"), full_page=True)
        largura = page.evaluate("document.documentElement.scrollWidth")
        if largura > 400:
            problemas.append({"fonte": "(celular)", "tipo": "layout", "msg": f"rolagem horizontal: {largura}px"})
        browser.close()

    # A validação dos corpos capturados roda no venv do projeto (o Playwright
    # fica num venv à parte): python scripts/verificar_interface.py --validar.

    (shots / "resultado.json").write_text(json.dumps(
        {"problemas": problemas, "payloads": capturados, "estimativas": estimativas},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(fontes)} fontes na interface, {len(capturados)} envios capturados, "
          f"{len(estimativas)} estimativas, {len(problemas)} problemas -> {shots}")
    for p in problemas:
        print(f"PROBLEMA {p['tipo']:<10} {p['fonte']:<40} {p['msg']}")
    return 1 if problemas else 0


def validar(shots: Path) -> int:
    from guaraci.services.downloads import DownloadService

    dados = json.loads((shots / "resultado.json").read_text(encoding="utf-8"))
    service = DownloadService()
    recusas = []
    for s, corpo in dados["payloads"].items():
        try:
            service.validate_source_params(s, corpo.get("params") or {})
        except ValueError as exc:
            recusas.append((s, str(exc)[:200]))
    print(f"{len(dados['payloads'])} corpos montados pela interface, {len(recusas)} recusados")
    for s, msg in recusas:
        print(f"RECUSA {s:<40} {msg}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
