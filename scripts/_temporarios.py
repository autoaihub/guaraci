"""Pasta temporária das verificações, apagada ao fim da execução.

As baterias de ``scripts/verificar_*.py`` baixam recortes reais (dezenas ou
centenas de MB por rodada) para pastas em ``%TEMP%``. Sem limpeza, cada rodada
deixa o que baixou para trás e o disco enche. Toda pasta criada aqui é apagada
na saída do processo, inclusive quando a bateria falha no meio.

Para inspecionar o que foi baixado, rode com ``GUARACI_MANTER_TEMP=1``: as
pastas ficam e o caminho de cada uma sai no stderr.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

__all__ = ["pasta_temporaria"]

_MANTER = os.environ.get("GUARACI_MANTER_TEMP", "").strip() not in ("", "0")


def _apagar(caminho: str) -> None:
    if _MANTER:
        print(f"[temporarios] mantida: {caminho}", file=sys.stderr)
        return
    shutil.rmtree(caminho, ignore_errors=True)


def pasta_temporaria(prefixo: str) -> Path:
    """Cria uma pasta em ``%TEMP%`` e agenda a remoção dela na saída."""
    caminho = tempfile.mkdtemp(prefix=prefixo)
    atexit.register(_apagar, caminho)
    return Path(caminho)
