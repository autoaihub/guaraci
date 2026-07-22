"""Publish a small aggregates file next to the download-jobs store.

Reads ``data/jobs/download_jobs.json`` (the raw job list written by the API)
and writes ``data/jobs/agregados.json`` with a handful of summary numbers:
distinct sources, job counts by outcome, failure rate and a timestamp.

Why: the Ninho do Vogel panel (an external dashboard) reads this file to show
"vital signs" for guaraci on its project card. The raw job list has no
aggregates, so this utility publishes them without touching the API/sources.
It is a pure read -> write; safe to run any time (manually, at the end of a job
run, or on a schedule). If the job store is missing it exits quietly.

Both files live under ``data/`` which is gitignored (runtime data), so this
script produces no versioned artifact — only the script itself is code.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JOBS_FILE = REPO_ROOT / "data" / "jobs" / "download_jobs.json"
OUT_FILE = REPO_ROOT / "data" / "jobs" / "agregados.json"

# job["status"] values considered a success (everything else counts as failure)
_OK_STATUSES = {"completed"}


def compute(jobs: list[dict]) -> dict:
    total = len(jobs)
    ok = sum(1 for j in jobs if str(j.get("status")) in _OK_STATUSES)
    falha = total - ok
    fontes = {j.get("source") for j in jobs if j.get("source")}
    pct = round(100.0 * falha / total, 1) if total else 0.0
    return {
        "fontes_distintas": len(fontes),
        "jobs_total": total,
        "jobs_ok": ok,
        "jobs_falha": falha,
        "pct_falha": pct,
        "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    if not JOBS_FILE.exists():
        print(f"no job store at {JOBS_FILE} — nothing to publish")
        return 0
    try:
        jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"could not read {JOBS_FILE}: {exc}")
        return 1
    if not isinstance(jobs, list):
        print(f"unexpected job store shape ({type(jobs).__name__}); expected a list")
        return 1

    agg = compute(jobs)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT_FILE)  # atomic on the same volume
    print(f"wrote {OUT_FILE}: {agg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
