"""Configuração do modo hospedado, lida das variáveis de ambiente.

``GUARACI_MODE=local`` (padrão) mantém o Guaraci como sempre foi: sem login,
sem rastreamento. ``GUARACI_MODE=hosted`` liga o serviço multiusuário e exige
segredo, raiz de saídas e banco configurados.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from guaraci.services.job_policy import JobPolicy

_GB = 1024**3


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw is not None else default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "sim", "on"}


@dataclass(frozen=True)
class HostedSettings:
    mode: str = "local"
    secret_key: str = ""
    output_root: Optional[Path] = None
    db_path: Path = Path("data/guaraci.db")
    # Fila
    max_running: int = 2
    max_running_per_user: int = 1
    max_active_per_user: int = 3
    max_jobs_per_day: int = 10
    max_active_global: int = 40
    max_job_bytes: int = 2 * _GB
    max_job_seconds: float = 2 * 3600
    min_free_disk_bytes: int = 5 * _GB
    output_ttl_hours: float = 48
    # Sessão e cookies
    session_ttl_hours: float = 12
    cookie_secure: bool = True
    # LGPD: retenção de IP e de eventos
    ip_retention_days: int = 30
    event_retention_days: int = 365
    privacy_version: str = "2026-11"
    # Origem pública, usada na checagem de Origin (ex.: https://guaraci.sabiadatalake.com.br)
    public_origin: Optional[str] = None
    # Contato para pedidos de titulares (LGPD), mostrado na política de privacidade.
    contact: Optional[str] = None
    # Rate limit (requisições por minuto, por IP) e por hora em rotas caras
    rate_ip_per_minute: int = 120
    rate_auth_per_minute: int = 10
    rate_signup_per_hour: int = 5
    rate_discovery_per_hour: int = 30
    rate_jobs_per_hour: int = 30
    janitor_interval_seconds: int = 900
    extra_public_paths: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def hosted(self) -> bool:
        return self.mode == "hosted"

    @classmethod
    def from_env(cls) -> "HostedSettings":
        mode = (_env("GUARACI_MODE", "local") or "local").lower()
        if mode not in {"local", "hosted"}:
            raise RuntimeError(f"GUARACI_MODE inválido: {mode!r} (use local ou hosted).")
        output_root_raw = _env("GUARACI_OUTPUT_ROOT")
        data_root = Path(_env("GUARACI_DATA_ROOT", "data") or "data")
        return cls(
            mode=mode,
            secret_key=_env("GUARACI_SECRET_KEY", "") or "",
            output_root=Path(output_root_raw).expanduser() if output_root_raw else None,
            db_path=Path(_env("GUARACI_DB_PATH", str(data_root / "guaraci.db")) or ""),
            max_running=_env_int("GUARACI_MAX_RUNNING", 2),
            max_running_per_user=_env_int("GUARACI_MAX_RUNNING_PER_USER", 1),
            max_active_per_user=_env_int("GUARACI_MAX_ACTIVE_PER_USER", 3),
            max_jobs_per_day=_env_int("GUARACI_MAX_JOBS_PER_DAY", 10),
            max_active_global=_env_int("GUARACI_MAX_ACTIVE_GLOBAL", 40),
            max_job_bytes=int(_env_float("GUARACI_MAX_JOB_GB", 2) * _GB),
            max_job_seconds=_env_float("GUARACI_MAX_JOB_MINUTES", 120) * 60,
            min_free_disk_bytes=int(_env_float("GUARACI_MIN_FREE_DISK_GB", 5) * _GB),
            output_ttl_hours=_env_float("GUARACI_OUTPUT_TTL_HOURS", 48),
            session_ttl_hours=_env_float("GUARACI_SESSION_TTL_HOURS", 12),
            cookie_secure=_env_bool("GUARACI_COOKIE_SECURE", True),
            ip_retention_days=_env_int("GUARACI_IP_RETENTION_DAYS", 30),
            event_retention_days=_env_int("GUARACI_EVENT_RETENTION_DAYS", 365),
            public_origin=_env("GUARACI_PUBLIC_ORIGIN"),
            contact=_env("GUARACI_CONTACT"),
            rate_ip_per_minute=_env_int("GUARACI_RATE_IP_PER_MINUTE", 120),
            rate_auth_per_minute=_env_int("GUARACI_RATE_AUTH_PER_MINUTE", 10),
            rate_signup_per_hour=_env_int("GUARACI_RATE_SIGNUP_PER_HOUR", 5),
            rate_discovery_per_hour=_env_int("GUARACI_RATE_DISCOVERY_PER_HOUR", 30),
            rate_jobs_per_hour=_env_int("GUARACI_RATE_JOBS_PER_HOUR", 30),
            janitor_interval_seconds=_env_int("GUARACI_JANITOR_SECONDS", 900),
        )

    def validate(self) -> None:
        """Recusa subir o modo hospedado com configuração insegura."""
        if not self.hosted:
            return
        problems = []
        if len(self.secret_key) < 32:
            problems.append("GUARACI_SECRET_KEY ausente ou curta (mínimo 32 caracteres).")
        if self.output_root is None:
            problems.append("GUARACI_OUTPUT_ROOT não definido.")
        if problems:
            raise RuntimeError("Modo hospedado mal configurado: " + " ".join(problems))

    def job_policy(self) -> JobPolicy:
        if not self.hosted:
            return JobPolicy()
        return JobPolicy(
            max_running_per_owner=self.max_running_per_user,
            max_active_per_owner=self.max_active_per_user,
            max_jobs_per_day=self.max_jobs_per_day,
            max_active_global=self.max_active_global,
            max_job_bytes=self.max_job_bytes,
            max_job_seconds=self.max_job_seconds,
            min_free_disk_bytes=self.min_free_disk_bytes,
            output_root=self.output_root,
            output_ttl_hours=self.output_ttl_hours,
        )
