"""Provoca as situações ruins contra um servidor real do Guaraci.

Sobe ``uvicorn`` num processo à parte, com GUARACI_DATA_ROOT temporário, e
confere pela API:

1. jobs simultâneos de fontes diferentes terminam todos, e o arquivo de
   estado continua um JSON válido;
2. cancelar um download grande em andamento para o job em poucos segundos;
3. origem inalcançável (porta fechada) e origem que não responde (timeout)
   falham com mensagem clara, sem travar, e o job pode ser repetido;
4. derrubar o servidor no meio de uma coleta deixa o job marcado como
   interrompido quando ele volta, e a retentativa funciona;
5. entradas inválidas voltam 4xx, nunca 500.

    python scripts/verificar_resiliencia.py [--casos cancelar,invalidas]
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
TERMINAIS = {"completed", "failed", "canceled"}


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.porta = porta_livre()
        self.url = f"http://127.0.0.1:{self.porta}"
        self.proc: subprocess.Popen | None = None

    def sobe(self) -> None:
        env = dict(os.environ, GUARACI_DATA_ROOT=str(self.data_root))
        log = open(self.data_root / f"uvicorn_{int(time.time())}.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "guaraci.api.main:app", "--port", str(self.porta)],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        fim = time.monotonic() + 60
        while time.monotonic() < fim:
            try:
                if httpx.get(self.url + "/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        raise RuntimeError("servidor não subiu")

    def derruba(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=30)


def espera(cli: httpx.Client, job_id: str, limite: float, cond: Callable[[Dict[str, Any]], bool],
           intervalo: float = 1.0) -> Dict[str, Any]:
    fim = time.monotonic() + limite
    job: Dict[str, Any] = {}
    while time.monotonic() < fim:
        job = cli.get(f"/jobs/{job_id}").json()
        if cond(job):
            return job
        time.sleep(intervalo)
    raise AssertionError(f"tempo esgotado ({limite}s); último estado {job.get('status')}")


def cria(cli: httpx.Client, source: str, params: Dict[str, Any]) -> str:
    resp = cli.post("/jobs", json={"source": source, "params": params})
    assert resp.status_code in (200, 201, 202), f"{source}: {resp.status_code} {resp.text[:300]}"
    return resp.json()["job_id"]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--casos", default="", help="trechos do nome dos casos a rodar")
    filtro = [c for c in parser.parse_args().casos.split(",") if c]
    base = Path(tempfile.mkdtemp(prefix="guaraci_resil_"))
    out = base / "saida"
    srv = Servidor(base)
    srv.sobe()
    resultados: List[Dict[str, Any]] = []

    def caso(nome: str, fn: Callable[[httpx.Client], Any]) -> None:
        if filtro and not any(f in nome for f in filtro):
            return
        t0 = time.monotonic()
        try:
            with httpx.Client(base_url=srv.url, timeout=60) as cli:
                detalhe = fn(cli)
            resultados.append({"caso": nome, "ok": True, "detalhe": detalhe, "s": round(time.monotonic() - t0)})
        except Exception as exc:  # noqa: BLE001
            resultados.append({"caso": nome, "ok": False, "detalhe": f"{type(exc).__name__}: {exc}"[:500],
                               "s": round(time.monotonic() - t0)})
        print(("OK    " if resultados[-1]["ok"] else "FALHA ") + nome, "|", resultados[-1]["detalhe"], flush=True)

    # 1. simultâneos -----------------------------------------------------------
    def simultaneos(cli: httpx.Client) -> str:
        pedidos = {
            "ibge_area_territorial": {"output_format": "csv"},
            "ibge_casamentos": {"output_format": "parquet"},
            "mpox": {"output_format": "csv", "max_pages": 2},
            "esavi": {"output_format": "sqlite", "max_pages": 2},
            "anvisa_cmed_precos": {"output_format": "parquet"},
            "painel_oncologia": {"output_format": "csv"},
            "sinasc": {"output_format": "csv", "states": ["AC", "RR"]},
            "sim": {"output_format": "parquet", "states": ["AC"]},
        }
        ids = {s: cria(cli, s, dict(p, output_dir=str(out / f"sim_{s}"))) for s, p in pedidos.items()}
        finais = {s: espera(cli, j, 900, lambda job: job["status"] in TERMINAIS) for s, j in ids.items()}
        ruins = {s: (j["status"], (j.get("error") or "")[:120]) for s, j in finais.items() if j["status"] != "completed"}
        assert not ruins, f"não concluíram: {ruins}"
        estado = json.loads((base / "jobs" / "download_jobs.json").read_text(encoding="utf-8"))
        assert all(j in {x["job_id"] for x in estado} for j in ids.values()), "estado sem algum job"
        listados = {x["job_id"] for x in cli.get("/jobs?limit=40").json()}
        assert set(ids.values()) <= listados, "GET /jobs não lista todos"
        return f"{len(ids)} jobs concluídos; estado íntegro"

    caso("jobs simultâneos", simultaneos)

    # 2. cancelar no meio de um download grande --------------------------------
    def cancelar(cli: httpx.Client) -> str:
        # Dois caminhos de download diferentes: o cliente da ANVISA e o do
        # portal (zip do SISAGUA, 78 MB). Cancela assim que passa de 1 MB.
        relatos = []
        for source in ("anvisa_vigimed_reacoes", "sisagua_tratamento_agua"):
            pasta = out / f"cancel_{source}"
            job_id = cria(cli, source, {"output_format": "parquet", "output_dir": str(pasta)})
            job = espera(cli, job_id, 300, lambda j: (j.get("bytes_downloaded") or 0) > 1_000_000
                         or j["status"] in TERMINAIS, intervalo=0.3)
            assert job["status"] not in TERMINAIS, f"{source}: terminou antes de passar de 1 MB ({job['status']})"
            t0 = time.monotonic()
            assert cli.post(f"/jobs/{job_id}/cancel").status_code == 200
            job = espera(cli, job_id, 120, lambda j: j["status"] in TERMINAIS, intervalo=0.3)
            demora = time.monotonic() - t0
            assert job["status"] == "canceled", f"{source}: terminou como {job['status']}"
            assert demora < 15, f"{source}: cancelamento levou {demora:.0f}s"
            sobras = [p.name for p in pasta.rglob("*.part")]
            assert not sobras, f"{source}: .part deixado para trás: {sobras}"
            relatos.append(f"{source} em {demora:.1f}s com {job['bytes_downloaded'] / 1e6:.0f} MB")
        return "cancelados: " + "; ".join(relatos)

    caso("cancelar download em andamento", cancelar)

    # 3. origem inalcançável / muda --------------------------------------------
    def origem_fechada(cli: httpx.Client) -> str:
        job_id = cria(cli, "mpox", {"api_base_url": f"http://127.0.0.1:{porta_livre()}", "max_pages": 1,
                                    "output_format": "csv", "output_dir": str(out / "fechada")})
        job = espera(cli, job_id, 180, lambda j: j["status"] in TERMINAIS)
        assert job["status"] == "failed", job["status"]
        assert job.get("error"), "falhou sem mensagem"
        nova = cli.post(f"/jobs/{job_id}/retry")
        assert nova.status_code in (200, 201, 202), f"retry -> {nova.status_code} {nova.text[:200]}"
        assert nova.json().get("attempt") == 2 and nova.json().get("retry_of") == job_id
        espera(cli, nova.json()["job_id"], 180, lambda j: j["status"] in TERMINAIS)
        return f"falhou com: {job['error'][:120]}; retry criou tentativa 2"

    caso("origem com porta fechada", origem_fechada)

    def origem_muda(cli: httpx.Client) -> str:
        # Servidor que aceita a conexão e nunca responde.
        muda = socket.socket()
        muda.bind(("127.0.0.1", 0))
        muda.listen(5)
        porta = muda.getsockname()[1]
        try:
            t0 = time.monotonic()
            job_id = cria(cli, "mpox", {"api_base_url": f"http://127.0.0.1:{porta}", "max_pages": 1,
                                        "output_format": "csv", "output_dir": str(out / "muda")})
            job = espera(cli, job_id, 900, lambda j: j["status"] in TERMINAIS)
            demora = time.monotonic() - t0
        finally:
            muda.close()
        assert job["status"] == "failed", job["status"]
        return f"desistiu em {demora:.0f}s: {(job.get('error') or '')[:120]}"

    caso("origem que não responde", origem_muda)

    # 4. servidor derrubado no meio ----------------------------------------------
    def derrubado(cli: httpx.Client) -> str:
        job_id = cria(cli, "srag_arquivos", {"start_year": 2024, "end_year": 2024, "output_format": "parquet",
                                             "output_dir": str(out / "derrubado")})
        espera(cli, job_id, 300, lambda j: (j.get("bytes_downloaded") or 0) > 5_000_000)
        srv.derruba()
        srv.sobe()
        with httpx.Client(base_url=srv.url, timeout=60) as novo:
            job = novo.get(f"/jobs/{job_id}").json()
            assert job["status"] == "failed", f"após reinício: {job['status']}"
            assert "interrupt" in (job.get("error") or "").lower(), job.get("error")
            nova = novo.post(f"/jobs/{job_id}/retry")
            assert nova.status_code in (200, 201, 202), f"retry -> {nova.status_code} {nova.text[:200]}"
            novo.post(f"/jobs/{nova.json()['job_id']}/cancel")
        return "job marcado como interrompido; retry aceito"

    caso("servidor derrubado no meio da coleta", derrubado)

    # 5. entradas inválidas ------------------------------------------------------
    def invalidas(cli: httpx.Client) -> str:
        pedidos = [
            ("POST", "/jobs", {"source": "sinasc", "params": {"start_year": "abc"}}),
            ("POST", "/jobs", {"source": "sinasc", "params": {"start_year": 1500}}),
            ("POST", "/jobs", {"source": "sinasc", "params": {"start_year": 2020, "end_year": 2019}}),
            ("POST", "/jobs", {"source": "sinasc", "params": {"parametro_que_nao_existe": 1}}),
            ("POST", "/jobs", {"source": "sinasc", "params": {"states": ["XX"]}}),
            ("POST", "/jobs", {"source": "sinasc", "params": "texto"}),
            ("POST", "/jobs", {"params": {}}),
            ("POST", "/jobs", {"source": "snis", "params": {"results_url": "http://169.254.169.254/latest"}}),
            ("POST", "/sources/sinasc/discovery", {"params": {"start_year": "abc"}}),
            ("POST", "/sources/nao_existe/discovery", {"params": {}}),
            ("GET", "/jobs/../../etc/passwd", None),
            ("GET", "/jobs?limit=-5", None),
            ("GET", "/jobs?limit=abc", None),
            ("POST", "/jobs/nao_existe/cancel", None),
            ("POST", "/jobs/nao_existe/retry", None),
        ]
        ruins = []
        for metodo, rota, corpo in pedidos:
            resp = cli.request(metodo, rota, json=corpo)
            if resp.status_code >= 500 or resp.status_code < 400:
                ruins.append(f"{metodo} {rota} {json.dumps(corpo)[:60]} -> {resp.status_code}")
        assert not ruins, "; ".join(ruins)
        return f"{len(pedidos)} pedidos inválidos, todos 4xx"

    caso("entradas inválidas", invalidas)

    srv.derruba()
    saida = ROOT / "reports" / f"verificacao_resiliencia_{time.strftime('%Y%m%d_%H%M')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    falhas = [r for r in resultados if not r["ok"]]
    print(f"{len(resultados)} casos, {len(falhas)} falhas -> {saida}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
