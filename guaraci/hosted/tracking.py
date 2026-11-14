"""Registro de acessos e uso, com os agregados do painel de administração.

Guarda login, telas visitadas, coletas e downloads com usuário, IP e
navegador. IP é dado pessoal (LGPD): depois de ``ip_retention_days`` ele é
reduzido à rede /24 (IPv4) ou /48 (IPv6) e o navegador vira só a família;
depois de ``event_retention_days`` o evento é apagado.
"""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from guaraci.hosted.db import Database

KINDS = {
    "signup",
    "login_ok",
    "login_fail",
    "lockout",
    "logout",
    "page_view",
    "discovery",
    "job_create",
    "job_rejected",
    "job_cancel",
    "job_retry",
    "download",
    "admin_action",
}

_VIEW_RE = re.compile(r"^[a-z0-9_\-:/.]{1,80}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def anonymize_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def browser_family(user_agent: Optional[str]) -> Optional[str]:
    if not user_agent:
        return None
    ua = user_agent.lower()
    for token, label in (
        ("edg/", "Edge"),
        ("opr/", "Opera"),
        ("firefox/", "Firefox"),
        ("chrome/", "Chrome"),
        ("safari/", "Safari"),
        ("curl/", "curl"),
        ("wget/", "wget"),
        ("python", "Python"),
    ):
        if token in ua:
            return label
    return "Outro"


def clean_view(view: object) -> Optional[str]:
    text = str(view or "").strip().lower()[:80]
    return text if _VIEW_RE.match(text) else None


class Tracker:
    def __init__(self, db: Database):
        self.db = db

    def record(
        self,
        kind: str,
        *,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        view: Optional[str] = None,
        source: Optional[str] = None,
        job_id: Optional[str] = None,
        meta: Optional[Dict[str, object]] = None,
    ) -> None:
        if kind not in KINDS:
            raise ValueError(f"Tipo de evento desconhecido: {kind}")
        self.db.execute(
            """INSERT INTO events (at, user_id, session_id, kind, view, source, job_id, ip,
                   user_agent, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _now().isoformat(),
                user_id,
                (session_id or "")[:16] or None,
                kind,
                view,
                (source or "")[:80] or None,
                job_id,
                ip,
                (user_agent or "")[:300] or None,
                json.dumps(meta, ensure_ascii=False)[:2000] if meta else None,
            ),
        )

    # -- painel -------------------------------------------------------------
    def stats(self, *, days: int = 30) -> Dict[str, object]:
        since = (_now() - timedelta(days=days)).isoformat()
        scalar = lambda sql, params=(): (self.db.one(sql, params) or [0])[0] or 0  # noqa: E731
        per_day = self.db.all(
            """SELECT substr(at, 1, 10) AS day,
                      COUNT(DISTINCT user_id) AS users,
                      COUNT(DISTINCT CASE WHEN user_id IS NULL THEN ip END) AS anon_ips,
                      SUM(kind = 'page_view') AS views,
                      SUM(kind = 'job_create') AS jobs,
                      SUM(kind = 'download') AS downloads
               FROM events WHERE at >= ? GROUP BY day ORDER BY day""",
            (since,),
        )
        top_sources = self.db.all(
            """SELECT source, COUNT(*) AS n FROM events
               WHERE kind = 'job_create' AND at >= ? AND source IS NOT NULL
               GROUP BY source ORDER BY n DESC LIMIT 15""",
            (since,),
        )
        top_views = self.db.all(
            """SELECT view, COUNT(*) AS n, COUNT(DISTINCT user_id) AS users FROM events
               WHERE kind = 'page_view' AND at >= ? AND view IS NOT NULL
               GROUP BY view ORDER BY n DESC LIMIT 20""",
            (since,),
        )
        return {
            "days": days,
            "users_total": scalar("SELECT COUNT(*) FROM users"),
            "users_pending": scalar("SELECT COUNT(*) FROM users WHERE status = 'pending'"),
            "users_approved": scalar("SELECT COUNT(*) FROM users WHERE status = 'approved'"),
            "active_users": scalar(
                "SELECT COUNT(DISTINCT user_id) FROM events WHERE at >= ? AND user_id IS NOT NULL",
                (since,),
            ),
            "distinct_ips": scalar(
                "SELECT COUNT(DISTINCT ip) FROM events WHERE at >= ? AND ip IS NOT NULL", (since,)
            ),
            "logins": scalar(
                "SELECT COUNT(*) FROM events WHERE kind = 'login_ok' AND at >= ?", (since,)
            ),
            "login_failures": scalar(
                "SELECT COUNT(*) FROM events WHERE kind IN ('login_fail','lockout') AND at >= ?",
                (since,),
            ),
            "jobs": scalar(
                "SELECT COUNT(*) FROM events WHERE kind = 'job_create' AND at >= ?", (since,)
            ),
            "jobs_rejected": scalar(
                "SELECT COUNT(*) FROM events WHERE kind = 'job_rejected' AND at >= ?", (since,)
            ),
            "downloads": scalar(
                "SELECT COUNT(*) FROM events WHERE kind = 'download' AND at >= ?", (since,)
            ),
            "per_day": [dict(row) for row in per_day],
            "top_sources": [dict(row) for row in top_sources],
            "top_views": [dict(row) for row in top_views],
        }

    def journey(
        self, *, user_id: Optional[int] = None, session_id: Optional[str] = None, limit: int = 500
    ) -> List[Dict[str, object]]:
        if user_id is None and not session_id:
            raise ValueError("Informe user_id ou session_id.")
        if user_id is not None:
            rows = self.db.all(
                "SELECT * FROM events WHERE user_id = ? ORDER BY at DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            rows = self.db.all(
                "SELECT * FROM events WHERE session_id = ? ORDER BY at DESC LIMIT ?",
                (session_id, limit),
            )
        items = []
        for row in rows:
            item = dict(row)
            if item.get("meta"):
                try:
                    item["meta"] = json.loads(item["meta"])
                except ValueError:
                    pass
            items.append(item)
        return items

    def recent(self, *, limit: int = 200, kind: Optional[str] = None) -> List[Dict[str, object]]:
        if kind:
            rows = self.db.all(
                """SELECT e.*, u.email FROM events e LEFT JOIN users u ON u.id = e.user_id
                   WHERE e.kind = ? ORDER BY e.at DESC LIMIT ?""",
                (kind, limit),
            )
        else:
            rows = self.db.all(
                """SELECT e.*, u.email FROM events e LEFT JOIN users u ON u.id = e.user_id
                   ORDER BY e.at DESC LIMIT ?""",
                (limit,),
            )
        return [dict(row) for row in rows]

    # -- retenção -------------------------------------------------------------
    def apply_retention(self, *, ip_days: int, event_days: int) -> Dict[str, int]:
        now = _now()
        ip_cutoff = (now - timedelta(days=ip_days)).isoformat()
        event_cutoff = (now - timedelta(days=event_days)).isoformat()
        deleted = self.db.execute("DELETE FROM events WHERE at < ?", (event_cutoff,)).rowcount
        rows = self.db.all(
            """SELECT id, ip, user_agent FROM events
               WHERE at < ? AND ((ip IS NOT NULL AND ip NOT LIKE '%/%') OR
                                 (user_agent IS NOT NULL AND user_agent NOT IN
                                  ('Edge','Opera','Firefox','Chrome','Safari','curl','wget','Python','Outro')))""",
            (ip_cutoff,),
        )
        for row in rows:
            self.db.execute(
                "UPDATE events SET ip = ?, user_agent = ? WHERE id = ?",
                (anonymize_ip(row["ip"]), browser_family(row["user_agent"]), row["id"]),
            )
        self.db.execute(
            "UPDATE sessions SET ip = NULL WHERE created_at < ?", (ip_cutoff,)
        )
        return {"deleted": int(deleted or 0), "anonymized": len(rows)}
