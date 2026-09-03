"""Mede o pico de memória da exportação por formato em guaraci.datasus.frames.

O caminho sqlite é o único que materializa: ``collect()`` traz o conjunto
inteiro, ``to_pandas()`` faz uma segunda cópia (com as colunas de texto virando
objetos Python, que é onde a conta estoura) e só então ``to_sql`` escreve.
Parquet e CSV escrevem em streaming a partir do plano lazy.

Uso:
    python scripts/bench_sqlite_export.py <formato> <linhas>

Imprime uma linha ``formato linhas pico_mb segundos bytes_saida``.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guaraci.datasus import frames


class _MemCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("PageFaultCount", ctypes.wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
# Sem estes `restype`/`argtypes`, o pseudo-handle do processo (-1) é truncado
# na conversão e a chamada devolve 0 em silêncio, dando "pico de 0 MB".
_kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
_kernel32.K32GetProcessMemoryInfo.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.POINTER(_MemCounters),
    ctypes.wintypes.DWORD,
]
_kernel32.K32GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL


def pico_mb() -> float:
    counters = _MemCounters()
    counters.cb = ctypes.sizeof(_MemCounters)
    if not _kernel32.K32GetProcessMemoryInfo(
        _kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError(ctypes.get_last_error(), "K32GetProcessMemoryInfo falhou")
    return counters.PeakWorkingSetSize / 1024 / 1024


def gera_parquet(destino: Path, linhas: int) -> None:
    """Escreve um parquet com a forma típica de um extrato do SINAN."""
    bloco = 200_000
    partes = []
    for inicio in range(0, linhas, bloco):
        n = min(bloco, linhas - inicio)
        indices = pl.int_range(inicio, inicio + n, eager=True)
        partes.append(
            pl.DataFrame(
                {
                    "NU_NOTIFIC": indices.cast(pl.Utf8),
                    "DT_NOTIFIC": pl.Series(["2024-03-15"] * n),
                    "SG_UF_NOT": pl.Series(["SP", "RJ", "MG", "BA"] * (n // 4 + 1))[:n],
                    "ID_MUNICIP": (indices % 5570).cast(pl.Utf8).str.zfill(6),
                    "CS_SEXO": pl.Series(["M", "F"] * (n // 2 + 1))[:n],
                    "NU_IDADE_N": (indices % 100).cast(pl.Int32),
                    "CLASSI_FIN": (indices % 13).cast(pl.Utf8),
                    "EVOLUCAO": (indices % 4).cast(pl.Utf8),
                    "CRITERIO": (indices % 3).cast(pl.Utf8),
                    "OBSERVACOES": pl.Series(["texto livre de notificacao " * 3] * n),
                }
            )
        )
    pl.concat(partes).write_parquet(destino)


def main() -> None:
    """Dois modos, para não medir a geração junto com a exportação.

    ``gerar <arquivo> <linhas>`` escreve o parquet de entrada. ``exportar
    <arquivo> <formato>`` mede só a escrita, num processo que nunca alocou o
    conjunto inteiro, de modo que o pico é atribuível à exportação.
    """
    modo = sys.argv[1]

    if modo == "gerar":
        gera_parquet(Path(sys.argv[2]), int(sys.argv[3]))
        return

    origem = Path(sys.argv[2])
    formato = sys.argv[3]
    base = pico_mb()

    with TemporaryDirectory() as tmp:
        plano = pl.scan_parquet(origem)
        inicio = time.perf_counter()
        saida = frames.write_frame(
            plano, output_dir=Path(tmp), stem="bench", format=formato
        )
        duracao = time.perf_counter() - inicio
        tamanho = saida.stat().st_size if saida and saida.exists() else 0

    print(
        f"{formato:8} pico={pico_mb():6.0f}MB base={base:5.0f}MB "
        f"custo={pico_mb() - base:6.0f}MB tempo={duracao:5.1f}s "
        f"saida={tamanho / 1024 / 1024:.0f}MB"
    )


if __name__ == "__main__":
    main()
