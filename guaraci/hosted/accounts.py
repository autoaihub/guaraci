"""Contas, senhas, sessões e bloqueio de força bruta."""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from guaraci.hosted.db import Database

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
PASSWORD_MIN = 10
PASSWORD_MAX = 256
STATUSES = ("pending", "approved", "rejected", "disabled")

# Bloqueio de força bruta: depois de N falhas na janela, o tempo de espera
# dobra a cada nova falha, até o teto.
FAIL_WINDOW_SECONDS = 15 * 60
FAIL_THRESHOLD_EMAIL = 5
FAIL_THRESHOLD_IP = 20
LOCK_BASE_SECONDS = 60
LOCK_MAX_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: Optional[datetime] = None) -> str:
    return (moment or _now()).isoformat()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AccountError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class User:
    id: int
    email: str
    name: str
    institution: str
    purpose: str
    role: str
    status: str
    created_at: str
    approved_at: Optional[str]
    last_login_at: Optional[str]
    quota_jobs_day: Optional[int]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "institution": self.institution,
            "purpose": self.purpose,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "last_login_at": self.last_login_at,
            "quota_jobs_day": self.quota_jobs_day,
        }


@dataclass
class Session:
    token_hash: str
    user: User
    csrf_token: str
    expires_at: str


def _user_from_row(row) -> User:
    return User(
        id=int(row["id"]),
        email=row["email"],
        name=row["name"],
        institution=row["institution"],
        purpose=row["purpose"],
        role=row["role"],
        status=row["status"],
        created_at=row["created_at"],
        approved_at=row["approved_at"],
        last_login_at=row["last_login_at"],
        quota_jobs_day=row["quota_jobs_day"],
    )


