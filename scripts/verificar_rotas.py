"""Varredura das rotas do Guaraci em todas as fontes do catálogo.

Camada ``offline`` (padrão): nada é baixado. Para cada fonte exercita as
rotas da API que a interface chama (``/sources``, ``/sources/{s}/schema``,
``/themes``, ``/presets``), os comandos da CLI que não coletam (``fetch
schema``, ``fetch fields``, ``fetch list``, ``orchestrate profiles``), o
perfil do orquestrador e a validação do pedido que a interface montaria com
os valores padrão do formulário.

Camada ``discovery``: chama ``POST /sources/{s}/discovery`` (o botão
"Estimar volume") em toda fonte que o oferece. Vai à rede, mas só lista.

Camada ``jobs``: dispara pela API de jobs uma coleta pequena por fonte e
confere estado final, eventos e arquivos. Vai à rede e baixa dado.

    python scripts/verificar_rotas.py [--camada offline|discovery|jobs]
                                      [--fontes a,b] [--saida reports/...]

O relatório sai em JSON (uma entrada por fonte e verificação) e o resumo no
terminal. Código de saída 1 se alguma verificação falhar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from click.testing import CliRunner  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from guaraci.api.main import app  # noqa: E402
from guaraci.cli.main import app as cli_app  # noqa: E402

# Janelas pequenas por modo, para a camada ``jobs``: o objetivo é provar que a
# rota funciona de ponta a ponta, não trazer a série inteira.
_SMALL = {
    "start_year": 2023, "end_year": 2023, "year": 2023,
    "start_month": 1, "end_month": 1, "month": 1,
    "states": ["AC"], "uf": "AC", "ufs": ["AC"],
    "max_pages": 1, "page_size": 50, "limit": 50, "max_files": 1,
}


def ui_payload(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Reproduz ``buildPayload()`` de app.js com o formulário intocado."""
    params: Dict[str, Any] = {}
    for spec in schema["params"]:
        name, kind, default = spec["name"], spec["type"], spec.get("default")
        if kind == "boolean":
            params[name] = bool(default)
        elif kind == "integer":
            if default is not None:
                params[name] = int(default)
            elif spec.get("required"):
                params[name] = None
        elif kind == "string_list":
            if isinstance(default, list) and default:
                params[name] = [str(v) for v in default]
        else:
            if default not in (None, ""):
                params[name] = str(default)
    return params


class Relatorio:
    def __init__(self) -> None:
        self.linhas: List[Dict[str, Any]] = []

    def registra(self, fonte: str, verificacao: str, ok: bool, detalhe: Any = "") -> None:
        self.linhas.append({"fonte": fonte, "verificacao": verificacao, "ok": ok, "detalhe": detalhe})

    def roda(self, fonte: str, verificacao: str, fn: Callable[[], Any]) -> Any:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                resultado = fn()
            avisos = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
            self.registra(fonte, verificacao, True, {"avisos": avisos} if avisos else "")
            return resultado
        except AssertionError as exc:
            self.registra(fonte, verificacao, False, str(exc) or "assert")
        except Exception as exc:  # noqa: BLE001
            self.registra(fonte, verificacao, False, f"{type(exc).__name__}: {exc}"[:600])
        return None

    @property
    def falhas(self) -> List[Dict[str, Any]]:
        return [linha for linha in self.linhas if not linha["ok"]]


# --- camada offline ---------------------------------------------------------


