"""Medida de memória e disco para as baterias de ``scripts/verificar_*.py``.

O runner do GitHub cai sem deixar mensagem da aplicação quando falta memória
ou disco ("The runner has received a shutdown signal", código 143), e o log
não diz qual fonte estava em curso. ``Vigia`` imprime, a cada intervalo, uma
linha com a memória do processo, a memória livre da máquina, o disco livre, o
tamanho da pasta temporária e as fontes em andamento; a última linha antes da
queda aponta a culpada. ``print`` sempre com flush: com a saída ligada a um
pipe (``| tee``) o Python acumula em bloco, e o que estava no buffer se perde
junto com o runner.

Só usa a biblioteca padrão (``/proc`` no Linux); com ``psutil`` instalado
mede também no Windows e no macOS.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

__all__ = ["Vigia", "agora", "pasta_mb", "registra"]

_MB = 1024 * 1024


def registra(texto: str) -> None:
    """Imprime e descarrega o buffer na hora."""
    # Uma só escrita: duas threads imprimindo juntas não colam linhas.
    print(texto + "\n", end="", flush=True)


def _kb(linhas: str, chave: str) -> Optional[int]:
    for linha in linhas.splitlines():
        if linha.startswith(chave + ":"):
            return int(linha.split()[1])
    return None


def agora(raiz: Optional[Path] = None) -> Dict[str, Optional[float]]:
    """Memória do processo (atual e pico), memória disponível e disco livre, em MB."""
    rss = pico = livre = None
    try:
        status = Path("/proc/self/status").read_text()
        rss, pico = _kb(status, "VmRSS"), _kb(status, "VmHWM")
        rss = rss / 1024 if rss is not None else None
        pico = pico / 1024 if pico is not None else None
        livre = _kb(Path("/proc/meminfo").read_text(), "MemAvailable")
        livre = livre / 1024 if livre is not None else None
    except OSError:
        try:
            import psutil

            rss = psutil.Process().memory_info().rss / _MB
            livre = psutil.virtual_memory().available / _MB
        except Exception:  # noqa: BLE001  (sem psutil, o campo fica vazio)
            pass
    try:
        disco = shutil.disk_usage(raiz or Path.cwd()).free / _MB
    except OSError:
        disco = None
    return {"rss": rss, "pico": pico, "livre": livre, "disco": disco}


def pasta_mb(pasta: Path) -> float:
    """Tamanho em MB de tudo o que está sob a pasta (0 se ela não existe)."""
    total = 0
    try:
        for arq in pasta.rglob("*"):
            try:
                if arq.is_file():
                    total += arq.stat().st_size
            except OSError:
                continue  # arquivo apagado no meio da varredura
    except OSError:
        pass
    return total / _MB


def _fmt(valor: Optional[float]) -> str:
    return "?" if valor is None else f"{valor:,.0f}".replace(",", "")


class Vigia:
    """Thread que imprime o estado a cada ``intervalo`` segundos.

    ``entra(fonte)`` e ``sai(fonte)`` mantêm a lista das fontes em andamento;
    ``pasta`` é a raiz temporária, cujo tamanho acompanha o disco gasto.
    """

    def __init__(self, pasta: Path, intervalo: float = 30.0) -> None:
        self.pasta = pasta
        self.intervalo = intervalo
        self._ativas: Dict[str, float] = {}
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._laco, name="vigia", daemon=True)
        self._inicio = time.monotonic()

    def entra(self, fonte: str) -> None:
        with self._trava:
            self._ativas[fonte] = time.monotonic()

    def sai(self, fonte: str) -> None:
        with self._trava:
            self._ativas.pop(fonte, None)

    def estado(self) -> str:
        m = agora(self.pasta)
        with self._trava:
            ativas: Set[str] = set(self._ativas)
            desde = dict(self._ativas)
        em_curso = ", ".join(f"{s} {time.monotonic() - desde[s]:.0f}s" for s in sorted(ativas)) or "-"
        return (f"[recursos] t={time.monotonic() - self._inicio:.0f}s "
                f"rss={_fmt(m['rss'])}MB pico={_fmt(m['pico'])}MB "
                f"livre={_fmt(m['livre'])}MB disco_livre={_fmt(m['disco'])}MB "
                f"tmp={_fmt(pasta_mb(self.pasta))}MB em_curso: {em_curso}")

    def _laco(self) -> None:
        while not self._parar.wait(self.intervalo):
            registra(self.estado())

    def __enter__(self) -> "Vigia":
        registra(self.estado())
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._parar.set()
        registra(self.estado())