class Accounts:
    def __init__(self, db: Database, *, session_ttl_hours: float = 12):
        self.db = db
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self._hasher = PasswordHasher()
        # Hash fictício: e-mail inexistente custa o mesmo tempo que senha errada.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))

    # -- validação -------------------------------------------------------
    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str) or not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
            raise AccountError(
                f"A senha precisa ter entre {PASSWORD_MIN} e {PASSWORD_MAX} caracteres."
            )
        if password.strip() != password or len(set(password)) < 5:
            raise AccountError("Escolha uma senha menos previsível.")

    @staticmethod
    def _clean(value: object, limit: int) -> str:
        text = str(value or "").strip()
        return text[:limit]

    # -- usuários --------------------------------------------------------
    def register(
        self,
        *,
        email: str,
        name: str,
        institution: str,
        purpose: str,
        password: str,
        consent_version: Optional[str],
        role: str = "user",
        status: str = "pending",
    ) -> Optional[User]:
        """Cria a conta. Devolve ``None`` se o e-mail já existe (sem revelar)."""
        email_norm = normalize_email(email)
        if not _EMAIL_RE.match(email_norm):
            raise AccountError("Informe um e-mail válido.")
        name_clean = self._clean(name, 120)
        if len(name_clean) < 2:
            raise AccountError("Informe seu nome.")
        self._validate_password(password)
        if self.db.one("SELECT 1 FROM users WHERE email = ?", (email_norm,)):
            return None
        now = _iso()
        cursor = self.db.execute(
            """INSERT INTO users (email, name, institution, purpose, password_hash, role,
                   status, created_at, approved_at, consent_version, consent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email_norm,
                name_clean,
                self._clean(institution, 200),
                self._clean(purpose, 1000),
                self._hasher.hash(password),
                role,
                status,
                now,
                now if status == "approved" else None,
                consent_version,
                now if consent_version else None,
            ),
        )
        return self.get(int(cursor.lastrowid))

    def get(self, user_id: int) -> Optional[User]:
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
        return _user_from_row(row) if row else None

    def get_by_email(self, email: str) -> Optional[User]:
        row = self.db.one("SELECT * FROM users WHERE email = ?", (normalize_email(email),))
        return _user_from_row(row) if row else None

    def list(self, status: Optional[str] = None) -> List[User]:
        if status:
            rows = self.db.all(
                "SELECT * FROM users WHERE status = ? ORDER BY created_at DESC", (status,)
            )
        else:
            rows = self.db.all("SELECT * FROM users ORDER BY created_at DESC")
        return [_user_from_row(row) for row in rows]

    def count_admins(self) -> int:
        row = self.db.one(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'approved'"
        )
        return int(row[0]) if row else 0

    def set_status(self, user_id: int, status: str, *, by: Optional[int] = None) -> User:
        if status not in STATUSES:
            raise AccountError(f"Status inválido: {status}")
        user = self.get(user_id)
        if user is None:
            raise AccountError("Usuário não encontrado.", status_code=404)
        if status == "approved":
            self.db.execute(
                "UPDATE users SET status = ?, approved_at = ?, approved_by = ? WHERE id = ?",
                (status, _iso(), by, user_id),
            )
        else:
            self.db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            self.revoke_user_sessions(user_id)
        return self.get(user_id)  # type: ignore[return-value]

    def set_role(self, user_id: int, role: str) -> User:
        if role not in {"user", "admin"}:
            raise AccountError(f"Papel inválido: {role}")
        self.db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        user = self.get(user_id)
        if user is None:
            raise AccountError("Usuário não encontrado.", status_code=404)
        return user

    def set_quota(self, user_id: int, quota_jobs_day: Optional[int]) -> User:
        self.db.execute(
            "UPDATE users SET quota_jobs_day = ? WHERE id = ?", (quota_jobs_day, user_id)
        )
        user = self.get(user_id)
        if user is None:
            raise AccountError("Usuário não encontrado.", status_code=404)
        return user

    def set_password(self, user_id: int, password: str) -> None:
        self._validate_password(password)
        self.db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (self._hasher.hash(password), user_id),
        )
        self.revoke_user_sessions(user_id)

    def delete(self, user_id: int) -> None:
        """Exclusão a pedido (LGPD): apaga a conta e desliga os eventos dela."""
        self.db.execute("UPDATE events SET user_id = NULL, ip = NULL, user_agent = NULL WHERE user_id = ?", (user_id,))
        self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))

    # -- login e bloqueio -----------------------------------------------
    def lock_seconds_remaining(self, email: str, ip: Optional[str]) -> int:
        now = time.time()
        since = now - FAIL_WINDOW_SECONDS
        worst = 0
        for column, key, threshold in (
            ("email", normalize_email(email), FAIL_THRESHOLD_EMAIL),
            ("ip", ip, FAIL_THRESHOLD_IP),
        ):
            if not key:
                continue
            row = self.db.one(
                f"SELECT COUNT(*), MAX(at) FROM login_failures WHERE {column} = ? AND at >= ?",
                (key, since),
            )
            count, last = (int(row[0]), row[1]) if row else (0, None)
            if count >= threshold and last is not None:
                lock = min(LOCK_MAX_SECONDS, LOCK_BASE_SECONDS * 2 ** (count - threshold))
                remaining = int(last + lock - now)
                worst = max(worst, remaining)
        return max(0, worst)

    def _record_failure(self, email: str, ip: Optional[str]) -> None:
        self.db.execute(
            "INSERT INTO login_failures (email, ip, at) VALUES (?, ?, ?)",
            (normalize_email(email), ip, time.time()),
        )

    def authenticate(self, email: str, password: str, ip: Optional[str]) -> User:
        """Confere a senha. Erros são genéricos para não revelar se a conta existe."""
        wait = self.lock_seconds_remaining(email, ip)
        if wait > 0:
            raise AccountError(
                f"Muitas tentativas. Tente de novo em {max(1, wait // 60)} minuto(s).",
                status_code=429,
            )
        row = self.db.one(
            "SELECT * FROM users WHERE email = ?", (normalize_email(email),)
        )
        stored = row["password_hash"] if row else self._dummy_hash
        try:
            self._hasher.verify(stored, password or "")
            ok = row is not None
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            ok = False
        if not ok:
            self._record_failure(email, ip)
            raise AccountError("E-mail ou senha incorretos.", status_code=401)
        user = _user_from_row(row)
        if self._hasher.check_needs_rehash(stored):
            self.db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self._hasher.hash(password), user.id),
            )
        self.db.execute("DELETE FROM login_failures WHERE email = ?", (user.email,))
        if user.status == "pending":
            raise AccountError(
                "Seu cadastro está aguardando aprovação de um administrador.", status_code=403
            )
        if user.status in {"rejected", "disabled"}:
            raise AccountError("Este acesso não está liberado.", status_code=403)
        self.db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_iso(), user.id))
        return self.get(user.id)  # type: ignore[return-value]

    # -- sessões ---------------------------------------------------------
    def create_session(self, user: User, *, ip: Optional[str], user_agent: Optional[str]) -> tuple[str, Session]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = _now()
        expires = now + self.session_ttl
        token_hash = hash_token(token)
        self.db.execute(
            """INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, expires_at,
                   last_seen_at, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (token_hash, user.id, csrf, _iso(now), _iso(expires), _iso(now), ip, (user_agent or "")[:300]),
        )
        return token, Session(token_hash=token_hash, user=user, csrf_token=csrf, expires_at=_iso(expires))

    def resolve_session(self, token: Optional[str]) -> Optional[Session]:
        if not token:
            return None
        token_hash = hash_token(token)
        row = self.db.one(
            """SELECT s.token_hash, s.csrf_token, s.expires_at, s.last_seen_at, u.*
               FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
            (token_hash,),
        )
        if row is None:
            return None
        now = _now()
        if datetime.fromisoformat(row["expires_at"]) <= now or row["status"] != "approved":
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            return None
        # Sessão deslizante: renova o prazo, no máximo uma vez por minuto.
        if now - datetime.fromisoformat(row["last_seen_at"]) > timedelta(minutes=1):
            self.db.execute(
                "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
                (_iso(now), _iso(now + self.session_ttl), token_hash),
            )
        return Session(
            token_hash=token_hash,
            user=_user_from_row(row),
            csrf_token=row["csrf_token"],
            expires_at=row["expires_at"],
        )

    def revoke_session(self, token_hash: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def revoke_user_sessions(self, user_id: int) -> None:
        self.db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def purge(self) -> None:
        self.db.execute("DELETE FROM sessions WHERE expires_at <= ?", (_iso(),))
        self.db.execute(
            "DELETE FROM login_failures WHERE at < ?", (time.time() - 24 * 3600,)
        )
