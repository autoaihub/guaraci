"""Limites da fila de coletas para o modo hospedado.

No modo local nenhuma política é passada ao ``DownloadJobService`` e a fila se
comporta como sempre: cada job vai direto ao executor. No modo hospedado a
política liga o revezamento entre usuários, as cotas e o corte por volume.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class JobPolicy:
    """Tetos aplicados pela fila. ``None`` desliga o teto correspondente."""

    # Revezamento: quantos jobs de um mesmo usuário rodam ao mesmo tempo.
    max_running_per_owner: Optional[int] = None
    # Jobs ativos (na fila ou rodando) por usuário.
    max_active_per_owner: Optional[int] = None
    # Jobs criados por usuário nas últimas 24 h.
    max_jobs_per_day: Optional[int] = None
    # Jobs ativos somando todos os usuários.
    max_active_global: Optional[int] = None
    # Corte por volume e por duração de uma coleta.
    max_job_bytes: Optional[int] = None
    max_job_seconds: Optional[float] = None
    # Piso de espaço livre no disco das saídas.
    min_free_disk_bytes: Optional[int] = None
    # Raiz das saídas. Com ela, cada job grava em ``<raiz>/users/<dono>/<job>``.
    output_root: Optional[Path] = None
    # Horas que o resultado fica disponível para download.
    output_ttl_hours: Optional[float] = None

    @property
    def fair_scheduling(self) -> bool:
        return self.max_running_per_owner is not None


class JobLimitError(Exception):
    """Pedido recusado por um teto da fila.

    ``status_code`` orienta a API: 429 para limite do usuário, 503 para
    limite do servidor (fila cheia, disco cheio), 413 para coleta grande demais.
    """

    def __init__(self, message: str, *, status_code: int = 429):
        super().__init__(message)
        self.status_code = status_code


class JobLimitExceeded(BaseException):
    """Interrompe uma coleta em andamento que passou do teto de volume ou tempo.

    Deriva de ``BaseException`` pelo mesmo motivo de ``JobCancelledError``:
    os ``except Exception`` por arquivo das datasources não podem engoli-la.
    """
