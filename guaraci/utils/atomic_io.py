"""Troca atômica de arquivo resistente aos bloqueios transitórios do Windows.

``os.replace`` é atômico nas três plataformas, mas no Windows ele falha com
``PermissionError`` (WinError 5 ou 32) enquanto qualquer outro processo mantém
um handle aberto sobre o destino, ainda que só para leitura. Indexador de
busca, antivírus e um leitor concorrente do próprio arquivo produzem janelas de
alguns milissegundos em que a troca é recusada.

O sintoma observado foi a persistência de jobs da API abortando de forma
intermitente ao gravar ``jobs.json``, com o trabalho já registrado em memória e
perdido em disco. Como a janela é curta, algumas tentativas espaçadas resolvem;
o que não se pode é deixar a exceção subir na primeira recusa.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# Cinco tentativas cobrem cerca de 150 ms no total, folga larga para o handle
# de um indexador. Passado esse ponto, o bloqueio não é transitório e o erro
# precisa aparecer em vez de virar espera indefinida.
_ATTEMPTS = 5
_INITIAL_BACKOFF = 0.01


def replace_with_retry(source: Path, target: Path) -> None:
    """Move ``source`` sobre ``target``, reagendando recusas transitórias."""
    espera = _INITIAL_BACKOFF
    for tentativa in range(_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if tentativa == _ATTEMPTS - 1:
                raise
            time.sleep(espera)
            espera *= 2
