"""Limite de requisições em memória (balde de fichas).

O Guaraci hospedado roda num processo só (a fila de jobs vive nele), então a
memória do processo basta. Cada chave (escopo + IP ou usuário) tem um balde
com ``capacity`` fichas que se repõem à taxa ``capacity / period``.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Tuple


class RateLimiter:
    def __init__(self, max_keys: int = 50_000):
        self._buckets: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def hit(self, scope: str, key: str, *, capacity: int, period: float) -> float:
        """Consome uma ficha. Devolve 0 se liberado, senão os segundos de espera."""
        if capacity <= 0:
            return 0.0
        now = time.monotonic()
        rate = capacity / period
        with self._lock:
            tokens, last = self._buckets.get((scope, key), (float(capacity), now))
            tokens = min(float(capacity), tokens + (now - last) * rate)
            if tokens < 1.0:
                self._buckets[(scope, key)] = (tokens, now)
                return (1.0 - tokens) / rate
            self._buckets[(scope, key)] = (tokens - 1.0, now)
            if len(self._buckets) > self._max_keys:
                self._evict(now)
            return 0.0

    def _evict(self, now: float) -> None:
        # Descarta os baldes parados há mais de uma hora (já estariam cheios).
        stale = [key for key, (_, last) in self._buckets.items() if now - last > 3600]
        for key in stale:
            self._buckets.pop(key, None)
        if len(self._buckets) > self._max_keys:
            self._buckets.clear()
