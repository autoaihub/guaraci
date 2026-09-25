"""Coletas grandes de verdade, com tempo e pico de memória medidos.

Cada caso roda num processo próprio, então o pico medido é só dele. Os casos
cobrem os caminhos que mais pesam: arquivo de centenas de MB do portal, zip
do SISAGUA, o maior arquivo da ANVISA em SQLite, a API paginada do DEMAS até
o limite de páginas e um ano inteiro de SIH de um estado grande.

    python scripts/verificar_volume.py [--casos a,b] [--limite-mb 4096]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CASOS = {
    "srag_2024_csv": ("srag_arquivos", {"start_year": 2024, "end_year": 2024, "output_format": "csv"}),
    "srag_2024_sqlite": ("srag_arquivos", {"start_year": 2024, "end_year": 2024, "output_format": "sqlite"}),
    "sisagua_tratamento_parquet": ("sisagua_tratamento_agua", {"output_format": "parquet"}),
    "enani_csv": ("enani_2019", {"output_format": "csv"}),
    "enani_csv_keep_raw": ("enani_2019", {"output_format": "csv", "keep_raw": True}),
    "enani_parquet": ("enani_2019", {"output_format": "parquet"}),
    "enani_sqlite": ("enani_2019", {"output_format": "sqlite"}),
    "sisagua_mensal_basicos_parquet": ("sisagua_controle_mensal_parametros_basicos", {"output_format": "parquet"}),
    "sisagua_mensal_basicos_csv": ("sisagua_controle_mensal_parametros_basicos", {"output_format": "csv"}),
    "sisagua_mensal_basicos_sqlite": ("sisagua_controle_mensal_parametros_basicos", {"output_format": "sqlite"}),
    "vigimed_reacoes_sqlite": ("anvisa_vigimed_reacoes", {"output_format": "sqlite"}),
    "dengue_250_paginas": ("dengue", {"start_year": 2024, "end_year": 2024, "output_format": "parquet"}),
    "sih_sp_mes": ("sih", {"start_year": 2024, "end_year": 2024, "states": ["SP"], "months": ["1"],
                           "output_format": "parquet"}),
    "sih_sp_ano": ("sih", {"start_year": 2024, "end_year": 2024, "states": ["SP"], "output_format": "parquet"}),
}

# Roda dentro do processo filho: coleta e mede o pico de memória do próprio
# processo no fim (Windows: PeakWorkingSetSize; Linux: ru_maxrss).
_FILHO = r"""
import json, sys, time
from loguru import logger
logger.remove()
from guaraci.services.downloads import DownloadService
source, params = sys.argv[1], json.loads(sys.argv[2])
t0 = time.monotonic()
erro = None
try:
    r = DownloadService().run(source, **params).to_dict()
except Exception as exc:
    r, erro = {}, f"{type(exc).__name__}: {exc}"[:400]
segundos = time.monotonic() - t0
try:
    import ctypes
    from ctypes import wintypes
    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
    # Sem restype, o pseudo-handle -1 é truncado para 32 bits, a chamada falha
    # calada e o pico sai 0.
    atual = ctypes.windll.kernel32.GetCurrentProcess
    atual.restype = wintypes.HANDLE
    info = ctypes.windll.psapi.GetProcessMemoryInfo
    info.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    if not info(atual(), ctypes.byref(pmc), pmc.cb):
        raise OSError("GetProcessMemoryInfo falhou")
    pico = pmc.PeakWorkingSetSize
except Exception:
    import resource
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
print("RESULTADO " + json.dumps({"erro": erro, "segundos": round(segundos, 1), "pico_mb": round(pico / 1e6),
      "exportados": r.get("exported_files") or [], "aviso": r.get("export_warning"), "warnings": r.get("warnings")}))
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--casos", default="")
    parser.add_argument("--limite-mb", type=int, default=4096, help="pico de memória acima disto é falha")
    args = parser.parse_args()
    casos = {k: v for k, v in CASOS.items() if not args.casos or k in args.casos.split(",")}
    base = Path(tempfile.mkdtemp(prefix="guaraci_volume_"))
    env = dict(os.environ, GUARACI_DATA_ROOT=str(base / "data"))
    resultados = {}
    falhas = 0
    for nome, (source, params) in casos.items():
        params = dict(params, output_dir=str(base / nome))
        proc = subprocess.run([sys.executable, "-c", _FILHO, source, json.dumps(params)], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        linha = next((l for l in proc.stdout.splitlines() if l.startswith("RESULTADO ")), None)
        r = json.loads(linha[len("RESULTADO "):]) if linha else {"erro": (proc.stderr or proc.stdout)[-400:]}
        tamanhos = [Path(p).stat().st_size for p in r.get("exportados", []) if Path(p).exists()]
        r["exportado_mb"] = round(sum(tamanhos) / 1e6)
        problema = r.get("erro") or (None if r.get("exportados") else "nada exportado")
        if not problema and r.get("pico_mb", 0) > args.limite_mb:
            problema = f"pico de {r['pico_mb']} MB acima do limite"
        r["ok"] = not problema
        falhas += 0 if r["ok"] else 1
        resultados[nome] = r
        print(f"{'OK   ' if r['ok'] else 'FALHA'} {nome:<28} {r.get('segundos')}s  pico {r.get('pico_mb')} MB  "
              f"exportado {r['exportado_mb']} MB  {problema or ''} {r.get('aviso') or ''}", flush=True)
    saida = ROOT / "reports" / f"verificacao_volume_{time.strftime('%Y%m%d_%H%M')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)  # reports/ não vem no checkout
    saida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(casos)} casos, {falhas} falhas -> {saida}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