def camada_offline(api: TestClient, fontes: List[Dict[str, Any]], rel: Relatorio) -> None:
    from guaraci.orchestrator.cadence import profile_for
    from guaraci.services.downloads import DownloadService

    service = DownloadService()
    # Largura folgada: a tabela do Rich dobra nomes longos em 80 colunas.
    cli = CliRunner(env={"COLUMNS": "400"})

    def globais() -> None:
        for rota in ("/", "/ui", "/health", "/themes", "/presets", "/jobs"):
            resp = api.get(rota)
            assert resp.status_code == 200, f"{rota} -> {resp.status_code}"
        temas = api.get("/themes").json()
        temas = temas.get("themes", temas) if isinstance(temas, dict) else temas
        for tema in temas:
            nome = tema["slug"] if isinstance(tema, dict) else tema
            resp = api.get("/sources", params={"theme": nome})
            assert resp.status_code == 200 and resp.json(), f"tema {nome} vazio"
        assert api.get("/sources", params={"theme": "nao_existe"}).status_code in (400, 404, 422)
        assert api.get("/sources/nao_existe/schema").status_code in (400, 404)
        for rota in ("/jobs/nao_existe", "/jobs/nao_existe/logs", "/jobs/nao_existe/output"):
            assert api.get(rota).status_code == 404, rota
        resp = api.post("/jobs", json={"source": "nao_existe", "params": {}})
        assert resp.status_code in (400, 404, 422), f"POST /jobs fonte inválida -> {resp.status_code}"
        for args in (["fetch", "list"], ["fetch", "themes"], ["fetch", "presets"],
                     ["orchestrate", "profiles"], ["--help"]):
            res = cli.invoke(cli_app, args)
            assert res.exit_code == 0, f"{' '.join(args)}: {res.output[-400:]}"

    rel.roda("*", "rotas globais e CLI de catálogo", globais)

    def presets() -> None:
        lista = api.get("/presets").json()
        lista = lista.get("presets", lista) if isinstance(lista, dict) else lista
        for item in lista:
            nome = item["name"]
            det = api.get(f"/presets/{nome}")
            assert det.status_code == 200, f"/presets/{nome}"
            res = cli.invoke(cli_app, ["fetch", "preset", nome])
            assert res.exit_code == 0, f"fetch preset {nome}: {res.output[-300:]}"
            for passo in det.json().get("steps", []):
                service.validate_source_params(passo["source"], passo.get("params") or {})

    rel.roda("*", "presets: rota, CLI e parâmetros de cada passo", presets)

    nomes_cli = cli.invoke(cli_app, ["fetch", "list"]).output

    for fonte in fontes:
        s = fonte["source"]

        def schema(s=s) -> Dict[str, Any]:
            resp = api.get(f"/sources/{s}/schema")
            assert resp.status_code == 200, resp.status_code
            corpo = resp.json()
            assert corpo["params"], "schema sem parâmetros"
            assert corpo["themes"], "fonte sem tema"
            vistos = set()
            for p in corpo["params"]:
                assert p["name"] not in vistos, f"parâmetro duplicado {p['name']}"
                vistos.add(p["name"])
                assert p["type"] in ("string", "integer", "boolean", "string_list"), p
                assert (p.get("description") or "").strip(), f"{p['name']} sem descrição"
                d, lo, hi = p.get("default"), p.get("minimum"), p.get("maximum")
                if p["type"] == "integer" and d is not None:
                    assert lo is None or d >= lo, f"{p['name']}: padrão {d} < mínimo {lo}"
                    assert hi is None or d <= hi, f"{p['name']}: padrão {d} > máximo {hi}"
                allowed = p.get("allowed_values")
                if allowed and d not in (None, "", []):
                    padroes = d if isinstance(d, list) else [d]
                    fora = [v for v in padroes if v not in allowed and str(v) not in map(str, allowed)]
                    assert not fora, f"{p['name']}: padrão {fora} fora de allowed_values"
            return corpo

        corpo = rel.roda(s, "GET /sources/{s}/schema", schema)

        def cli_schema(s=s) -> None:
            res = cli.invoke(cli_app, ["fetch", "schema", s])
            assert res.exit_code == 0, res.output[-400:]
            assert s in nomes_cli, "ausente de `fetch list`"

        rel.roda(s, "CLI fetch schema / list", cli_schema)

        def cli_fields(s=s) -> None:
            res = cli.invoke(cli_app, ["fetch", "fields", s])
            assert res.exit_code == 0, res.output[-400:]
            assert res.output.strip(), "saída vazia"
            return res.output.count("\n")

        rel.roda(s, "CLI fetch fields", cli_fields)

        rel.roda(s, "perfil do orquestrador", lambda s=s, m=fonte["mode"]: profile_for(s, m))

        if corpo:
            def valida_ui(s=s, corpo=corpo) -> str:
                # Campo obrigatório sem padrão (estação, código CNES,
                # coordenada) é entrada do usuário por desenho: aí o que se
                # exige é que a recusa nomeie o campo, e que POST /jobs a
                # devolva como 400 em vez de enfileirar um job condenado.
                pendentes = [p["name"] for p in corpo["params"] if p["required"] and p["default"] is None]
                try:
                    service.validate_source_params(s, ui_payload(corpo))
                except ValueError as exc:
                    citados = [n for n in pendentes if n in str(exc)] or [
                        n for n in ("codigoCatmat", "cnpjInstituicao") if n in str(exc)
                    ]
                    assert citados, f"recusa não nomeia o campo: {exc}"
                    resp = api.post("/jobs", json={"source": s, "params": ui_payload(corpo)})
                    assert resp.status_code == 400, f"POST /jobs -> {resp.status_code}"
                    return f"exige {', '.join(citados)} do usuário"
                assert not pendentes, f"{pendentes} obrigatórios sem padrão, mas aceitou vazio"
                return ""

            rel.roda(s, "pedido da interface com valores padrão é válido", valida_ui)

            def discovery_flag(s=s) -> None:
                anunciado = bool(fonte.get("supports_discovery"))
                assert anunciado == service.supports_discovery(s), "supports_discovery diverge"

            rel.roda(s, "supports_discovery coerente", discovery_flag)


