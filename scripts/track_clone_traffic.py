"""Acumula permanentemente as clonagens dos repositórios do dono deste repo.

A API de tráfego do GitHub (`/traffic/clones`) só retém **14 dias**. Este script
descobre os repositórios em que o token tem acesso de push, consulta a API de
cada um, funde a janela dia a dia com o histórico já gravado e mantém o total
acumulado desde a primeira execução. Todo o histórico é centralizado aqui, nos
arquivos de `.github/traffic/`; os outros repositórios não são modificados.

Arquivos gerados (em `.github/traffic/`):
- `clones.json`         : histórico do Guaraci (caminho legado, alimenta o badge do README).
- `clones-badge.json`   : payload no formato *endpoint* do shields.io para o Guaraci.
- `repos/<owner>--<repo>.json` : histórico de cada um dos demais repositórios.
- `summary.json`        : totais por repositório mais o agregado da conta.
- `summary.md`          : a mesma tabela em Markdown, para leitura humana.

Clonagens do próprio CI: cada `actions/checkout` de um workflow conta como uma
clonagem na API de tráfego. Para cada dia, o script também conta os checkouts
feitos pelas Actions do repositório (campo `ci` do dia, `total_ci` no acumulado).
Por ora é só registro: `total_clones` e o badge seguem com o número bruto da API.
A contagem reconhece o passo pelo nome ("checkout" em qualquer caixa); um passo
de checkout renomeado sem essa palavra fica de fora, e o clone de submódulos
conta no repositório do submódulo, não aqui. Por isso `ci` é um piso. Os logs das
Actions somem depois de 90 dias, e dias mais antigos que isso ficam sem `ci`.

Autenticação: os endpoints de tráfego exigem permissão de *push*, e o
`GITHUB_TOKEN` padrão das Actions **não** basta. Defina o secret `TRAFFIC_TOKEN`
com um PAT clássico de escopo `repo`. Um token *fine-grained* pertence a um único
dono, então não alcança ao mesmo tempo os repositórios pessoais e os da
organização; nesse caso o script registra o repositório como inacessível e segue.

Variáveis de ambiente opcionais:
- `TRAFFIC_REPOS`   : lista fixa `owner/nome` separada por vírgula, no lugar da descoberta.
- `TRAFFIC_EXCLUDE` : lista `owner/nome` separada por vírgula a ignorar.
- `TRAFFIC_ALWAYS`  : repositórios a incluir sempre, mesmo fora da descoberta.

Uso:
    TRAFFIC_TOKEN=ghp_... python scripts/track_clone_traffic.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".github" / "traffic"
REPOS_DIR = OUT_DIR / "repos"
BADGE = OUT_DIR / "clones-badge.json"
SUMMARY_JSON = OUT_DIR / "summary.json"
SUMMARY_MD = OUT_DIR / "summary.md"

HOME_REPO = "autoaihub/guaraci"
# O histórico do Guaraci nasceu em `clones.json`, e o badge do README aponta para
# lá. Mantemos esse caminho para não quebrar o link nem perder a série semeada.
LEGACY_PATHS = {HOME_REPO: OUT_DIR / "clones.json"}

BADGE_COLOR = "1f6feb"
API = "https://api.github.com"


def _token() -> str:
    for var in ("TRAFFIC_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    sys.exit("erro: defina TRAFFIC_TOKEN (PAT com acesso de push aos repositórios).")


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _request(url: str, token: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "guaraci-clone-tracker",
        },
    )


def get_json(url: str, token: str):
    """GET numa URL da API. Levanta `urllib.error.HTTPError` no erro."""
    with urllib.request.urlopen(_request(url, token), timeout=30) as response:
        return json.load(response)


def history_path(repo: str) -> Path:
    if repo in LEGACY_PATHS:
        return LEGACY_PATHS[repo]
    owner, _, name = repo.partition("/")
    return REPOS_DIR / f"{owner}--{name}.json"


def discover_repos(token: str) -> list[str]:
    """Repositórios em que o token tem push, que é o que a API de tráfego exige.

    A descoberta cobre os repositórios próprios e os das organizações de que o
    usuário participa. Repositórios de terceiros em que ele é apenas colaborador
    ficam de fora, porque o tráfego deles é dado do dono; para acompanhar algum,
    liste em `TRAFFIC_ALWAYS`. Repositórios sem push também são descartados: a
    API responderia 403 para eles.
    """
    repos: list[str] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "affiliation": "owner,organization_member",
                "per_page": 100,
                "page": page,
            }
        )
        batch = get_json(f"{API}/user/repos?{query}", token)
        if not batch:
            break
        for repo in batch:
            if (repo.get("permissions") or {}).get("push"):
                repos.append(repo["full_name"])
        if len(batch) < 100:
            break
        page += 1
    return repos


def target_repos(token: str) -> list[str]:
    fixed = _env_list("TRAFFIC_REPOS")
    repos = fixed if fixed else discover_repos(token)

    always = _env_list("TRAFFIC_ALWAYS") or [HOME_REPO]
    for repo in always:
        if repo not in repos:
            repos.append(repo)

    excluded = set(_env_list("TRAFFIC_EXCLUDE"))
    # Preserva quem já tem histórico gravado: perder um repo da lista de
    # descoberta não deve apagar a série dele.
    for path in sorted(REPOS_DIR.glob("*.json")) if REPOS_DIR.exists() else []:
        owner, _, name = path.stem.partition("--")
        known = f"{owner}/{name}"
        if known not in repos:
            repos.append(known)

    return sorted({repo for repo in repos if repo not in excluded})


def fetch_clones(repo: str, token: str) -> dict:
    """Retorna o payload de `/traffic/clones` (janela de 14 dias, granularidade diária)."""
    return get_json(f"{API}/repos/{repo}/traffic/clones?per=day", token)


def load_history(repo: str) -> dict:
    path = history_path(repo)
    if not path.exists():
        return {"repo": repo, "days": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("repo", repo)
    data.setdefault("days", {})
    return data


def _get_pages(url: str, token: str, key: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        batch = get_json(f"{url}{sep}per_page=100&page={page}", token).get(key, [])
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def fetch_ci_checkouts(repo: str, token: str, since: str) -> dict[str, int]:
    """Checkouts feitos pelas Actions do repositório, por dia, desde `since`.

    Conta os passos de checkout concluídos com sucesso em todas as tentativas
    de cada execução (uma reexecução clona de novo). O passo `Post ...` é a
    limpeza do checkout e não clona.
    """
    runs = _get_pages(
        f"{API}/repos/{repo}/actions/runs?created=%3E%3D{since}", token, "workflow_runs"
    )
    per_day: dict[str, int] = {}
    for run in runs:
        jobs = _get_pages(
            f"{API}/repos/{repo}/actions/runs/{run['id']}/jobs?filter=all", token, "jobs"
        )
        for job in jobs:
            day = (job.get("started_at") or run["created_at"])[:10]
            for step in job.get("steps") or []:
                name = step.get("name", "")
                if (
                    "checkout" in name.lower()
                    and not name.startswith("Post ")
                    and step.get("conclusion") == "success"
                ):
                    per_day[day] = per_day.get(day, 0) + 1
    return per_day


def ci_since(history: dict, payload: dict) -> str | None:
    """Primeiro dia cuja contagem de CI precisa ser (re)calculada.

    Recalcula sempre a janela corrente da API e, além dela, qualquer dia do
    histórico que ainda não tenha o campo `ci` dentro da retenção das Actions.
    """
    window = [entry["timestamp"][:10] for entry in payload.get("clones", [])]
    retention = (_today() - datetime.timedelta(days=90)).isoformat()
    missing = [d for d, v in history["days"].items() if "ci" not in v and d >= retention]
    candidates = window + missing
    return min(candidates) if candidates else None


def merge(history: dict, payload: dict, ci: dict[str, int] | None = None) -> dict:
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
        if "ci" in previous:
            days[day]["ci"] = previous["ci"]

    if ci is not None:
        since = min(ci) if ci else None
        for day, value in days.items():
            if day in ci:
                value["ci"] = max(value.get("ci", 0), ci[day])
            elif since is not None and day >= since:
                value.setdefault("ci", 0)

    history["days"] = dict(sorted(days.items()))
    history["total_clones"] = sum(d["count"] for d in days.values())
    history["total_uniques"] = sum(d["uniques"] for d in days.values())
    history["total_ci"] = sum(d.get("ci", 0) for d in days.values())
    history["tracking_since"] = next(iter(history["days"]), None)
    history["updated_at"] = _now()
    return history


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def write_summary(entries: list[dict], failures: list[dict]) -> dict:
    entries = sorted(entries, key=lambda e: (-e["total_clones"], e["repo"]))
    summary = {
        "updated_at": _now(),
        "repo_count": len(entries),
        "total_clones": sum(e["total_clones"] for e in entries),
        "total_uniques": sum(e["total_uniques"] for e in entries),
        "total_ci": sum(e["total_ci"] for e in entries),
        "repos": entries,
        "unreachable": failures,
    }
    write_json(SUMMARY_JSON, summary)

    lines = [
        "# Clonagens acumuladas",
        "",
        f"Atualizado em {summary['updated_at']}. "
        f"{summary['total_clones']} clonagens ({summary['total_uniques']} únicas) "
        f"em {summary['repo_count']} repositórios. Dessas, ao menos "
        f"{summary['total_ci']} vieram do checkout das próprias Actions (coluna CI).",
        "",
        "| Repositório | Clonagens | Únicas | CI | Desde |",
        "| --- | --: | --: | --: | --- |",
    ]
    for entry in entries:
        lines.append(
            f"| {entry['repo']} | {entry['total_clones']} | "
            f"{entry['total_uniques']} | {entry['total_ci']} | "
            f"{entry['tracking_since'] or 'n/d'} |"
        )
    if failures:
        lines += ["", "## Inacessíveis", ""]
        lines += [f"- {f['repo']}: {f['error']}" for f in failures]
    lines.append("")
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    return summary


def main() -> int:
    token = _token()
    try:
        repos = target_repos(token)
    except urllib.error.HTTPError as exc:
        sys.exit(f"erro: não foi possível listar os repositórios ({exc.code}).")

    entries: list[dict] = []
    failures: list[dict] = []

    for repo in repos:
        try:
            payload = fetch_clones(repo, token)
        except urllib.error.HTTPError as exc:
            # Um repositório fora do alcance do token não pode derrubar os outros.
            reason = f"HTTP {exc.code}"
            failures.append({"repo": repo, "error": reason})
            print(f"aviso: {repo} inacessível ({reason})", file=sys.stderr)
            continue

        history = load_history(repo)
        ci = None
        since = ci_since(history, payload)
        if since:
            try:
                ci = fetch_ci_checkouts(repo, token, since)
                # Dias da janela sem nenhuma execução também ficam registrados.
                ci.setdefault(since, 0)
            except urllib.error.HTTPError as exc:
                # Sem acesso às Actions o tráfego ainda vale; só a coluna CI falta.
                print(f"aviso: {repo} sem contagem de CI (HTTP {exc.code})", file=sys.stderr)

        history = merge(history, payload, ci)
        write_json(history_path(repo), history)
        entries.append(
            {
                "repo": repo,
                "total_clones": history["total_clones"],
                "total_uniques": history["total_uniques"],
                "total_ci": history["total_ci"],
                "tracking_since": history["tracking_since"],
            }
        )
        print(
            f"{repo}: {history['total_clones']} clonagens acumuladas "
            f"({history['total_uniques']} únicas, {history['total_ci']} do CI) "
            f"desde {history['tracking_since']}"
        )

    if not entries:
        sys.exit("erro: nenhum repositório pôde ser consultado; verifique o token.")

    summary = write_summary(entries, failures)

    home = next((e for e in entries if e["repo"] == HOME_REPO), None)
    if home:
        write_json(
            BADGE,
            {
                "schemaVersion": 1,
                "label": "clones",
                "message": f"{home['total_clones']} total ({home['total_uniques']} únicos)",
                "color": BADGE_COLOR,
            },
        )

    print(
        f"total: {summary['total_clones']} clonagens "
        f"({summary['total_uniques']} únicas) em {summary['repo_count']} repositórios"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
