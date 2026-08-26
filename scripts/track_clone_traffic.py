"""Acumula permanentemente as clonagens do repositório Guaraci.

A API de tráfego do GitHub (`/traffic/clones`) só retém **14 dias**. Este script
consulta a API, faz o merge dia a dia com o histórico já gravado e mantém o
total acumulado desde a primeira execução.

Arquivos gerados (em `.github/traffic/`):
- `clones.json`        — histórico completo: total acumulado + contagem por dia.
- `clones-badge.json`  — payload no formato *endpoint* do shields.io (badge do README).

Autenticação: os endpoints de tráfego exigem permissão de *push*, e o
`GITHUB_TOKEN` padrão das Actions **não** basta. Defina o secret `TRAFFIC_TOKEN`
com um PAT de escopo `repo` (clássico) ou *fine-grained* com permissão
`Administration: read`.

Uso:
    GITHUB_REPOSITORY=autoaihub/guaraci TRAFFIC_TOKEN=ghp_... \\
        python scripts/track_clone_traffic.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".github" / "traffic"
HISTORY = OUT_DIR / "clones.json"
BADGE = OUT_DIR / "clones-badge.json"

DEFAULT_REPO = "autoaihub/guaraci"
BADGE_COLOR = "1f6feb"


def _token() -> str:
    for var in ("TRAFFIC_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    sys.exit("erro: defina TRAFFIC_TOKEN (PAT com acesso de push ao repositório).")


def fetch_clones(repo: str, token: str) -> dict:
    """Retorna o payload de `/traffic/clones` (janela de 14 dias, granularidade diária)."""
    url = f"https://api.github.com/repos/{repo}/traffic/clones?per=day"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "guaraci-clone-tracker",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:  # 403 = token sem permissão de push
        body = exc.read().decode("utf-8", "replace")[:300]
        sys.exit(f"erro: GitHub respondeu {exc.code} para {url}\n{body}")


def load_history(repo: str) -> dict:
    if not HISTORY.exists():
        return {"repo": repo, "days": {}}
    data = json.loads(HISTORY.read_text(encoding="utf-8"))
    data.setdefault("repo", repo)
    data.setdefault("days", {})
    return data


def merge(history: dict, payload: dict) -> dict:
    """Funde a janela de 14 dias no histórico.

    Cada dia guarda o maior valor já visto: a contagem do dia corrente ainda
    cresce até a virada do dia, e reexecuções não podem reduzir o acumulado.
    """
    days = history["days"]
    for entry in payload.get("clones", []):
        day = entry["timestamp"][:10]
        previous = days.get(day, {"count": 0, "uniques": 0})
        days[day] = {
            "count": max(previous.get("count", 0), int(entry.get("count", 0))),
            "uniques": max(previous.get("uniques", 0), int(entry.get("uniques", 0))),
        }

    history["days"] = dict(sorted(days.items()))
    history["total_clones"] = sum(d["count"] for d in days.values())
    history["total_uniques"] = sum(d["uniques"] for d in days.values())
    history["tracking_since"] = next(iter(history["days"]), None)
    history["updated_at"] = (
        datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    )
    return history


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    history = merge(load_history(repo), fetch_clones(repo, _token()))

    write_json(HISTORY, history)
    write_json(
        BADGE,
        {
            "schemaVersion": 1,
            "label": "clones",
            "message": f"{history['total_clones']} total ({history['total_uniques']} únicos)",
            "color": BADGE_COLOR,
        },
    )

    print(
        f"{repo}: {history['total_clones']} clonagens acumuladas "
        f"({history['total_uniques']} únicas) desde {history['tracking_since']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
