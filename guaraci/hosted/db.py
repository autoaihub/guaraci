"""Banco SQLite do modo hospedado (usuários, sessões, eventos).

Um processo só usa o banco, então uma conexão compartilhada protegida por
trava basta. WAL deixa leitura e escrita conviverem sem bloqueio longo.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

_MIGRATIONS: Sequence[str] = (
    # 1: esquema inicial
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        institution TEXT NOT NULL DEFAULT '',
        purpose TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        approved_at TEXT,
        approved_by INTEGER,
        last_login_at TEXT,
        consent_version TEXT,
        consent_at TEXT,
        quota_jobs_day INTEGER,
        notes TEXT
    );
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        ip TEXT,
        user_agent TEXT
    );
    CREATE INDEX idx_sessions_user ON sessions(user_id);
    CREATE TABLE login_failures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        ip TEXT,
        at REAL NOT NULL
    );
    CREATE INDEX idx_login_failures_email ON login_failures(email, at);
    CREATE INDEX idx_login_failures_ip ON login_failures(ip, at);
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        user_id INTEGER,
        session_id TEXT,
        kind TEXT NOT NULL,
        view TEXT,
        source TEXT,
        job_id TEXT,
        ip TEXT,
        user_agent TEXT,
        meta TEXT
    );
    CREATE INDEX idx_events_at ON events(at);
    CREATE INDEX idx_events_user ON events(user_id, at);
    CREATE INDEX idx_events_kind ON events(kind, at);
    """,
)


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None, timeout=30
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(self.path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            for index, script in enumerate(_MIGRATIONS[version:], start=version + 1):
                self._conn.execute("BEGIN")
                for statement in [part.strip() for part in script.split(";") if part.strip()]:
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {index}")
                self._conn.execute("COMMIT")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def all(self, sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    def backup_to(self, target: Path | str) -> None:
        with self._lock:
            dest = sqlite3.connect(str(target))
            try:
                self._conn.backup(dest)
            finally:
                dest.close()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