# --- camada discovery -------------------------------------------------------


def camada_discovery(api: TestClient, fontes: List[Dict[str, Any]], rel: Relatorio) -> None:
    alvos = [f for f in fontes if f.get("supports_discovery")]

    def um(fonte: Dict[str, Any]) -> None:
        s = fonte["source"]
        schema = api.get(f"/sources/{s}/schema").json()
        params = ui_payload(schema)
        nomes = {p["name"] for p in schema["params"]}
        # Ano padrão do formulário (é o que o usuário estima sem mexer) e um
        # estado com dado em todo sistema, inclusive o PCE, só de área endêmica.
        if "states" in nomes:
            params["states"] = ["BA"]

        def chama() -> Dict[str, Any]:
            t0 = time.monotonic()
            resp = api.post(f"/sources/{s}/discovery", json={"params": params})
            assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:400]}"
            corpo = resp.json()
            achados = corpo.get("files_found", corpo.get("documents_found", corpo.get("total_files")))
            assert achados, f"estimativa vazia: {json.dumps(corpo, ensure_ascii=False)[:300]}"
            return {"arquivos": achados, "s": round(time.monotonic() - t0, 1)}

        rel.roda(s, "POST /sources/{s}/discovery", chama)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(um, alvos))


# --- camada jobs ------------------------------------------------------------


def camada_jobs(api: TestClient, fontes: List[Dict[str, Any]], rel: Relatorio, timeout: int) -> None:
    base = Path(tempfile.mkdtemp(prefix="guaraci_jobs_"))

    def um(fonte: Dict[str, Any]) -> None:
        s = fonte["source"]
        schema = api.get(f"/sources/{s}/schema").json()
        nomes = {p["name"] for p in schema["params"]}
        params = ui_payload(schema)
        for chave, valor in _SMALL.items():
            if chave in nomes:
                spec = next(p for p in schema["params"] if p["name"] == chave)
                lo, hi = spec.get("minimum"), spec.get("maximum")
                if isinstance(valor, int) and hi is not None and valor > hi:
                    valor = hi
                if isinstance(valor, int) and lo is not None and valor < lo:
                    valor = lo
                allowed = spec.get("allowed_values")
                if allowed and isinstance(valor, list) and not set(valor) <= set(allowed):
                    continue
                params[chave] = valor
        params["output_dir"] = str(base / s)
        if "output_format" in nomes and "output_format" not in params:
            params["output_format"] = "csv"

        def roda() -> Dict[str, Any]:
            resp = api.post("/jobs", json={"source": s, "params": params})
            assert resp.status_code in (200, 201, 202), f"{resp.status_code}: {resp.text[:400]}"
            job_id = resp.json()["job_id"]
            fim = time.monotonic() + timeout
            job: Dict[str, Any] = {}
            while time.monotonic() < fim:
                job = api.get(f"/jobs/{job_id}").json()
                if job["status"] in ("succeeded", "failed", "canceled", "cancelled"):
                    break
                time.sleep(2)
            else:
                api.post(f"/jobs/{job_id}/cancel")
                raise AssertionError(f"estourou {timeout}s")
            logs = api.get(f"/jobs/{job_id}/logs").json()
            saida = api.get(f"/jobs/{job_id}/output")
            eventos = logs.get("events", logs) if isinstance(logs, dict) else logs
            erros = [e.get("message") for e in eventos if e.get("level") in ("error", "warning")]
            assert job["status"] == "succeeded", f"{job['status']}: {job.get('error') or erros[-3:]}"
            assert saida.status_code == 200, f"/output -> {saida.status_code}"
            arquivos = [p for p in (base / s).rglob("*") if p.is_file()]
            assert arquivos, "job terminou sem arquivo"
            vazios = [p.name for p in arquivos if p.stat().st_size == 0]
            return {
                "arquivos": len(arquivos),
                "bytes": sum(p.stat().st_size for p in arquivos),
                "vazios": vazios,
                "avisos_log": erros[:5],
            }

        rel.roda(s, "POST /jobs (coleta pequena)", roda)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(um, fontes))


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camada", default="offline", choices=["offline", "discovery", "jobs"])
    parser.add_argument("--fontes", default="")
    parser.add_argument("--excluir", default="")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--saida", default="")
    args = parser.parse_args()

    os.environ.setdefault("GUARACI_JOBS_STATE_PATH", str(Path(tempfile.mkdtemp()) / "jobs.json"))
    api = TestClient(app)
    fontes = api.get("/sources").json()
    fontes = fontes.get("sources", fontes) if isinstance(fontes, dict) else fontes
    if args.fontes:
        wanted = set(args.fontes.split(","))
        fontes = [f for f in fontes if f["source"] in wanted]
    if args.excluir:
        skip = set(args.excluir.split(","))
        fontes = [f for f in fontes if f["source"] not in skip]

    rel = Relatorio()
    t0 = time.monotonic()
    if args.camada == "offline":
        camada_offline(api, fontes, rel)
    elif args.camada == "discovery":
        camada_discovery(api, fontes, rel)
    else:
        camada_jobs(api, fontes, rel, args.timeout)

    saida = Path(args.saida or ROOT / "reports" / f"verificacao_{args.camada}_{datetime.now():%Y%m%d_%H%M}.json")
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(rel.linhas, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    avisos = [l for l in rel.linhas if l["ok"] and isinstance(l["detalhe"], dict) and l["detalhe"].get("avisos")]
    print(f"{len(fontes)} fontes, {len(rel.linhas)} verificações, {len(rel.falhas)} falhas, "
          f"{len(avisos)} com aviso, {time.monotonic() - t0:.0f}s -> {saida}")
    for linha in rel.falhas:
        print(f"FALHA  {linha['fonte']:<40} {linha['verificacao']}: {linha['detalhe']}")
    return 1 if rel.falhas else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
